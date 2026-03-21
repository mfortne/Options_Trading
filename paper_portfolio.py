"""
Paper Portfolio Manager
Persists open positions, pending trades, and trade history to paper_portfolio.json.
Survives restarts — all state is saved to disk after every change.

Usage:
    pm = PaperPortfolioManager()
    pm.add_pending_trade(trade_data)   # Queue a trade for approval
    pm.approve_trade(trade_id)         # Open the position
    pm.reject_trade(trade_id)          # Discard it
    pm.close_position(position_id, exit_premium, reason)
    pm.get_open_positions()
    pm.get_summary()
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_FILE = "paper_portfolio.json"

TAKE_PROFIT_PCT = 0.50   # Close when premium drops 50%
STOP_LOSS_PCT   = 0.30   # Close when loss reaches 30%


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_id() -> str:
    return str(uuid.uuid4())[:8].upper()


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class PaperPortfolioManager:
    """
    Manages paper trading state across restarts via JSON file.

    State structure:
    {
        "portfolios": {
            "small":  { "balance": 500,    "capital_used": 0 },
            "medium": { "balance": 50000,  "capital_used": 0 },
            "large":  { "balance": 200000, "capital_used": 0 }
        },
        "pending_trades": [ { ...trade_data... } ],
        "open_positions": [ { ...position_data... } ],
        "trade_history":  [ { ...closed_trade... } ]
    }
    """

    def __init__(self, state_file: str = STATE_FILE):
        self.state_file = Path(state_file)
        self.state = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        """Load state from disk, or create fresh state if file doesn't exist."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, KeyError):
                print(f"[PaperPortfolio] Corrupted state file — starting fresh.")

        return self._default_state()

    def _save(self):
        """Write current state to disk."""
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2, default=str)

    def _default_state(self) -> dict:
        return {
            "portfolios": {
                "small":  {"balance": 500,    "capital_used": 0.0},
                "medium": {"balance": 50000,  "capital_used": 0.0},
                "large":  {"balance": 200000, "capital_used": 0.0},
            },
            "pending_trades": [],
            "open_positions": [],
            "trade_history":  [],
        }

    # ------------------------------------------------------------------
    # Pending Trades (waiting for your approval)
    # ------------------------------------------------------------------

    def add_pending_trade(self,
                          symbol: str,
                          option_type: str,       # "PUT" or "CALL"
                          strike: float,
                          expiration_date: str,
                          dte: int,
                          bid: float,
                          delta: float,
                          spread: float,
                          current_price: float,
                          portfolio_name: str,
                          strategy: str = "CSP",  # "CSP" or "CC"
                          contracts: int = 1) -> dict:
        """
        Queue a trade opportunity for your approval.
        Returns the pending trade dict (includes trade_id for Telegram reply matching).
        """
        capital_required = strike * 100 * contracts if strategy == "CSP" else 0.0

        # Check if portfolio has capacity before queuing
        can_trade, reason = self._can_open(portfolio_name, capital_required)
        if not can_trade:
            print(f"[PaperPortfolio] Skipping {symbol} — {reason}")
            return {}

        trade = {
            "trade_id":        _new_id(),
            "status":          "PENDING",         # PENDING → APPROVED or REJECTED
            "queued_at":       _now_str(),
            "symbol":          symbol,
            "option_type":     option_type,
            "strike":          strike,
            "expiration_date": expiration_date,
            "dte":             dte,
            "bid":             bid,
            "delta":           delta,
            "spread":          spread,
            "current_price":   current_price,
            "portfolio_name":  portfolio_name,
            "strategy":        strategy,
            "contracts":       contracts,
            "capital_required": capital_required,
            "take_profit_at":  round(bid * (1 - TAKE_PROFIT_PCT), 2),
            "stop_loss_at":    round(bid * (1 + STOP_LOSS_PCT), 2),
        }

        self.state["pending_trades"].append(trade)
        self._save()

        print(f"[PaperPortfolio] Queued trade {trade['trade_id']} — "
              f"{symbol} ${strike} {option_type} exp {expiration_date}")
        return trade

    def get_pending_trades(self) -> list:
        return [t for t in self.state["pending_trades"] if t["status"] == "PENDING"]

    def get_pending_by_id(self, trade_id: str) -> Optional[dict]:
        for t in self.state["pending_trades"]:
            if t["trade_id"] == trade_id and t["status"] == "PENDING":
                return t
        return None

    # ------------------------------------------------------------------
    # Approve / Reject
    # ------------------------------------------------------------------

    def approve_trade(self, trade_id: str) -> Optional[dict]:
        """
        Approve a pending trade → opens it as a paper position.
        Returns the new position dict, or None if trade not found.
        """
        trade = self.get_pending_by_id(trade_id)
        if not trade:
            print(f"[PaperPortfolio] Trade {trade_id} not found or already resolved.")
            return None

        # Double-check capital still available (another trade may have been approved)
        can_trade, reason = self._can_open(trade["portfolio_name"], trade["capital_required"])
        if not can_trade:
            print(f"[PaperPortfolio] Cannot approve {trade_id} — {reason}")
            trade["status"] = "REJECTED"
            trade["rejected_reason"] = reason
            self._save()
            return None

        # Open the position
        position = {
            "position_id":     _new_id(),
            "trade_id":        trade_id,
            "symbol":          trade["symbol"],
            "option_type":     trade["option_type"],
            "strike":          trade["strike"],
            "expiration_date": trade["expiration_date"],
            "dte":             trade["dte"],
            "portfolio_name":  trade["portfolio_name"],
            "strategy":        trade["strategy"],
            "contracts":       trade["contracts"],
            "entry_date":      _now_str(),
            "entry_premium":   trade["bid"],
            "current_premium": trade["bid"],
            "current_price":   trade["current_price"],
            "capital_required": trade["capital_required"],
            "take_profit_at":  trade["take_profit_at"],
            "stop_loss_at":    trade["stop_loss_at"],
            "unrealized_pnl":  0.0,
            "unrealized_pnl_pct": 0.0,
            "status":          "OPEN",
        }

        # Deduct capital from portfolio
        self.state["portfolios"][trade["portfolio_name"]]["capital_used"] += trade["capital_required"]

        self.state["open_positions"].append(position)
        trade["status"] = "APPROVED"
        self._save()

        print(f"[PaperPortfolio] ✅ Opened position {position['position_id']} — "
              f"{position['symbol']} ${position['strike']} {position['option_type']}")
        return position

    def reject_trade(self, trade_id: str, reason: str = "User rejected"):
        """Reject a pending trade — discards it, no position opened."""
        trade = self.get_pending_by_id(trade_id)
        if not trade:
            return
        trade["status"] = "REJECTED"
        trade["rejected_reason"] = reason
        self._save()
        print(f"[PaperPortfolio] ❌ Rejected trade {trade_id} — {reason}")

    def expire_pending_trades(self, max_age_minutes: int = 10):
        """
        Auto-reject pending trades older than max_age_minutes.
        Call this at the start of each scan to clean up stale approvals.
        """
        now = datetime.now()
        for trade in self.state["pending_trades"]:
            if trade["status"] != "PENDING":
                continue
            queued = datetime.strptime(trade["queued_at"], "%Y-%m-%d %H:%M:%S")
            age_minutes = (now - queued).total_seconds() / 60
            if age_minutes > max_age_minutes:
                trade["status"] = "EXPIRED"
                print(f"[PaperPortfolio] ⏰ Expired trade {trade['trade_id']} "
                      f"({age_minutes:.0f} min old)")
        self._save()

    # ------------------------------------------------------------------
    # Open Positions
    # ------------------------------------------------------------------

    def get_open_positions(self) -> list:
        return [p for p in self.state["open_positions"] if p["status"] == "OPEN"]

    def get_position_by_id(self, position_id: str) -> Optional[dict]:
        for p in self.state["open_positions"]:
            if p["position_id"] == position_id and p["status"] == "OPEN":
                return p
        return None

    def update_position_price(self, position_id: str,
                               current_premium: float,
                               current_price: float,
                               new_dte: int):
        """Re-price an open position with latest market data."""
        pos = self.get_position_by_id(position_id)
        if not pos:
            return

        pos["current_premium"] = current_premium
        pos["current_price"]   = current_price
        pos["dte"]             = new_dte

        credit        = pos["entry_premium"] * pos["contracts"] * 100
        cost_to_close = current_premium * pos["contracts"] * 100
        pos["unrealized_pnl"]     = round(credit - cost_to_close, 2)
        pos["unrealized_pnl_pct"] = round((pos["unrealized_pnl"] / credit) * 100, 2) if credit else 0

        self._save()

    def check_exit_signals(self) -> list:
        """
        Check all open positions for take-profit or stop-loss triggers.
        Returns list of dicts: { position, signal }
        signal is 'TAKE_PROFIT' or 'STOP_LOSS'
        """
        signals = []
        for pos in self.get_open_positions():
            if pos["current_premium"] <= pos["take_profit_at"]:
                signals.append({"position": pos, "signal": "TAKE_PROFIT"})
            elif pos["current_premium"] >= pos["stop_loss_at"]:
                signals.append({"position": pos, "signal": "STOP_LOSS"})
        return signals

    def close_position(self, position_id: str,
                        exit_premium: float,
                        reason: str = "Manual") -> Optional[dict]:
        """
        Close an open position and move it to trade history.
        Returns the closed trade record.
        """
        pos = self.get_position_by_id(position_id)
        if not pos:
            print(f"[PaperPortfolio] Position {position_id} not found.")
            return None

        credit        = pos["entry_premium"] * pos["contracts"] * 100
        cost_to_close = exit_premium * pos["contracts"] * 100
        pnl           = round(credit - cost_to_close, 2)
        pnl_pct       = round((pnl / credit) * 100, 2) if credit else 0

        entry_date = datetime.strptime(pos["entry_date"], "%Y-%m-%d %H:%M:%S")
        days_held  = (datetime.now() - entry_date).days

        closed_trade = {
            **pos,
            "status":        "CLOSED",
            "exit_date":     _now_str(),
            "exit_premium":  exit_premium,
            "close_reason":  reason,
            "realized_pnl":  pnl,
            "realized_pnl_pct": pnl_pct,
            "days_held":     days_held,
        }

        # Free up capital
        portfolio = self.state["portfolios"].get(pos["portfolio_name"])
        if portfolio:
            portfolio["capital_used"] = max(
                0, portfolio["capital_used"] - pos["capital_required"]
            )

        pos["status"] = "CLOSED"
        self.state["trade_history"].append(closed_trade)
        self._save()

        emoji = "✅" if pnl >= 0 else "🔴"
        print(f"[PaperPortfolio] {emoji} Closed {position_id} — "
              f"P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%) | Reason: {reason}")
        return closed_trade

    # ------------------------------------------------------------------
    # Portfolio Checks
    # ------------------------------------------------------------------

    def _can_open(self, portfolio_name: str, capital_required: float) -> tuple:
        """Check if a portfolio can absorb a new position."""
        portfolio = self.state["portfolios"].get(portfolio_name)
        if not portfolio:
            return False, f"Unknown portfolio: {portfolio_name}"

        available = portfolio["balance"] - portfolio["capital_used"]
        if capital_required > available:
            return False, (f"Insufficient capital — need ${capital_required:.0f}, "
                           f"available ${available:.0f}")

        # Count open positions for this portfolio
        open_count = sum(
            1 for p in self.get_open_positions()
            if p["portfolio_name"] == portfolio_name
        )

        # Max positions per portfolio
        max_positions = {"small": 1, "medium": 2, "large": 5}
        limit = max_positions.get(portfolio_name, 1)
        if open_count >= limit:
            return False, f"Max positions reached ({open_count}/{limit})"

        return True, ""

    # ------------------------------------------------------------------
    # Summary / Reporting
    # ------------------------------------------------------------------

    def get_summary(self) -> dict:
        """
        Return a summary dict for display or Telegram notification.
        """
        open_positions = self.get_open_positions()
        history        = self.state["trade_history"]

        total_realized   = sum(t.get("realized_pnl", 0) for t in history)
        total_unrealized = sum(p.get("unrealized_pnl", 0) for p in open_positions)

        wins  = [t for t in history if t.get("realized_pnl", 0) > 0]
        loses = [t for t in history if t.get("realized_pnl", 0) < 0]

        return {
            "open_positions":    len(open_positions),
            "closed_trades":     len(history),
            "total_realized":    round(total_realized, 2),
            "total_unrealized":  round(total_unrealized, 2),
            "total_pnl":         round(total_realized + total_unrealized, 2),
            "win_count":         len(wins),
            "loss_count":        len(loses),
            "win_rate":          round(len(wins) / len(history) * 100, 1) if history else 0,
            "positions":         open_positions,
        }

    def format_summary_message(self) -> str:
        """Format summary as a Telegram-ready message."""
        s = self.get_summary()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        lines = [
            f"📋 *Paper Portfolio Summary*",
            f"🕐 {now}",
            f"",
            f"Open positions:  {s['open_positions']}",
            f"Closed trades:   {s['closed_trades']}",
            f"Win rate:        {s['win_rate']}%  ({s['win_count']}W / {s['loss_count']}L)",
            f"",
            f"Realized P&L:    ${s['total_realized']:+.2f}",
            f"Unrealized P&L:  ${s['total_unrealized']:+.2f}",
            f"Total P&L:       ${s['total_pnl']:+.2f}",
        ]

        if s["positions"]:
            lines.append("")
            lines.append("*Open Positions:*")
            for p in s["positions"]:
                pnl_emoji = "✅" if p["unrealized_pnl"] >= 0 else "🔴"
                lines.append(
                    f"  {pnl_emoji} {p['symbol']} ${p['strike']} {p['option_type']} "
                    f"exp {p['expiration_date']} | "
                    f"P&L ${p['unrealized_pnl']:+.2f} ({p['unrealized_pnl_pct']:+.1f}%)"
                )

        return "\n".join(lines)
