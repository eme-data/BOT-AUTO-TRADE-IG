from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminUser, AppSetting
from dashboard.api.auth.jwt import get_current_user
from dashboard.api.deps import get_db, get_redis

router = APIRouter(prefix="/api/bot", tags=["bot"])


class BotStatusResponse(BaseModel):
    status: str  # stopped, starting, running, error
    message: str = ""


class BotCommandResponse(BaseModel):
    success: bool
    message: str


@router.get("/status", response_model=BotStatusResponse)
async def get_bot_status(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Get current bot status."""
    result = await db.execute(select(AppSetting).where(AppSetting.key == "bot_status"))
    setting = result.scalar_one_or_none()
    status_val = setting.value if setting else "stopped"

    return BotStatusResponse(status=status_val)


@router.post("/start", response_model=BotCommandResponse)
async def start_bot(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Send start command to the bot via Redis."""
    # Check if IG credentials are configured
    cred_keys = ["ig_api_key", "ig_username", "ig_password"]
    result = await db.execute(select(AppSetting).where(AppSetting.key.in_(cred_keys)))
    creds = {s.key: s.value for s in result.scalars().all()}

    if not all(creds.get(k) for k in cred_keys):
        raise HTTPException(status_code=400, detail="IG credentials not configured. Go to Settings > IG Account.")

    # Send start command via Redis
    redis = await get_redis()
    await redis.publish("bot:commands", json.dumps({"command": "start"}))

    # Update status
    await _set_status(db, "starting")

    return BotCommandResponse(success=True, message="Start command sent")


@router.post("/stop", response_model=BotCommandResponse)
async def stop_bot(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Send stop command to the bot via Redis."""
    redis = await get_redis()
    await redis.publish("bot:commands", json.dumps({"command": "stop"}))

    await _set_status(db, "stopped")

    return BotCommandResponse(success=True, message="Stop command sent")


@router.post("/restart", response_model=BotCommandResponse)
async def restart_bot(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Send restart command to the bot via Redis."""
    redis = await get_redis()
    await redis.publish("bot:commands", json.dumps({"command": "restart"}))

    await _set_status(db, "starting")

    return BotCommandResponse(success=True, message="Restart command sent")


async def _set_status(db: AsyncSession, status: str) -> None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == "bot_status"))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = status
    else:
        db.add(AppSetting(key="bot_status", value=status, category="general"))
    await db.commit()
