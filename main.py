"""
Main entry point for options trading system
Runs hourly, checks market hours before scanning
"""

import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

from schwab_client import SchwabClient
from cache import OptionsCache
from market_hours import is_market_open, market_status_message
from excel_logger import log_pipeline_run
from notifier import build_scan_summary, notify_error, notify_startup, send_message


def load_config(config_path: str = "portfolio_config.json") -> dict:
    with open(config_path, 'r') as f:
        return json.load(f)


def fetch_chain_with_retry(client, cache, symbol, expiration_date, retries=3, delay=10):
    """
    Fetch options chain with cache-first logic and retry on server errors.
    Always uses a specific expiration date to avoid 502s on large chains.
    """
    # Cache-first
    chain = cache.get_options_chain(symbol, expiration_date)
    if chain:
        print(f"  Cache hit for {symbol}")
        return chain

    # Fetch with retry
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


def run_scan():
    """Run one full options scan and notify via Telegram."""

    # ----------------------------------------------------------------
    # Market hours check
    # ----------------------------------------------------------------
    notify_closed = os.getenv("NOTIFY_MARKET_CLOSED", "true").lower() == "true"

    is_open, reason = is_market_open()
    print(f"Market status: {reason}")

    if not is_open:
        if notify_closed:
            send_message(market_status_message(is_open, reason))
        else:
            print("Market closed — notifications off, exiting.")
        return

    # ----------------------------------------------------------------
    # Load config
    # ----------------------------------------------------------------
    try:
        config = load_config()
    except FileNotFoundError:
        notify_error("portfolio_config.json not found")
        return

    api_cfg      = config['api']
    api_key      = api_cfg.get('schwab_api_key', '')
    app_secret   = api_cfg.get('schwab_app_secret', '')
    callback_url = api_cfg.get('schwab_callback_url', 'https://127.0.0.1:8182')
    token_path   = api_cfg.get('schwab_token_path', 'schwab_token.json')

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
    except Exception as e:
        notify_error(f"Failed to initialize client: {e}")
        return

    rules       = config['rules']
    delta_min   = rules['target_delta_min']
    delta_max   = rules['target_delta_max']
    min_premium = rules['min_premium']
    max_spread  = rules['max_bid_ask_spread']

    # Get nearest expiration date once — used for all symbols
    from schwab_client import _next_expiration_date
    expiration_date = _next_expiration_date()
    print(f"Target expiration: {expiration_date}")

    # Deduplicate symbols across portfolios
    symbol_portfolios: dict = {}
    for portfolio in config['portfolios']:
        for symbol in portfolio['symbols']:
            if symbol not in symbol_portfolios:
                symbol_portfolios[symbol] = []
            symbol_portfolios[symbol].append(portfolio['name'])

    print(f"Unique symbols to scan: {list(symbol_portfolios.keys())}")

    for symbol, portfolios in symbol_portfolios.items():
        portfolio_label = ", ".join(portfolios)
        print(f"\nScanning {symbol} (portfolios: {portfolio_label})...")

        try:
            chain = fetch_chain_with_retry(
                client, cache, symbol, expiration_date
            )

            if not chain:
                print(f"  Could not fetch chain after retries, skipping.")
                notify_error(f"{symbol}: could not fetch options chain after retries")
                continue

            print(f"  Price: ${chain.current_price:.2f}")

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

            log_pipeline_run(symbol, chain.current_price, eligible_puts, eligible_calls)

            msg = build_scan_summary(
                symbol=symbol,
                current_price=chain.current_price,
                eligible_puts=eligible_puts,
                eligible_calls=eligible_calls,
                portfolio_name=portfolio_label,
            )
            send_message(msg)

        except Exception as e:
            error_msg = f"{symbol} scan failed after all retries: {e}"
            print(f"  ERROR: {error_msg}")
            notify_error(error_msg)

    print("\n✓ Scan complete.")


if __name__ == "__main__":
    run_scan()
