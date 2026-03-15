from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from bot.db.models import AdminUser
from dashboard.api.auth.jwt import get_current_user
from dashboard.api.deps import get_redis

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/status")
async def get_calendar_status(
    _user: AdminUser = Depends(get_current_user),
):
    """Get economic calendar status and upcoming events."""
    r = await get_redis()
    raw = await r.get("calendar:status")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "enabled": True,
        "paused": False,
        "paused_until": None,
        "next_event": None,
        "total_events": 0,
        "upcoming_events": [],
    }
