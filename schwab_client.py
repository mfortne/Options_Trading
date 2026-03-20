"""
Charles Schwab API client for options data
Drop-in replacement for finnhub_client.py using the schwab-py library.

Authentication flow:
  - First run  : opens browser for OAuth login → saves token to token_path
  - Subsequent : loads token from file; schwab-py auto-refreshes access tokens
                 (access token lasts 30 min, refresh token lasts 7 days)
  - Headless   : set SCHWAB_HEADLESS=1 env var to use manual-flow (prints URL,
                 paste into any browser, paste back the redirect URL)

Setup:
  1. pip install schwab-py
  2. Register app at https://developer.schwab.com → get api_key + app_secret
  3. Set callback_url to https://127.0.0.1:8182 (or whatever you registered)
  4. Fill in portfolio_config.json → api section (see example in that file)
  5. Run once interactively to complete OAuth; token is saved for future use

Public methods (same signatures/return shapes as FinnhubClient):
  get_quote(symbol)                  → dict
  get_option_expirations(symbol)     → list[str]
  get_option_chain(symbol, date)     → dict  (Finnhub-compatible shape)
  fetch_options_chain(symbol, date)  → OptionsChain | None
  get_rate_limit_remaining()         → int
  wait_if_rate_limited()             → None
"""

import os
import time
import httpx
from datetime import datetime, date
from typing import Optional, Dict, Any, List

from models import OptionChainData, OptionsChain, OptionType

try:
    import schwab
    from schwab import auth as schwab_auth
except ImportError:
    raise ImportError(
        "schwab-py is not installed. Run: pip install schwab-py"
    )


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


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class SchwabClient:
    """
    Schwab Trader API wrapper with the same public interface as FinnhubClient.

    Parameters
    ----------
    api_key        : Schwab app key (consumer key)
    app_secret     : Schwab app secret
    callback_url   : Must match exactly what is registered in the developer portal
                     (default: https://127.0.0.1:8182)
    token_path     : Path to the persisted OAuth token JSON file
    """

    # Schwab rate limit: ~120 market-data requests per minute
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

        self._request_count = 0          # requests this minute
        self._minute_start = time.time()  # when the current rate-window started
        self._client = self._build_client()

    # ------------------------------------------------------------------
    # Client / Auth
    # ------------------------------------------------------------------

    def _build_client(self):
        """
        Return an authenticated schwab-py client.
        
        Priority:
          1. Existing token file  → client_from_token_file (auto-refresh)
          2. SCHWAB_HEADLESS env  → client_from_manual_flow (no browser needed)
          3. Otherwise            → easy_client (opens browser automatically)
        """
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
                print(f"[SchwabClient] Token file invalid ({exc}); re-authenticating…")

        if os.environ.get("SCHWAB_HEADLESS"):
            print("[SchwabClient] Headless mode: follow the URL printed below.")
            client = schwab_auth.client_from_manual_flow(
                api_key=self.api_key,
                app_secret=self.app_secret,
                callback_url=self.callback_url,
                token_path=self.token_path,
            )
        else:
            print("[SchwabClient] Opening browser for OAuth login…")
            client = schwab_auth.easy_client(
                api_key=self.api_key,
                app_secret=self.app_secret,
                callback_url=self.callback_url,
                token_path=self.token_path,
            )

        print(f"[SchwabClient] Token saved to {self.token_path}")
        return client

    # ------------------------------------------------------------------
    # Rate-limit helpers (mirrors FinnhubClient interface)
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
                print(f"[SchwabClient] Rate limit close; waiting {wait:.0f}s…")
                time.sleep(wait)
            self._request_count = 0
            self._minute_start = time.time()

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------

    def get_quote(self, symbol: str) -> Dict[str, float]:
        """
        Fetch current stock quote.

        Returns dict with keys:
            current_price, high, low, open, previous_close
        Raises ValueError for invalid symbols or missing data.
        """
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

        # Schwab returns { "AAPL": { "quote": {...}, "reference": {...} } }
        ticker_data = data.get(symbol, {})
        quote = ticker_data.get("quote", {})

        current_price = _safe_float(quote.get("lastPrice") or quote.get("mark"))
        if current_price == 0:
            raise ValueError(f"No quote data available for symbol: {symbol}")

        return {
            "current_price": current_price,
            "high":          _safe_float(quote.get("highPrice")),
            "low":           _safe_float(quote.get("lowPrice")),
            "open":          _safe_float(quote.get("openPrice")),
            "previous_close": _safe_float(quote.get("closePrice")),
        }

    # ------------------------------------------------------------------
    # Option expirations
    # ------------------------------------------------------------------

    def get_option_expirations(self, symbol: str) -> List[str]:
        """
        Return sorted list of available option expiration dates (YYYY-MM-DD).
        Fetches the full chain once (no strikes, just to collect expirations).
        """
        self.wait_if_rate_limited()
        self._track_request()

        resp = self._client.get_option_chain(
            symbol,
            include_underlying_quote=False,
        )
        resp.raise_for_status()
        data = resp.json()

        expirations: set[str] = set()

        for side in ("callExpDateMap", "putExpDateMap"):
            for exp_key in data.get(side, {}).keys():
                # Keys look like "2025-01-17:29"  (date:DTE)
                exp_date = exp_key.split(":")[0]
                expirations.add(exp_date)

        return sorted(expirations)

    # ------------------------------------------------------------------
    # Raw option chain (Finnhub-compatible output shape)
    # ------------------------------------------------------------------

    def get_option_chain(self, symbol: str, expiration_date: str) -> Dict[str, Any]:
        """
        Fetch raw option chain for one expiration and return a dict shaped like
        Finnhub's response so the rest of the codebase (models, cache) stays unchanged.

        Finnhub shape used downstream:
            {
              "call": [ {strike, bid, ask, last, volume, openInterest,
                         impliedVolatility, delta, theta, gamma, vega}, ... ],
              "put":  [ ... ]
            }
        """
        self.wait_if_rate_limited()
        self._track_request()

        # Parse expiration into a date object for the API filter
        try:
            exp_dt = datetime.strptime(expiration_date, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"expiration_date must be YYYY-MM-DD, got: {expiration_date!r}")

        resp = self._client.get_option_chain(
            symbol,
            from_date=exp_dt,
            to_date=exp_dt,
            include_underlying_quote=True,
        )
        resp.raise_for_status()
        raw = resp.json()

        calls = self._parse_side(raw.get("callExpDateMap", {}), expiration_date)
        puts  = self._parse_side(raw.get("putExpDateMap", {}),  expiration_date)

        return {"call": calls, "put": puts, "callExpired": [], "putExpired": []}

    @staticmethod
    def _parse_side(exp_map: dict, target_date: str) -> List[Dict[str, Any]]:
        """
        Convert one side of Schwab's callExpDateMap / putExpDateMap into a flat list
        of option dicts matching Finnhub's field names.
        """
        options = []
        for exp_key, strikes in exp_map.items():
            exp_date = exp_key.split(":")[0]
            if exp_date != target_date:
                continue
            for strike_str, contracts in strikes.items():
                for c in contracts:
                    options.append({
                        "strike":          _safe_float(c.get("strikePrice")),
                        "bid":             _safe_float(c.get("bid")),
                        "ask":             _safe_float(c.get("ask")),
                        "last":            _safe_float(c.get("last")),
                        "volume":          _safe_int(c.get("totalVolume")),
                        "openInterest":    _safe_int(c.get("openInterest")),
                        "impliedVolatility": _safe_float(c.get("volatility")) / 100
                                             if c.get("volatility") else None,
                        "delta":           c.get("delta"),   # keep None if absent
                        "theta":           c.get("theta"),
                        "gamma":           c.get("gamma"),
                        "vega":            c.get("vega"),
                    })
        return options

    # ------------------------------------------------------------------
    # High-level: fetch + parse into OptionsChain model
    # ------------------------------------------------------------------

    def fetch_options_chain(
        self,
        symbol: str,
        expiration_date: Optional[str] = None,
    ) -> Optional[OptionsChain]:
        """
        Fetch and parse a complete options chain for one symbol/expiration.
        Identical return type to FinnhubClient.fetch_options_chain().
        """
        try:
            quote = self.get_quote(symbol)
            current_price = quote["current_price"]

            expirations = self.get_option_expirations(symbol)
            if not expirations:
                print(f"[SchwabClient] No option expirations found for {symbol}")
                return None

            if expiration_date is None:
                expiration_date = expirations[0]
            elif expiration_date not in expirations:
                print(f"[SchwabClient] Expiration {expiration_date} not available for {symbol}")
                return None

            raw_chain = self.get_option_chain(symbol, expiration_date)

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

            for call_data in raw_chain.get("callExpired", []) + raw_chain.get("call", []):
                opt = _build_option(call_data, OptionType.CALL)
                if opt:
                    options_chain.calls.append(opt)

            for put_data in raw_chain.get("putExpired", []) + raw_chain.get("put", []):
                opt = _build_option(put_data, OptionType.PUT)
                if opt:
                    options_chain.puts.append(opt)

            return options_chain

        except Exception as exc:
            print(f"[SchwabClient] Error fetching options chain for {symbol}: {exc}")
            return None
