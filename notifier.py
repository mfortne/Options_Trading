"""
Telegram notifier for options scan results
Credentials loaded from .env file — never hardcoded

Outbound:
    send_message()         — generic message
    build_scan_summary()   — scan results formatter
    notify_error()         — error alert
    notify_startup()       — startup confirmation
    send_trade_alert()     — pending trade waiting for approval

Inbound:
    listen_for_replies()   — polls for approve/reject replies
    parse_reply()          — extracts action + trade_id from reply text
"""

import os
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

OFFSET_FILE = "telegram_offset.json"   # Tracks last processed Telegram update ID


# ---------------------------------------------------------------------------
# Offset persistence (prevents re-processing old messages)
# ---------------------------------------------------------------------------

def _load_offset() -> int:
    """Load last processed Telegram update ID from disk."""
    if Path(OFFSET_FILE).exists():
        try:
            with open(OFFSET_FILE, "r") as f:
                return json.load(f).get("offset", 0)
        except (json.JSONDecodeError, KeyError):
            pass
    return 0


def _save_offset(offset: int):
    """Save last processed Telegram update ID to disk."""
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset}, f)


# ---------------------------------------------------------------------------
# Existing outbound functions (unchanged)
# ---------------------------------------------------------------------------

def send_message(text: str) -> bool:
    """
    Send a plain text message to your Telegram bot.

    Args:
        text: Message to send (Markdown supported)

    Returns:
        True if sent successfully, False otherwise
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("[Telegram] Not configured — skipping send.")
        print(f"[Telegram] Message would have been:\n{text}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        print("[Telegram] Message sent successfully.")
        return True
    except requests.RequestException as e:
        print(f"[Telegram] Failed to send message: {e}")
        return False


def build_scan_summary(symbol: str,
                       current_price: float,
                       eligible_puts: list,
                       eligible_calls: list,
                       portfolio_name: str = "small") -> str:
    """
    Build a concise Telegram summary message from scan results.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"📊 *Options Scan — {symbol}*",
        f"🕐 {now}  |  Portfolio: `{portfolio_name}`",
        f"💵 Underlying price: *${current_price:.2f}*",
        "",
    ]

    if eligible_puts:
        lines.append(f"✅ *{len(eligible_puts)} eligible PUT(s) to sell:*")
        for put in sorted(eligible_puts, key=lambda x: x.bid, reverse=True)[:3]:
            lines.append(
                f"  • Strike ${put.strike:.0f} | Bid ${put.bid:.2f} "
                f"| Δ {put.delta:.2f} | Spread ${put.bid_ask_spread:.2f}"
            )
    else:
        lines.append("❌ No eligible puts found")

    lines.append("")

    if eligible_calls:
        lines.append(f"✅ *{len(eligible_calls)} eligible CALL(s) to sell:*")
        for call in sorted(eligible_calls, key=lambda x: x.bid, reverse=True)[:3]:
            lines.append(
                f"  • Strike ${call.strike:.0f} | Bid ${call.bid:.2f} "
                f"| Δ {call.delta:.2f} | Spread ${call.bid_ask_spread:.2f}"
            )
    else:
        lines.append("❌ No eligible calls found")

    lines.append("")
    lines.append("_Options Trading Bot — Paper Trading Only_")

    return "\n".join(lines)


def notify_error(error_msg: str) -> bool:
    """Send an error alert to Telegram."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = f"⚠️ *Options Bot Error*\n🕐 {now}\n\n`{error_msg}`"
    return send_message(text)


def notify_startup() -> bool:
    """Send a startup confirmation message."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = f"🚀 *Options Bot Started*\n🕐 {now}\nScheduled scan is running..."
    return send_message(text)


# ---------------------------------------------------------------------------
# New: Trade alert (outbound)
# ---------------------------------------------------------------------------

def send_trade_alert(trade: dict) -> bool:
    """
    Send a pending trade alert to Telegram asking for approval.

    The message clearly shows the trade ID and exact reply format
    so you can approve or reject from your phone.

    Args:
        trade: Pending trade dict from PaperPortfolioManager.add_pending_trade()

    Returns:
        True if sent successfully
    """
    t = trade
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"🔔 *New Trade Opportunity*",
        f"🕐 {now}  |  Portfolio: `{t['portfolio_name']}`",
        f"",
        f"*{t['symbol']}* — {t['strategy']} ({t['option_type']})",
        f"Strike:      ${t['strike']:.0f}",
        f"Expiration:  {t['expiration_date']}  ({t['dte']} DTE)",
        f"Bid:         ${t['bid']:.2f}  per share",
        f"Delta:       {t['delta']:.2f}",
        f"Spread:      ${t['spread']:.2f}",
        f"",
        f"Capital required: ${t['capital_required']:,.0f}",
        f"Take profit at:   ${t['take_profit_at']:.2f}  (50%)",
        f"Stop loss at:     ${t['stop_loss_at']:.2f}  (30%)",
        f"",
        f"Trade ID: `{t['trade_id']}`",
        f"",
        f"Reply with:",
        f"  `approve {t['trade_id']}`",
        f"  `reject {t['trade_id']}`",
        f"",
        f"_Expires in 10 minutes if no reply._",
    ]

    return send_message("\n".join(lines))


# ---------------------------------------------------------------------------
# New: Reply listener (inbound polling)
# ---------------------------------------------------------------------------

def parse_reply(text: str):
    """
    Parse an approve/reject reply from Telegram.

    Expected formats (case-insensitive):
        approve ABC12345
        reject  ABC12345

    Args:
        text: Raw message text from Telegram

    Returns:
        (action, trade_id) tuple, e.g. ("approve", "ABC12345")
        Returns (None, None) if message doesn't match expected format
    """
    if not text:
        return None, None

    parts = text.strip().lower().split()
    if len(parts) < 2:
        return None, None

    action = parts[0]
    trade_id = parts[1].upper()

    if action not in ("approve", "reject"):
        return None, None

    return action, trade_id


def listen_for_replies(timeout_seconds: int = 600,
                        poll_interval: int = 5) -> tuple:
    """
    Poll Telegram for approve/reject replies until one arrives or timeout.

    Ignores messages from anyone other than your configured chat ID
    so random users can't manipulate your trades.

    Args:
        timeout_seconds: How long to wait before giving up (default 10 min)
        poll_interval:   Seconds between each poll (default 5s)

    Returns:
        (action, trade_id) e.g. ("approve", "ABC12345")
        Returns (None, None) on timeout or error
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("[Telegram] Not configured — cannot listen for replies.")
        return None, None

    url    = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    offset = _load_offset()
    elapsed = 0

    print(f"[Telegram] Listening for reply (timeout: {timeout_seconds}s)...")

    while elapsed < timeout_seconds:
        try:
            resp = requests.get(url, params={"offset": offset, "timeout": poll_interval}, timeout=15)
            resp.raise_for_status()
            updates = resp.json().get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                _save_offset(offset)

                message = update.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                text    = message.get("text", "")

                # Only accept messages from your own chat ID
                if chat_id != str(TELEGRAM_CHAT_ID):
                    continue

                action, trade_id = parse_reply(text)
                if action and trade_id:
                    print(f"[Telegram] Received: {action} {trade_id}")
                    return action, trade_id

        except requests.RequestException as e:
            print(f"[Telegram] Poll error: {e}")

        time.sleep(poll_interval)
        elapsed += poll_interval

    print(f"[Telegram] Timeout — no reply received after {timeout_seconds}s.")
    return None, None


def listen_for_any_replies() -> list:
    """
    Non-blocking — drain all pending replies in one shot.
    Returns a list of (action, trade_id) tuples for all pending replies.

    Use this in the main scan loop to process approvals that arrived
    while the bot was busy scanning other symbols.
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        return []

    url    = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    offset = _load_offset()
    results = []

    try:
        resp = requests.get(url, params={"offset": offset, "timeout": 1}, timeout=10)
        resp.raise_for_status()
        updates = resp.json().get("result", [])

        for update in updates:
            offset = update["update_id"] + 1
            _save_offset(offset)

            message = update.get("message", {})
            chat_id = str(message.get("chat", {}).get("id", ""))
            text    = message.get("text", "")

            if chat_id != str(TELEGRAM_CHAT_ID):
                continue

            action, trade_id = parse_reply(text)
            if action and trade_id:
                results.append((action, trade_id))

    except requests.RequestException as e:
        print(f"[Telegram] Poll error: {e}")

    return results
