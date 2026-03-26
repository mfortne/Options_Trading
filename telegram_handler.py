"""
Telegram Handler — controls the paper trading bot via Telegram commands.

Run this in a separate terminal (always-on):
    python3 telegram_handler.py

Commands:
    /approve TRADEID       — Open a pending paper position
    /reject TRADEID        — Discard a pending trade
    /close POSITIONID PREMIUM — Close an open position with P&L
    /positions             — List all open positions with live P&L
    /summary               — Full portfolio summary (win rate, total P&L)
    /pending               — List trades waiting for approval
    /help                  — Show all commands

Exit signal alerts are sent automatically when a position hits
take-profit (50%) or stop-loss (30%) thresholds.
The bot does NOT auto-close — it alerts you and waits for /close.
"""

import os
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from paper_portfolio import PaperPortfolioManager

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env")

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ---------------------------------------------------------------------------
# Telegram API helpers
# ---------------------------------------------------------------------------

def send(text: str):
    """Send a plain message to your Telegram chat."""
    try:
        requests.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        print(f"[Telegram] Send error: {e}")


def get_updates(offset: int) -> list:
    """Poll for new messages since offset."""
    try:
        resp = requests.get(
            f"{BASE_URL}/getUpdates",
            params={"offset": offset, "timeout": 10},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])
    except Exception as e:
        print(f"[Telegram] Poll error: {e}")
        return []


def get_latest_update_id() -> int:
    """Get the current highest update_id so we skip stale messages on startup."""
    updates = get_updates(offset=-1)
    if updates:
        return updates[-1]["update_id"]
    return 0

# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

pm = PaperPortfolioManager()


def handle_approve(args: list):
    if not args:
        send("Usage: `/approve TRADEID`")
        return
    trade_id = args[0].upper()
    position = pm.approve_trade(trade_id)
    if position:
        send(
            f"✅ *Position Opened*\n"
            f"ID: `{position['position_id']}`\n"
            f"Symbol: {position['symbol']} ${position['strike']} {position['option_type']}\n"
            f"Expiry: {position['expiration_date']}  |  DTE: {position['dte']}\n"
            f"Entry premium: ${position['entry_premium']:.2f}\n"
            f"Take profit at: ${position['take_profit_at']:.2f}  "
            f"Stop loss at: ${position['stop_loss_at']:.2f}\n"
            f"Capital reserved: ${position['capital_required']:.0f}"
        )
    else:
        send(f"❌ Could not approve `{trade_id}` — not found, already resolved, or insufficient capital.")


def handle_reject(args: list):
    if not args:
        send("Usage: `/reject TRADEID`")
        return
    trade_id = args[0].upper()
    pm.reject_trade(trade_id, reason="User rejected via Telegram")
    send(f"❌ Trade `{trade_id}` rejected.")


def handle_close(args: list):
    if len(args) < 2:
        send("Usage: `/close POSITIONID PREMIUM`\nExample: `/close AB12CD34 0.15`")
        return
    position_id  = args[0].upper()
    try:
        exit_premium = float(args[1])
    except ValueError:
        send("❌ Premium must be a number. Example: `/close AB12CD34 0.15`")
        return

    closed = pm.close_position(position_id, exit_premium, reason="Manual close via Telegram")
    if closed:
        pnl        = closed["realized_pnl"]
        pnl_pct    = closed["realized_pnl_pct"]
        days_held  = closed.get("days_held", "?")
        emoji      = "✅" if pnl >= 0 else "🔴"
        send(
            f"{emoji} *Position Closed*\n"
            f"ID: `{position_id}`\n"
            f"Symbol: {closed['symbol']} ${closed['strike']} {closed['option_type']}\n"
            f"Entry: ${closed['entry_premium']:.2f}  →  Exit: ${exit_premium:.2f}\n"
            f"Realized P&L: *${pnl:+.2f}* ({pnl_pct:+.1f}%)\n"
            f"Days held: {days_held}\n"
            f"Reason: {closed['close_reason']}"
        )
    else:
        send(f"❌ Position `{position_id}` not found or already closed.")


def handle_positions(_args: list):
    positions = pm.get_open_positions()
    if not positions:
        send("📭 No open positions.")
        return

    lines = [f"📋 *Open Positions ({len(positions)})*\n"]
    for p in positions:
        pnl       = p.get("unrealized_pnl", 0)
        pnl_pct   = p.get("unrealized_pnl_pct", 0)
        emoji     = "✅" if pnl >= 0 else "🔴"
        tp_dist   = p["current_premium"] - p["take_profit_at"]
        sl_dist   = p["stop_loss_at"] - p["current_premium"]
        lines.append(
            f"{emoji} `{p['position_id']}` — *{p['symbol']}* ${p['strike']} {p['option_type']}\n"
            f"   Portfolio: {p['portfolio_name']}  |  Expiry: {p['expiration_date']}  |  DTE: {p['dte']}\n"
            f"   Entry: ${p['entry_premium']:.2f}  Current: ${p['current_premium']:.2f}\n"
            f"   Unrealized P&L: *${pnl:+.2f}* ({pnl_pct:+.1f}%)\n"
            f"   TP in: ${tp_dist:.2f}  |  SL in: ${sl_dist:.2f}\n"
        )
    send("\n".join(lines))


def handle_pending(_args: list):
    pending = pm.get_pending_trades()
    if not pending:
        send("📭 No pending trades.")
        return

    lines = [f"⏳ *Pending Trades ({len(pending)})*\n"]
    for t in pending:
        lines.append(
            f"`{t['trade_id']}` — *{t['symbol']}* ${t['strike']} {t['option_type']}\n"
            f"   Portfolio: {t['portfolio_name']}  |  Expiry: {t['expiration_date']}  |  DTE: {t['dte']}\n"
            f"   Bid: ${t['bid']:.2f}  Delta: {t['delta']:.2f}  Spread: ${t['spread']:.2f}\n"
            f"   Capital required: ${t['capital_required']:.0f}\n"
            f"   Queued: {t['queued_at']}\n"
            f"   → /approve {t['trade_id']}  or  /reject {t['trade_id']}\n"
        )
    send("\n".join(lines))


def handle_summary(_args: list):
    send(pm.format_summary_message())


def handle_help(_args: list):
    send(
        "*Options Bot Commands*\n\n"
        "/approve TRADEID — Open a pending paper position\n"
        "/reject TRADEID — Discard a pending trade\n"
        "/close POSITIONID PREMIUM — Close position with P&L\n"
        "/positions — List open positions with live P&L\n"
        "/pending — List trades waiting for approval\n"
        "/summary — Portfolio summary, win rate, total P&L\n"
        "/help — Show this message\n\n"
        "_Exit signals (TP/SL) are sent automatically each scan._"
    )


COMMANDS = {
    "/approve":   handle_approve,
    "/reject":    handle_reject,
    "/close":     handle_close,
    "/positions": handle_positions,
    "/pending":   handle_pending,
    "/summary":   handle_summary,
    "/help":      handle_help,
}

# ---------------------------------------------------------------------------
# Exit signal checker  (called once per poll loop)
# ---------------------------------------------------------------------------

_alerted_positions: set = set()   # Don't spam the same alert repeatedly


def check_and_alert_exit_signals():
    """
    Check open positions for TP/SL breaches.
    Sends a Telegram alert for each breach — does NOT auto-close.
    Alerts only once per position per breach to avoid spam.
    """
    signals = pm.check_exit_signals()
    for item in signals:
        pos    = item["position"]
        signal = item["signal"]
        key    = f"{pos['position_id']}:{signal}"

        if key in _alerted_positions:
            continue   # Already sent this alert

        _alerted_positions.add(key)

        if signal == "TAKE_PROFIT":
            emoji = "🎯"
            msg   = "Take Profit target hit!"
        else:
            emoji = "⚠️"
            msg   = "Stop Loss threshold reached!"

        pnl     = pos.get("unrealized_pnl", 0)
        pnl_pct = pos.get("unrealized_pnl_pct", 0)

        send(
            f"{emoji} *{msg}*\n"
            f"Position: `{pos['position_id']}`\n"
            f"Symbol: {pos['symbol']} ${pos['strike']} {pos['option_type']}\n"
            f"Entry: ${pos['entry_premium']:.2f}  Current: ${pos['current_premium']:.2f}\n"
            f"Unrealized P&L: *${pnl:+.2f}* ({pnl_pct:+.1f}%)\n\n"
            f"→ To close: `/close {pos['position_id']} {pos['current_premium']:.2f}`"
        )

# ---------------------------------------------------------------------------
# Main poll loop
# ---------------------------------------------------------------------------

def run():
    print("[TelegramHandler] Starting up...")

    # Skip any messages that arrived before we started
    offset = get_latest_update_id() + 1
    print(f"[TelegramHandler] Fast-forwarded to update_id {offset} — ignoring stale messages.")

    send("🤖 *Options Bot online*\nType /help to see available commands.")

    while True:
        try:
            updates = get_updates(offset)

            for update in updates:
                offset = update["update_id"] + 1

                message = update.get("message", {})
                text    = message.get("text", "").strip()
                chat_id = str(message.get("chat", {}).get("id", ""))

                # Only respond to your chat
                if chat_id != str(CHAT_ID):
                    continue

                if not text.startswith("/"):
                    continue

                parts   = text.split()
                command = parts[0].lower().split("@")[0]   # strip @botname if present
                args    = parts[1:]

                print(f"[TelegramHandler] Command: {command} {args}")

                handler = COMMANDS.get(command)
                if handler:
                    handler(args)
                else:
                    send(f"Unknown command: `{command}`\nType /help for the list.")

            # Check exit signals on every poll cycle
            check_and_alert_exit_signals()

            time.sleep(3)

        except KeyboardInterrupt:
            print("[TelegramHandler] Stopped.")
            send("🔴 Options bot offline.")
            break
        except Exception as e:
            print(f"[TelegramHandler] Unexpected error: {e}")
            time.sleep(10)


if __name__ == "__main__":
    run()
