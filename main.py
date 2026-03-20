"""
Main entry point for options trading system
Test script for data pipeline (Schwab API edition)
"""

import json
import sys
from pathlib import Path
from schwab_client import SchwabClient
from cache import OptionsCache
from models import OptionType


def load_config(config_path: str = "portfolio_config.json") -> dict:
    """Load configuration from JSON"""
    with open(config_path, 'r') as f:
        return json.load(f)


def test_data_pipeline():
    """Test Schwab API and caching"""

    # Load config
    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: portfolio_config.json not found")
        print("Please copy portfolio_config.json to your working directory")
        return

    api_cfg = config['api']

    # Check for Schwab credentials
    api_key    = api_cfg.get('schwab_api_key', '')
    app_secret = api_cfg.get('schwab_app_secret', '')
    callback_url = api_cfg.get('schwab_callback_url', 'https://127.0.0.1:8182')
    token_path   = api_cfg.get('schwab_token_path', 'schwab_token.json')

    if not api_key or api_key == "YOUR_SCHWAB_APP_KEY_HERE":
        print("Error: Schwab API key not configured")
        print("1. Create an app at https://developer.schwab.com")
        print("2. Update 'api.schwab_api_key' in portfolio_config.json")
        return

    if not app_secret or app_secret == "YOUR_SCHWAB_APP_SECRET_HERE":
        print("Error: Schwab app secret not configured")
        print("1. Create an app at https://developer.schwab.com")
        print("2. Update 'api.schwab_app_secret' in portfolio_config.json")
        return

    print("=" * 80)
    print("Options Trading Data Pipeline Test  (Schwab API)")
    print("=" * 80)

    # Initialize clients
    client = SchwabClient(
        api_key=api_key,
        app_secret=app_secret,
        callback_url=callback_url,
        token_path=token_path,
    )
    cache = OptionsCache()

    # Test with first symbol from config
    symbol = config['portfolios'][0]['symbols'][0]
    print(f"\nTesting with symbol: {symbol}")

    # Test 1: Get quote
    print("\n[1] Fetching stock quote...")
    try:
        quote = client.get_quote(symbol)
        print(f"  Current price: ${quote['current_price']:.2f}")
        print(f"  High:          ${quote['high']:.2f}")
        print(f"  Low:           ${quote['low']:.2f}")
    except Exception as e:
        print(f"  Error: {e}")
        return

    # Test 2: Get expirations
    print(f"\n[2] Fetching option expirations for {symbol}...")
    try:
        expirations = client.get_option_expirations(symbol)
        print(f"  Found {len(expirations)} expirations")
        print(f"  Nearest 3: {expirations[:3]}")
    except Exception as e:
        print(f"  Error: {e}")
        return

    if not expirations:
        print(f"  No expirations found for {symbol}")
        return

    # Test 3: Fetch options chain (with caching)
    expiration = expirations[0]
    print(f"\n[3] Fetching options chain for {symbol} {expiration}...")

    print("  Fetching from API (first time)...")
    try:
        chain = client.fetch_options_chain(symbol, expiration)
        if not chain:
            print(f"  Error: Could not fetch options chain")
            return

        print(f"  ✓ Calls: {len(chain.calls)}")
        print(f"  ✓ Puts: {len(chain.puts)}")

        print("  Caching...")
        cache.set_options_chain(chain, ttl_minutes=60)
    except Exception as e:
        print(f"  Error: {e}")
        return

    # Test 4: Retrieve from cache
    print(f"\n[4] Testing cache retrieval...")
    try:
        cached_chain = cache.get_options_chain(symbol, expiration)
        if cached_chain:
            print(f"  ✓ Cache hit!")
            print(f"  ✓ Calls in cache: {len(cached_chain.calls)}")
            print(f"  ✓ Puts in cache:  {len(cached_chain.puts)}")
        else:
            print(f"  Cache miss (expected on first run)")
    except Exception as e:
        print(f"  Error: {e}")

    # Test 5: Filter options by rules
    print(f"\n[5] Filtering options by rules (delta 0.10-0.20)...")

    rules = config['rules']
    delta_min   = rules['target_delta_min']
    delta_max   = rules['target_delta_max']
    min_premium = rules['min_premium']
    max_spread  = rules['max_bid_ask_spread']

    eligible_puts = []
    for put in chain.puts:
        if put.delta is None:
            continue
        abs_delta = abs(put.delta)
        if (put.bid_ask_spread <= max_spread and
                put.bid >= min_premium and
                delta_min <= abs_delta <= delta_max):
            eligible_puts.append(put)

    print(f"  Found {len(eligible_puts)} eligible puts")
    if eligible_puts:
        print("\n  Top 3 puts to sell (by premium):")
        for put in sorted(eligible_puts, key=lambda x: x.bid, reverse=True)[:3]:
            print(f"    Strike ${put.strike:.2f}: "
                  f"Bid ${put.bid:.2f}, "
                  f"Delta {put.delta:.2f}, "
                  f"Spread ${put.bid_ask_spread:.2f}")

    eligible_calls = []
    for call in chain.calls:
        if call.delta is None:
            continue
        if (call.bid_ask_spread <= max_spread and
                call.bid >= min_premium and
                delta_min <= call.delta <= delta_max):
            eligible_calls.append(call)

    print(f"\n  Found {len(eligible_calls)} eligible calls")
    if eligible_calls:
        print("\n  Top 3 calls to sell (by premium):")
        for call in sorted(eligible_calls, key=lambda x: x.bid, reverse=True)[:3]:
            print(f"    Strike ${call.strike:.2f}: "
                  f"Bid ${call.bid:.2f}, "
                  f"Delta {call.delta:.2f}, "
                  f"Spread ${call.bid_ask_spread:.2f}")
            
# Quick & dirty logging hook
    from excel_logger import log_pipeline_run

    # Test 6: Cache statistics
    print(f"\n[6] Cache statistics:")
    stats = cache.get_cache_size()
    print(f"  Cached option chains: {stats['options_chains']}")
    print(f"  Cached quotes: {stats['quotes']}")
    log_pipeline_run(
        symbol=symbol,
        current_price=quote['current_price'],
        eligible_puts=eligible_puts,
        eligible_calls=eligible_calls
    )

    print(f"\n[✓] Data pipeline test complete!")
    print(f"API calls remaining this minute: {client.get_rate_limit_remaining()}/{SchwabClient._RATE_LIMIT_MAX}")


if __name__ == "__main__":
    test_data_pipeline()
