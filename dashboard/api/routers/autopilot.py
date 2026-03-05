from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminUser, AppSetting
from dashboard.api.auth.jwt import get_current_user
from dashboard.api.deps import get_db, get_redis
from dashboard.api.schemas import (
    AutoPilotConfigRequest,
    AutoPilotScoreResponse,
    AutoPilotStatusResponse,
)

router = APIRouter(prefix="/api/autopilot", tags=["autopilot"])

_AP_SETTING_KEYS = [
    "autopilot_enabled",
    "autopilot_scan_interval_minutes",
    "autopilot_max_active_markets",
    "autopilot_min_score_threshold",
    "autopilot_universe_mode",
    "autopilot_search_terms",
    "autopilot_api_budget_per_cycle",
]


@router.get("/status", response_model=AutoPilotStatusResponse)
async def get_autopilot_status(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Get autopilot status, scores, and configuration."""
    r = await get_redis()

    # Get enabled from DB
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == "autopilot_enabled")
    )
    setting = result.scalar_one_or_none()
    enabled = setting and setting.value.lower() in ("true", "1", "yes")

    # Get runtime status from Redis
    status = await r.get("autopilot:status") or ("idle" if enabled else "disabled")
    last_scan = await r.get("autopilot:last_scan")

    # Get scores from Redis
    scores_raw = await r.get("autopilot:scores")
    scores = []
    active_count = 0
    if scores_raw:
        try:
            for s in json.loads(scores_raw):
                scores.append(AutoPilotScoreResponse(**s))
                if s.get("is_active"):
                    active_count += 1
        except (json.JSONDecodeError, TypeError):
            pass

    return AutoPilotStatusResponse(
        enabled=enabled,
        status=status,
        last_scan=last_scan,
        active_markets=active_count,
        scores=scores,
    )


@router.post("/toggle")
async def toggle_autopilot(
    enabled: bool,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Enable or disable autopilot."""
    # Save to DB
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == "autopilot_enabled")
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = str(enabled).lower()
    else:
        db.add(AppSetting(
            key="autopilot_enabled",
            value=str(enabled).lower(),
            category="autopilot",
        ))
    await db.commit()

    # Send command to bot via Redis
    r = await get_redis()
    await r.publish(
        "bot:commands",
        json.dumps({"command": "autopilot_toggle", "enabled": enabled}),
    )

    return {"enabled": enabled, "message": f"Auto-Pilot {'enabled' if enabled else 'disabled'}"}


@router.post("/scan-now")
async def trigger_scan(
    _user: AdminUser = Depends(get_current_user),
):
    """Trigger an immediate autopilot scan cycle."""
    r = await get_redis()
    await r.publish("bot:commands", json.dumps({"command": "autopilot_scan_now"}))
    return {"message": "Scan triggered"}


@router.get("/config")
async def get_autopilot_config(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Get current autopilot configuration."""
    result = await db.execute(
        select(AppSetting).where(AppSetting.key.in_(_AP_SETTING_KEYS))
    )
    settings_map = {s.key: s.value for s in result.scalars().all()}

    return {
        "enabled": settings_map.get("autopilot_enabled", "false").lower() in ("true", "1"),
        "scan_interval_minutes": int(settings_map.get("autopilot_scan_interval_minutes", "30")),
        "max_active_markets": int(settings_map.get("autopilot_max_active_markets", "3")),
        "min_score_threshold": float(settings_map.get("autopilot_min_score_threshold", "0.5")),
        "universe_mode": settings_map.get("autopilot_universe_mode", "watchlist"),
        "search_terms": settings_map.get(
            "autopilot_search_terms",
            "EUR/USD,GBP/USD,USD/JPY,US 500,FTSE 100,Germany 40,Gold,Oil",
        ),
        "api_budget_per_cycle": int(settings_map.get("autopilot_api_budget_per_cycle", "30")),
    }


@router.put("/config")
async def update_autopilot_config(
    req: AutoPilotConfigRequest,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Update autopilot configuration."""
    updates = req.model_dump(exclude_none=True)
    for field_name, value in updates.items():
        key = f"autopilot_{field_name}"
        result = await db.execute(select(AppSetting).where(AppSetting.key == key))
        setting = result.scalar_one_or_none()
        str_value = str(value).lower() if isinstance(value, bool) else str(value)
        if setting:
            setting.value = str_value
        else:
            db.add(AppSetting(key=key, value=str_value, category="autopilot"))

    await db.commit()

    # Notify bot to reload settings
    r = await get_redis()
    await r.publish("bot:commands", json.dumps({"command": "reload_settings"}))

    return {"message": "Configuration updated", "updated_fields": list(updates.keys())}


@router.get("/activity")
async def get_autopilot_activity(
    _user: AdminUser = Depends(get_current_user),
):
    """Get recent autopilot activity log entries from Redis."""
    r = await get_redis()
    raw_entries = await r.lrange("autopilot:activity", 0, 29)  # last 30
    entries = []
    for raw in raw_entries:
        try:
            entries.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            pass
    return entries
