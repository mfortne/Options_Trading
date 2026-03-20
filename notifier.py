"""
Telegram notifier for options scan results
Credentials loaded from .env file — never hardcoded
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # loads .env from the project root

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")


def send_message(text: str) -> bool:
    """
    Send a plain text message to your Telegram bot.

    Args:
        text: Message to send (Markdown supported)

    Returns:
        True if sent successfully, False otherwise
    """
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
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

    Args:
        symbol: Stock symbol scanned
        current_price: Current stock price
        eligible_puts: List of eligible put options
        eligible_calls: List of eligible call options
        portfolio_name: Which portfolio was scanned

    Returns:
        Formatted string ready to send
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"📊 *Options Scan — {symbol}*",
        f"🕐 {now}  |  Portfolio: `{portfolio_name}`",
        f"💵 Underlying price: *${current_price:.2f}*",
        "",
    ]

    # --- Puts ---
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

    # --- Calls ---
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
