"""
Standalone Schwab OAuth token refresher.
Bypasses market hours check — run anytime to keep your token alive.

Usage:
    python refresh_token.py

The Schwab refresh token expires after 7 days of inactivity.
Run this script daily (or add to cron) to prevent re-authentication.
"""

import json
import sys
from pathlib import Path


def main():
    # Load config
    config_path = "portfolio_config.json"
    if not Path(config_path).exists():
        print(f"❌ Error: {config_path} not found.")
        print("   Make sure you run this from your project directory.")
        sys.exit(1)

    try:
        config = json.load(open(config_path))
    except json.JSONDecodeError as e:
        print(f"❌ Error reading {config_path}: {e}")
        sys.exit(1)

    api = config.get("api", {})
    api_key      = api.get("schwab_api_key", "")
    app_secret   = api.get("schwab_app_secret", "")
    callback_url = api.get("schwab_callback_url", "https://127.0.0.1:8182")
    token_path   = api.get("schwab_token_path", "schwab_token.json")

    if not api_key or api_key == "YOUR_SCHWAB_APP_KEY_HERE":
        print("❌ Schwab API key not configured in portfolio_config.json")
        sys.exit(1)

    if not app_secret or app_secret == "YOUR_SCHWAB_APP_SECRET_HERE":
        print("❌ Schwab app secret not configured in portfolio_config.json")
        sys.exit(1)

    # Import here so missing schwab-py gives a clean error
    try:
        from schwab_client import SchwabClient
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Run: pip install schwab-py")
        sys.exit(1)

    print("=" * 50)
    print("Schwab OAuth Token Refresher")
    print("=" * 50)

    token_file = Path(token_path)
    if token_file.exists():
        print(f"✓ Token file found: {token_path}")
    else:
        print(f"⚠ No token file found at {token_path}")
        print("  A browser window will open for first-time login.")

    print("\nConnecting to Schwab API...")

    try:
        client = SchwabClient(
            api_key=api_key,
            app_secret=app_secret,
            callback_url=callback_url,
            token_path=token_path,
        )

        # Fetch a quote to confirm the token works
        print("Verifying token with a live quote (SPY)...")
        quote = client.get_quote("SPY")
        print(f"\n✅ Token is valid!")
        print(f"   SPY = ${quote['current_price']:.2f}")
        print(f"   Token file: {token_path}")
        print(f"\nThe 7-day expiration clock has been reset.")

    except Exception as e:
        print(f"\n❌ Token refresh failed: {e}")
        print("\nTo fix:")
        print(f"  1. Delete {token_path}")
        print(f"  2. Run this script again — browser will open for login")
        sys.exit(1)


if __name__ == "__main__":
    main()
