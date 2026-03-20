"""
Charles Schwab API client for options data.

Key changes:
  - fetch_options_chain() always passes a specific expiration date
    to avoid 502 errors on large chains like QQQ and SPY.
  - _next_expiration_date() calculates the nearest Friday automatically.
  - get_option_expirations() kept for backwards compatibility only.
"""

import os
import time
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List

from models import OptionChainData, OptionsChain, OptionType

try:
    import schwab
    from schwab import auth as schwab_auth
except ImportError:
    raise ImportError("schwab-py is not installed. Run: pip install schwab-py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int(val, default: int = 0) -> int:
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _next_expiration_date() -> str:
    """
    Return the nearest upcoming Friday as YYYY-MM-DD.
    Most options expire on Fridays. If today is Friday, use next Friday.
    """
    today = date.today()
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7  # Never use today even if it's Friday
    nearest_friday = today + timedelta(days=days_until_friday)
    return nearest_friday.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class SchwabClient:
    """Schwab Trader API wrapper."""

    _RATE_LIMIT_MAX = 120

    def __init__(
        self,
        api_key: str,
        app_secret: str,
        callback_url: str = "https://127.0.0.1:8182",
        token_path: str = "schwab_token.json",
    ):
        self.api_key = api_key
        self.app_secret = app_secret
        self.callback_url = callback_url
        self.token_path = token_path

        self._request_count = 0
        self._minute_start = time.time()
        self._client = self._build_client()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _build_client(self):
        if os.path.exists(self.token_path):
            try:
                client = schwab_auth.client_from_token_file(
                    token_path=self.token_path,
                    api_key=self.api_key,
                    app_secret=self.app_secret,
                )
                print(f"[SchwabClient] Loaded token from {self.token_path}")
                return client
            except Exception as exc:
                print(f"[SchwabClient] Token file invalid ({exc}); re-authenticating...")

        if os.environ.get("SCHWAB_HEADLESS"):
            print("[SchwabClient] Headless mode: follow the URL printed below.")
            client = schwab_auth.client_from_manual_flow(
                api_key=self.api_key,
                app_secret=self.app_secret,
                callback_url=self.callback_url,
                token_path=self.token_path,
            )
        else:
            print("[SchwabClient] Opening browser for OAuth login...")
            client = schwab_auth.easy_client(
                api_key=self.api_key,
                app_secret=self.app_secret,
                callback_url=self.callback_url,
                token_path=self.token_path,
            )

        print(f"[SchwabClient] Token saved to {self.token_path}")
        return client

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _track_request(self):
        now = time.time()
        if now - self._minute_start >= 60:
            self._request_count = 0
            self._minute_start = now
        self._request_count += 1

    def get_rate_limit_remaining(self) -> int:
        elapsed = time.time() - self._minute_start
        if elapsed >= 60:
            return self._RATE_LIMIT_MAX
        return max(0, self._RATE_LIMIT_MAX - self._request_count)

    def wait_if_rate_limited(self):
        if self.get_rate_limit_remaining() < 5:
            wait = 60 - (time.time() - self._minute_start)
            if wait > 0:
                print(f"[SchwabClient] Rate limit close; waiting {wait:.0f}s...")
                time.sleep(wait)
            self._request_count = 0
            self._minute_start = time.time()

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------

    def get_quote(self, symbol: str) -> Dict[str, float]:
        """Fetch current stock quote."""
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"Invalid symbol: {symbol!r}")

        symbol = symbol.upper().strip()
        if not (1 <= len(symbol) <= 10):
            raise ValueError(f"Symbol must be 1-10 characters: {symbol!r}")

        self.wait_if_rate_limited()
        self._track_request()

        resp = self._client.get_quote(symbol)
        resp.raise_for_status()
        data = resp.json()

        ticker_data = data.get(symbol, {})
        quote = ticker_data.get("quote", {})

        current_price = _safe_float(quote.get("lastPrice") or quote.get("mark"))
        if current_price == 0:
            raise ValueError(f"No quote data available for symbol: {symbol}")

        return {
            "current_price": current_price,
            "high":           _safe_float(quote.get("highPrice")),
            "low":            _safe_float(quote.get("lowPrice")),
            "open":           _safe_float(quote.get("openPrice")),
            "previous_close": _safe_float(quote.get("closePrice")),
        }

    # ------------------------------------------------------------------
    # Fetch full chain — always uses a specific expiration date
    # ------------------------------------------------------------------

    def fetch_options_chain(
        self,
        symbol: str,
        expiration_date: Optional[str] = None,
    ) -> Optional[OptionsChain]:
        """
        Fetch and parse a complete options chain for one expiration.
        Always passes a specific date to avoid 502s on large chains.
        If no date given, uses the nearest upcoming Friday.
        """
        self.wait_if_rate_limited()
        self._track_request()

        # Always use a specific date — never fetch unfiltered full chain
        if expiration_date is None:
            expiration_date = _next_expiration_date()

        try:
            exp_dt = datetime.strptime(expiration_date, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"expiration_date must be YYYY-MM-DD, got: {expiration_date!r}")

        try:
            quote = self.get_quote(symbol)
            current_price = quote["current_price"]

            resp = self._client.get_option_chain(
                symbol,
                from_date=exp_dt,
                to_date=exp_dt,
                include_underlying_quote=False,
            )
            resp.raise_for_status()
            raw = resp.json()

            calls = self._parse_side(raw.get("callExpDateMap", {}), expiration_date)
            puts  = self._parse_side(raw.get("putExpDateMap",  {}), expiration_date)

            options_chain = OptionsChain(
                symbol=symbol,
                current_price=current_price,
                fetch_time=datetime.now(),
            )

            def _build_option(data: dict, opt_type: OptionType) -> Optional[OptionChainData]:
                try:
                    option = OptionChainData(
                        symbol=symbol,
                        expiration_date=expiration_date,
                        strike=_safe_float(data.get("strike")),
                        option_type=opt_type,
                        bid=_safe_float(data.get("bid")),
                        ask=_safe_float(data.get("ask")),
                        last_price=_safe_float(data.get("last")) or None,
                        volume=_safe_int(data.get("volume")) or None,
                        open_interest=_safe_int(data.get("openInterest")) or None,
                        implied_volatility=data.get("impliedVolatility"),
                        delta=data.get("delta"),
                        theta=data.get("theta"),
                        gamma=data.get("gamma"),
                        vega=data.get("vega"),
                    )
                    option.calculate_derived()
                    return option
                except Exception as exc:
                    print(f"[SchwabClient] Error parsing option: {exc}")
                    return None

            for call_data in calls:
                opt = _build_option(call_data, OptionType.CALL)
                if opt:
                    options_chain.calls.append(opt)

            for put_data in puts:
                opt = _build_option(put_data, OptionType.PUT)
                if opt:
                    options_chain.puts.append(opt)

            return options_chain

        except Exception as exc:
            print(f"[SchwabClient] Error fetching options chain for {symbol}: {exc}")
            raise  # Re-raise so retry logic in main.py catches it

    # ------------------------------------------------------------------
    # Kept for backwards compatibility
    # ------------------------------------------------------------------

    def get_option_expirations(self, symbol: str) -> List[str]:
        """
        Kept for backwards compatibility.
        Prefer fetch_options_chain() which handles expiration internally.
        """
        self.wait_if_rate_limited()
        self._track_request()

        resp = self._client.get_option_chain(
            symbol,
            include_underlying_quote=False,
        )
        resp.raise_for_status()
        data = resp.json()

        expirations: set = set()
        for side in ("callExpDateMap", "putExpDateMap"):
            for exp_key in data.get(side, {}).keys():
                expirations.add(exp_key.split(":")[0])

        return sorted(expirations)

    @staticmethod
    def _parse_side(exp_map: dict, target_date: str) -> List[Dict[str, Any]]:
        """Convert one side of Schwab's expDateMap into a flat list of option dicts."""
        options = []
        for exp_key, strikes in exp_map.items():
            exp_date = exp_key.split(":")[0]
            if exp_date != target_date:
                continue
            for strike_str, contracts in strikes.items():
                for c in contracts:
                    options.append({
                        "strike":            _safe_float(c.get("strikePrice")),
                        "bid":               _safe_float(c.get("bid")),
                        "ask":               _safe_float(c.get("ask")),
                        "last":              _safe_float(c.get("last")),
                        "volume":            _safe_int(c.get("totalVolume")),
                        "openInterest":      _safe_int(c.get("openInterest")),
                        "impliedVolatility": _safe_float(c.get("volatility")) / 100
                                             if c.get("volatility") else None,
                        "delta":  c.get("delta"),
                        "theta":  c.get("theta"),
                        "gamma":  c.get("gamma"),
                        "vega":   c.get("vega"),
                    })
        return options
