"""Notification settings and test endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminUser, AppSetting
from dashboard.api.auth.crypto import decrypt
from dashboard.api.auth.jwt import get_current_user
from dashboard.api.deps import get_db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class TestRequest(BaseModel):
    bot_token: str = ""
    chat_id: str = ""


class TestResponse(BaseModel):
    success: bool
    message: str


@router.post("/test", response_model=TestResponse)
async def test_telegram(
    req: TestRequest,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Send a test message to Telegram."""
    import httpx

    bot_token = req.bot_token
    chat_id = req.chat_id

    # If token is "__stored__", fetch from DB
    if bot_token == "__stored__":
        result = await db.execute(
            select(AppSetting).where(AppSetting.key == "telegram_bot_token")
        )
        row = result.scalar_one_or_none()
        if not row or not row.value:
            return TestResponse(success=False, message="No stored bot token found")
        bot_token = decrypt(row.value) if row.encrypted else row.value

    if not bot_token or not chat_id:
        return TestResponse(success=False, message="Bot token and chat ID are required")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "\u2705 <b>Altior Auto-Trade IG</b>\nTest notification successful!",
        "parse_mode": "HTML",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return TestResponse(success=True, message="Test message sent!")
            data = resp.json()
            desc = data.get("description", "Unknown error")
            return TestResponse(success=False, message=f"Telegram API error: {desc}")
    except Exception as e:
        return TestResponse(success=False, message=f"Connection error: {e}")
