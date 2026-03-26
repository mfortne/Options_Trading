"""
Main entry point — options scan loop with Telegram handler watchdog.

Runs hourly via cron (see run_scan.sh).
On each run it:
  1. Ensures telegram_handler.py is running — starts it if not
  2. Checks market hours — exits early if closed
  3. Scans all symbols across all portfolios
  4. Filters eligible puts/calls by rules
  5. Queues pending trades to paper_portfolio.json
  6. Re-prices open positions with live data
  7. Logs eligible options to trades.xlsx
  8. Sends Telegram summary for each symbol
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from cache import OptionsCache
from excel_logger import log_pipeline_run
from market_hours import is_market_open, market_status_message
from notifier import build_scan_summary, notify_error, notify_startup, send_message
from paper_portfolio import PaperPortfolioManager
from schwab_client import SchwabClient, _next_expiration_date


# ---------------------------------------------------------------------------
# Telegram handler watchdog  (PID file edition)
# ---------------------------------------------------------------------------

HANDLER_SCRIPT = Path(__file__).parent / "telegram_handler.py"
HANDLER_PID_FILE = Path(__file__).parent / "telegram_handler.pid"


def _read_pid() -> int | None:
    """Read the PID from the pid file. Returns None if file missing or corrupt."""
    try:
        return int(HANDLER_PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _write_pid(pid: int):
    """Write a PID to the pid file."""
    HANDLER_PID_FILE.write_text(str(pid))


def _clear_pid():
    """Remove the pid file (called when we know the process is dead)."""
    try:
        HANDLER_PID_FILE.unlink()
    except FileNotFoundError:
        pass


def _pid_is_alive(pid: int) -> bool:
    """
    Check if a process with this PID is actually running.
    Works on Linux, macOS, and Windows.
    """
    try:
        # os.kill(pid, 0) sends no signal — just checks if process exists.
        # Raises ProcessLookupError if dead, PermissionError if alive but
        # owned by another user (still counts as running).
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True   # Process exists, we just can't signal it


def ensure_telegram_handler():
    """
    Ensure telegram_handler.py is running, using a PID file to survive
    across separate cron invocations of main.py.

    Flow:
      1. Read PID file → if PID is alive, nothing to do
      2. If no PID file or PID is dead → start a new handler process
      3. Write the new PID to the file
    """
    pid = _read_pid()

    if pid is not None:
        if _pid_is_alive(pid):
            print(f"[Watchdog] telegram_handler already running (PID {pid}).")
            return
        else:
            print(f"[Watchdog] Stale PID {pid} found — process is dead, restarting.")
            _clear_pid()

    if not HANDLER_SCRIPT.exists():
        print(f"[Watchdog] WARNING: {HANDLER_SCRIPT} not found — skipping handler start.")
        print("[Watchdog] Drop telegram_handler.py into the project folder to enable it.")
        return

    print("[Watchdog] Starting telegram_handler.py ...")
    process = subprocess.Popen(
        [sys.executable, str(HANDLER_SCRIPT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,   # detach so it outlives this cron process
    )

    # Give it a moment to boot and send its Telegram "online" message
    time.sleep(2)

    if _pid_is_alive(process.pid):
        _write_pid(process.pid)
        print(f"[Watchdog] telegram_handler started (PID {process.pid}). PID saved to {HANDLER_PID_FILE.name}.")
    else:
        print("[Watchdog] telegram_handler failed to start — check the script for errors.")
        _clear_pid()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(config_path: str = "portfolio_config.json") -> dict:
    with open(config_path, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Fetch with cache-first + retry
# ---------------------------------------------------------------------------

def fetch_chain_with_retry(client, cache, symbol, expiration_date, retries=3, delay=10):
    """Cache-first options chain fetch with retry on server errors."""
    chain = cache.get_options_chain(symbol, expiration_date)
    if chain:
        print(f"  Cache hit for {symbol}")
        return chain

    for attempt in range(1, retries + 1):
        try:
            chain = client.fetch_options_chain(symbol, expiration_date)
            if chain:
                cache.set_options_chain(chain, ttl_minutes=60)
                return chain
        except Exception as e:
            if attempt < retries:
                print(f"  Attempt {attempt}/{retries} failed for {symbol}: {e}")
                print(f"  Retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise

    return None


# ---------------------------------------------------------------------------
# Re-price open positions for a symbol
# ---------------------------------------------------------------------------

def reprice_open_positions(pm: PaperPortfolioManager, symbol: str, chain):
    """
    Update current_premium on any open positions for this symbol
    using the live options chain. Triggers TP/SL threshold calculations
    that the telegram_handler will alert on next poll.
    """
    open_positions = [
        p for p in pm.get_open_positions() if p["symbol"] == symbol
    ]
    if not open_positions:
        return

    # Build a quick lookup: strike → option data
    all_options = chain.puts + chain.calls
    lookup = {(o.strike, o.option_type.value): o for o in all_options}

    for pos in open_positions:
        key = (pos["strike"], pos["option_type"])
        option = lookup.get(key)
        if not option:
            print(f"  Could not find live price for position {pos['position_id']} — skipping reprice")
            continue

        try:
            dte = option.days_to_expiration()
        except ValueError:
            dte = 0

        pm.update_position_price(
            position_id=pos["position_id"],
            current_premium=option.bid,
            current_price=chain.current_price,
            new_dte=dte,
        )
        print(f"  Re-priced {pos['position_id']} ({symbol} ${pos['strike']}): "
              f"${pos['entry_premium']:.2f} → ${option.bid:.2f}")


# ---------------------------------------------------------------------------
# Queue eligible options as pending trades
# ---------------------------------------------------------------------------

def queue_pending_trades(pm: PaperPortfolioManager,
                          symbol: str,
                          chain,
                          eligible_puts: list,
                          eligible_calls: list,
                          expiration_date: str,
                          portfolios: list):
    """
    For each portfolio that covers this symbol, queue the best eligible
    put (and call) as a pending trade waiting for Telegram approval.
    Only queues if the portfolio has capacity.
    """
    for portfolio in portfolios:
        portfolio_name = portfolio["name"]

        # Best put (highest premium)
        if eligible_puts:
            best_put = sorted(eligible_puts, key=lambda x: x.bid, reverse=True)[0]
            try:
                dte = best_put.days_to_expiration()
            except ValueError:
                dte = 0

            pm.add_pending_trade(
                symbol=symbol,
                option_type="PUT",
                strike=best_put.strike,
                expiration_date=expiration_date,
                dte=dte,
                bid=best_put.bid,
                delta=best_put.delta or 0.0,
                spread=best_put.bid_ask_spread,
                current_price=chain.current_price,
                portfolio_name=portfolio_name,
                strategy="CSP",
                contracts=1,
            )

        # Best call (highest premium)
        if eligible_calls:
            best_call = sorted(eligible_calls, key=lambda x: x.bid, reverse=True)[0]
            try:
                dte = best_call.days_to_expiration()
            except ValueError:
                dte = 0

            pm.add_pending_trade(
                symbol=symbol,
                option_type="CALL",
                strike=best_call.strike,
                expiration_date=expiration_date,
                dte=dte,
                bid=best_call.bid,
                delta=best_call.delta or 0.0,
                spread=best_call.bid_ask_spread,
                current_price=chain.current_price,
                portfolio_name=portfolio_name,
                strategy="CC",
                contracts=1,
            )


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def run_scan():
    """Run one full options scan."""

    # ── 1. Ensure Telegram handler is running ────────────────────────────
    ensure_telegram_handler()

    # ── 2. Market hours check ────────────────────────────────────────────
    notify_closed = os.getenv("NOTIFY_MARKET_CLOSED", "true").lower() == "true"
    is_open, reason = is_market_open()
    print(f"Market status: {reason}")

    if not is_open:
        if notify_closed:
            send_message(market_status_message(is_open, reason))
        else:
            print("Market closed — notifications off, exiting.")
        return

    # ── 3. Load config ───────────────────────────────────────────────────
    try:
        config = load_config()
    except FileNotFoundError:
        notify_error("portfolio_config.json not found")
        return

    api_cfg      = config["api"]
    api_key      = api_cfg.get("schwab_api_key", "")
    app_secret   = api_cfg.get("schwab_app_secret", "")
    callback_url = api_cfg.get("schwab_callback_url", "https://127.0.0.1:8182")
    token_path   = api_cfg.get("schwab_token_path", "schwab_token.json")

    if not api_key or api_key == "YOUR_SCHWAB_APP_KEY_HERE":
        notify_error("Schwab API key not configured in portfolio_config.json")
        return

    print("=" * 60)
    print("Options Scan Starting (Schwab API)")
    print("=" * 60)

    notify_startup()

    try:
        client = SchwabClient(
            api_key=api_key,
            app_secret=app_secret,
            callback_url=callback_url,
            token_path=token_path,
        )
        cache = OptionsCache()
        pm    = PaperPortfolioManager()
    except Exception as e:
        notify_error(f"Failed to initialize client: {e}")
        return

    # Expire stale pending trades from previous scans
    pm.expire_pending_trades(max_age_minutes=10)

    rules       = config["rules"]
    delta_min   = rules["target_delta_min"]
    delta_max   = rules["target_delta_max"]
    min_premium = rules["min_premium"]
    max_spread  = rules["max_bid_ask_spread"]

    expiration_date = _next_expiration_date()
    print(f"Target expiration: {expiration_date}")

    # Build symbol → portfolios map (deduplicated)
    symbol_portfolios: dict = {}
    for portfolio in config["portfolios"]:
        for symbol in portfolio["symbols"]:
            symbol_portfolios.setdefault(symbol, []).append(portfolio)

    print(f"Symbols to scan: {list(symbol_portfolios.keys())}")

    # ── 4-8. Per-symbol scan loop ─────────────────────────────────────────
    for symbol, portfolios in symbol_portfolios.items():
        portfolio_label = ", ".join(p["name"] for p in portfolios)
        print(f"\nScanning {symbol} (portfolios: {portfolio_label})...")

        try:
            chain = fetch_chain_with_retry(client, cache, symbol, expiration_date)
            if not chain:
                print(f"  Could not fetch chain after retries, skipping.")
                notify_error(f"{symbol}: could not fetch options chain after retries")
                continue

            print(f"  Price: ${chain.current_price:.2f}")

            # Filter eligible options
            eligible_puts = [
                p for p in chain.puts
                if p.delta is not None
                and p.bid_ask_spread <= max_spread
                and p.bid >= min_premium
                and delta_min <= abs(p.delta) <= delta_max
            ]
            eligible_calls = [
                c for c in chain.calls
                if c.delta is not None
                and c.bid_ask_spread <= max_spread
                and c.bid >= min_premium
                and delta_min <= c.delta <= delta_max
            ]

            print(f"  Eligible puts:  {len(eligible_puts)}")
            print(f"  Eligible calls: {len(eligible_calls)}")

            # Re-price any open positions for this symbol
            reprice_open_positions(pm, symbol, chain)

            # Queue best options as pending trades (Telegram approval required)
            queue_pending_trades(
                pm, symbol, chain,
                eligible_puts, eligible_calls,
                expiration_date, portfolios,
            )

            # Log to Excel
            log_pipeline_run(symbol, chain.current_price, eligible_puts, eligible_calls)

            # Send Telegram summary
            msg = build_scan_summary(
                symbol=symbol,
                current_price=chain.current_price,
                eligible_puts=eligible_puts,
                eligible_calls=eligible_calls,
                portfolio_name=portfolio_label,
            )
            send_message(msg)

        except Exception as e:
            error_msg = f"{symbol} scan failed: {e}"
            print(f"  ERROR: {error_msg}")
            notify_error(error_msg)

    print("\n✓ Scan complete.")


if __name__ == "__main__":
    run_scan()
