"""Telegram notifications for trade events."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from bot.config import settings

log = logging.getLogger(__name__)

# Telegram settings are stored in app_settings DB table
_telegram_bot_token: str = ""
_telegram_chat_id: str = ""
_enabled: bool = False


async def load_telegram_settings() -> None:
    """Load Telegram settings from the database."""
    global _telegram_bot_token, _telegram_chat_id, _enabled

    from sqlalchemy import select

    from bot.db.models import AppSetting
    from bot.db.session import async_session_factory
    from dashboard.api.auth.crypto import decrypt

    async with async_session_factory() as session:
        result = await session.execute(
            select(AppSetting).where(AppSetting.key.in_(["telegram_bot_token", "telegram_chat_id"]))
        )
        rows = {r.key: r for r in result.scalars().all()}

    token_row = rows.get("telegram_bot_token")
    chat_row = rows.get("telegram_chat_id")

    if token_row and token_row.value:
        _telegram_bot_token = decrypt(token_row.value) if token_row.encrypted else token_row.value
    if chat_row and chat_row.value:
        _telegram_chat_id = chat_row.value

    _enabled = bool(_telegram_bot_token and _telegram_chat_id)
    if _enabled:
        log.info("Telegram notifications enabled")
    else:
        log.info("Telegram notifications disabled (missing token or chat_id)")


async def send_message(text: str) -> bool:
    """Send a message via Telegram Bot API."""
    if not _enabled:
        return False

    url = f"https://api.telegram.org/bot{_telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": _telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return True
            log.warning("Telegram send failed: %s %s", resp.status_code, resp.text)
    except Exception as e:
        log.warning("Telegram send error: %s", e)
    return False


async def notify_trade_opened(
    epic: str,
    direction: str,
    size: float,
    strategy: str,
    deal_id: str,
) -> None:
    """Notify when a new trade is opened."""
    emoji = "\u2b06\ufe0f" if direction == "BUY" else "\u2b07\ufe0f"
    text = (
        f"{emoji} <b>Trade Opened</b>\n"
        f"Epic: <code>{epic}</code>\n"
        f"Direction: {direction} | Size: {size}\n"
        f"Strategy: {strategy}\n"
        f"Deal: <code>{deal_id}</code>"
    )
    await send_message(text)


async def notify_trade_closed(
    epic: str,
    direction: str,
    profit: float,
    strategy: str,
    deal_id: str,
) -> None:
    """Notify when a trade is closed."""
    emoji = "\u2705" if profit >= 0 else "\u274c"
    sign = "+" if profit >= 0 else ""
    text = (
        f"{emoji} <b>Trade Closed</b>\n"
        f"Epic: <code>{epic}</code>\n"
        f"Direction: {direction} | P&L: <b>{sign}{profit:.2f}</b>\n"
        f"Strategy: {strategy}\n"
        f"Deal: <code>{deal_id}</code>"
    )
    await send_message(text)


async def notify_bot_status(status: str, detail: str = "") -> None:
    """Notify on bot status changes."""
    icons = {"running": "\u25b6\ufe0f", "stopped": "\u23f9\ufe0f", "error": "\u26a0\ufe0f"}
    icon = icons.get(status, "\u2139\ufe0f")
    text = f"{icon} <b>Bot {status.upper()}</b>"
    if detail:
        text += f"\n{detail}"
    await send_message(text)


async def notify_autopilot_activation(epic: str, strategy: str, score: float, regime: str) -> None:
    """Notify when autopilot activates a new market strategy."""
    text = (
        f"\U0001f916 <b>Autopilot Activated</b>\n"
        f"Market: <code>{epic}</code>\n"
        f"Strategy: {strategy}\n"
        f"Score: {score:.0%} | Regime: {regime}"
    )
    await send_message(text)


async def notify_autopilot_scan(active: int, scored: int, qualified: int) -> None:
    """Notify scan cycle summary."""
    text = (
        f"\U0001f50d <b>Autopilot Scan</b>\n"
        f"Scored: {scored} | Qualified: {qualified} | Active: {active}"
    )
    await send_message(text)


async def notify_ai_decision(epic: str, verdict: str, reasoning: str, strategy: str) -> None:
    """Notify when AI validates or rejects a trade."""
    icons = {"approve": "\u2705", "adjust": "\u2699\ufe0f", "reject": "\u274c"}
    icon = icons.get(verdict.lower(), "\U0001f916")
    text = (
        f"{icon} <b>AI {verdict.upper()}</b>\n"
        f"Epic: <code>{epic}</code>\n"
        f"Strategy: {strategy}\n"
        f"Reason: {reasoning[:200]}"
    )
    await send_message(text)


async def notify_drawdown_warning(daily_pnl: float, limit: float, pct_used: float) -> None:
    """Notify when drawdown reaches 50% or 80% of the daily limit."""
    if pct_used >= 80:
        icon = "\U0001f534"
        level = "CRITICAL"
    else:
        icon = "\U0001f7e1"
        level = "WARNING"
    text = (
        f"{icon} <b>Drawdown {level}</b>\n"
        f"Daily P&L: <b>{daily_pnl:.2f}</b>\n"
        f"Limit: -{limit:.0f} ({pct_used:.0f}% consumed)"
    )
    await send_message(text)


async def notify_trailing_stop_breakeven(deal_id: str, epic: str) -> None:
    """Notify when a position moves to breakeven."""
    text = (
        f"\U0001f512 <b>Breakeven Activated</b>\n"
        f"Epic: <code>{epic}</code>\n"
        f"Deal: <code>{deal_id}</code>\n"
        f"Stop moved to entry price"
    )
    await send_message(text)
