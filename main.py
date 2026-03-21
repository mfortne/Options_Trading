"""
Main entry point — Options Trading Bot (Schwab API)

Run this file directly or via run_scan.sh on a cron schedule.

Each run:
  1.  Check market hours — exit silently if closed
  2.  Expire stale pending trades (>10 min old)
  3.  Process any approve/reject replies that arrived since last scan
  4.  Scan each symbol across all portfolios
  5.  Queue top eligible put + call as pending trades
  6.  Send Telegram alert and wait for your approve/reject reply
  7.  Log approved trades to paper_portfolio.json and trades.xlsx
  8.  Check all open positions for take-profit / stop-loss signals
  9.  Send portfolio summary at end of scan

Cron (every 30 min, Mon-Fri):
  */30 9-16 * * 1-5 /path/to/venv/bin/python /path/to/main.py
"""

import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

from schwab_client import SchwabClient, _next_expiration_date
from cache import OptionsCache
from market_hours import is_market_open, market_status_message
from paper_portfolio import PaperPortfolioManager
from excel_logger import log_pipeline_run
from notifier import (
    send_message,
    send_trade_alert,
    listen_for_replies,
    listen_for_any_replies,
    notify_error,
    notify_startup,
    build_scan_summary,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH    = "portfolio_config.json"
REPLY_TIMEOUT  = 600   # Seconds to wait for approve/reject per trade (10 min)
RETRY_ATTEMPTS = 3
RETRY_DELAY    = 10    # Seconds between retries on API failure


def load_config() -> dict:
    """Load portfolio_config.json."""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def fetch_chain_with_retry(client, cache, symbol, expiration_date):
    """
    Cache-first fetch with retry on API failure.
    Returns OptionsChain or None after all retries exhausted.
    """
    chain = cache.get_options_chain(symbol, expiration_date)
    if chain:
        print(f"  [{symbol}] Cache hit")
        return chain

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            chain = client.fetch_options_chain(symbol, expiration_date)
            if chain:
                cache.set_options_chain(chain, ttl_minutes=60)
                return chain
        except Exception as e:
            if attempt < RETRY_ATTEMPTS:
                print(f"  [{symbol}] Attempt {attempt}/{RETRY_ATTEMPTS} failed: {e}")
                print(f"  [{symbol}] Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                raise

    return None


def filter_eligible(chain, rules: dict) -> tuple:
    """
    Apply delta, premium, and spread filters.
    Returns (eligible_puts, eligible_calls) sorted by bid descending.
    """
    delta_min   = rules["target_delta_min"]
    delta_max   = rules["target_delta_max"]
    min_premium = rules["min_premium"]
    max_spread  = rules["max_bid_ask_spread"]

    puts = [
        p for p in chain.puts
        if p.delta is not None
        and p.bid_ask_spread <= max_spread
        and p.bid >= min_premium
        and delta_min <= abs(p.delta) <= delta_max
    ]

    calls = [
        c for c in chain.calls
        if c.delta is not None
        and c.bid_ask_spread <= max_spread
        and c.bid >= min_premium
        and delta_min <= c.delta <= delta_max
    ]

    puts.sort(key=lambda x: x.bid, reverse=True)
    calls.sort(key=lambda x: x.bid, reverse=True)

    return puts, calls


# ---------------------------------------------------------------------------
# Trade approval flow
# ---------------------------------------------------------------------------

def queue_and_await_approval(pm: PaperPortfolioManager,
                              option,
                              option_type: str,
                              chain,
                              portfolio_name: str,
                              expiration_date: str) -> bool:
    """
    Queue a single trade, send Telegram alert, wait for reply.
    Returns True if approved, False if rejected or timed out.
    """
    try:
        dte = option.days_to_expiration()
    except ValueError:
        return False

    strategy = "CSP" if option_type == "PUT" else "CC"

    trade = pm.add_pending_trade(
        symbol          = chain.symbol,
        option_type     = option_type,
        strike          = option.strike,
        expiration_date = expiration_date,
        dte             = dte,
        bid             = option.bid,
        delta           = round(option.delta, 2),
        spread          = round(option.bid_ask_spread, 2),
        current_price   = chain.current_price,
        portfolio_name  = portfolio_name,
        strategy        = strategy,
        contracts       = 1,
    )

    if not trade:
        # Portfolio at capacity — add_pending_trade returned {}
        return False

    # Send alert and wait for your reply
    send_trade_alert(trade)
    action, trade_id = listen_for_replies(timeout_seconds=REPLY_TIMEOUT)

    if action == "approve" and trade_id == trade["trade_id"]:
        position = pm.approve_trade(trade["trade_id"])
        if position:
            send_message(
                f"✅ *Trade Opened*\n"
                f"{position['symbol']} ${position['strike']} {position['option_type']} "
                f"exp {position['expiration_date']}\n"
                f"Position ID: `{position['position_id']}`"
            )
            return True

    elif action == "reject" and trade_id == trade["trade_id"]:
        pm.reject_trade(trade["trade_id"])
        send_message(f"❌ Trade `{trade['trade_id']}` rejected.")

    else:
        # Timeout or no matching reply
        pm.reject_trade(trade["trade_id"], reason="No reply — auto-expired")
        send_message(f"⏰ Trade `{trade['trade_id']}` expired (no reply in 10 min).")

    return False


# ---------------------------------------------------------------------------
# Exit signal handling
# ---------------------------------------------------------------------------

def check_and_notify_exits(pm: PaperPortfolioManager):
    """
    Check all open positions for take-profit / stop-loss triggers.
    Sends a Telegram alert for each — you close manually for now.
    Auto-close will be added in a later session.
    """
    signals = pm.check_exit_signals()
    if not signals:
        return

    for item in signals:
        pos    = item["position"]
        signal = item["signal"]

        emoji = "💰" if signal == "TAKE_PROFIT" else "🛑"
        label = "TAKE PROFIT" if signal == "TAKE_PROFIT" else "STOP LOSS"

        send_message(
            f"{emoji} *{label} Signal*\n"
            f"{pos['symbol']} ${pos['strike']} {pos['option_type']} "
            f"exp {pos['expiration_date']}\n"
            f"Entry: ${pos['entry_premium']:.2f} | "
            f"Current: ${pos['current_premium']:.2f}\n"
            f"P&L: ${pos['unrealized_pnl']:+.2f} ({pos['unrealized_pnl_pct']:+.1f}%)\n"
            f"Position ID: `{pos['position_id']}`\n"
            f"_Review and close manually when ready._"
        )


# ---------------------------------------------------------------------------
# Main scan loop
# ---------------------------------------------------------------------------

def run_scan():
    """Run one full options scan cycle."""

    # ----------------------------------------------------------------
    # 1. Market hours check
    # ----------------------------------------------------------------
    notify_closed = os.getenv("NOTIFY_MARKET_CLOSED", "true").lower() == "true"
    is_open, reason = is_market_open()
    print(f"Market: {reason}")

    if not is_open:
        if notify_closed:
            send_message(market_status_message(is_open, reason))
        else:
            print("Market closed — skipping scan.")
        return

    # ----------------------------------------------------------------
    # 2. Load config + initialise clients
    # ----------------------------------------------------------------
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
        notify_error(f"Initialisation failed: {e}")
        return

    rules = config["rules"]

    print("=" * 60)
    print("Options Scan Starting")
    print("=" * 60)

    notify_startup()

    # ----------------------------------------------------------------
    # 3. Expire stale pending trades from previous scan
    # ----------------------------------------------------------------
    pm.expire_pending_trades(max_age_minutes=10)

    # ----------------------------------------------------------------
    # 4. Process any approve/reject replies that arrived since last run
    # ----------------------------------------------------------------
    pending_replies = listen_for_any_replies()
    for action, trade_id in pending_replies:
        if action == "approve":
            position = pm.approve_trade(trade_id)
            if position:
                send_message(
                    f"✅ *Trade Opened* (queued reply)\n"
                    f"{position['symbol']} ${position['strike']} "
                    f"{position['option_type']} exp {position['expiration_date']}\n"
                    f"Position ID: `{position['position_id']}`"
                )
        elif action == "reject":
            pm.reject_trade(trade_id)
            send_message(f"❌ Trade `{trade_id}` rejected.")

    # ----------------------------------------------------------------
    # 5. Deduplicate symbols across all portfolios
    # ----------------------------------------------------------------
    symbol_portfolios: dict = {}
    for portfolio in config["portfolios"]:
        for symbol in portfolio["symbols"]:
            if symbol not in symbol_portfolios:
                symbol_portfolios[symbol] = []
            symbol_portfolios[symbol].append(portfolio["name"])

    expiration_date = _next_expiration_date()
    print(f"Target expiration: {expiration_date}")
    print(f"Symbols: {list(symbol_portfolios.keys())}\n")

    # ----------------------------------------------------------------
    # 6. Scan each symbol
    # ----------------------------------------------------------------
    for symbol, portfolios in symbol_portfolios.items():
        portfolio_label = ", ".join(portfolios)
        print(f"Scanning {symbol} ({portfolio_label})...")

        try:
            chain = fetch_chain_with_retry(client, cache, symbol, expiration_date)
            if not chain:
                notify_error(f"{symbol}: could not fetch options chain after retries")
                continue

            print(f"  Price: ${chain.current_price:.2f}")

            eligible_puts, eligible_calls = filter_eligible(chain, rules)
            print(f"  Eligible puts:  {len(eligible_puts)}")
            print(f"  Eligible calls: {len(eligible_calls)}")

            # Always log scan results to Excel
            log_pipeline_run(
                symbol=symbol,
                current_price=chain.current_price,
                eligible_puts=eligible_puts,
                eligible_calls=eligible_calls,
            )

            # Send scan summary to Telegram
            send_message(build_scan_summary(
                symbol=symbol,
                current_price=chain.current_price,
                eligible_puts=eligible_puts,
                eligible_calls=eligible_calls,
                portfolio_name=portfolio_label,
            ))

            # Queue top put — first portfolio with capacity gets it
            if eligible_puts:
                for portfolio_name in portfolios:
                    approved = queue_and_await_approval(
                        pm, eligible_puts[0], "PUT",
                        chain, portfolio_name, expiration_date
                    )
                    if approved:
                        break

            # Queue top call — first portfolio with capacity gets it
            if eligible_calls:
                for portfolio_name in portfolios:
                    approved = queue_and_await_approval(
                        pm, eligible_calls[0], "CALL",
                        chain, portfolio_name, expiration_date
                    )
                    if approved:
                        break

        except Exception as e:
            error_msg = f"{symbol} scan failed: {e}"
            print(f"  ERROR: {error_msg}")
            notify_error(error_msg)

    # ----------------------------------------------------------------
    # 7. Check open positions for take-profit / stop-loss
    # ----------------------------------------------------------------
    check_and_notify_exits(pm)

    # ----------------------------------------------------------------
    # 8. Send portfolio summary
    # ----------------------------------------------------------------
    send_message(pm.format_summary_message())

    print("\n✓ Scan complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_scan()
