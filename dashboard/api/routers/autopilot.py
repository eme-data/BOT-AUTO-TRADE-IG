from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import func as sa_func

from bot.db.models import AdminUser, AppSetting, Trade, WatchedMarket
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
    "autopilot_shadow_mode",
]


@router.get("/status", response_model=AutoPilotStatusResponse)
async def get_autopilot_status(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Get autopilot status, scores, and configuration."""
    r = await get_redis()

    # Get enabled and shadow_mode from DB
    result = await db.execute(
        select(AppSetting).where(AppSetting.key.in_(["autopilot_enabled", "autopilot_shadow_mode"]))
    )
    ap_settings = {s.key: s.value for s in result.scalars().all()}
    enabled = ap_settings.get("autopilot_enabled", "false").lower() in ("true", "1", "yes")
    shadow_mode = ap_settings.get("autopilot_shadow_mode", "true").lower() in ("true", "1", "yes")

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
        shadow_mode=shadow_mode,
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

    # If enabling, auto-set discovery mode when no watchlist markets exist
    if enabled:
        wl_result = await db.execute(
            select(WatchedMarket).where(WatchedMarket.enabled.is_(True)).limit(1)
        )
        has_watchlist = wl_result.scalar_one_or_none() is not None

        if not has_watchlist:
            # Auto-switch to discovery mode so it works out of the box
            mode_result = await db.execute(
                select(AppSetting).where(AppSetting.key == "autopilot_universe_mode")
            )
            mode_setting = mode_result.scalar_one_or_none()
            if mode_setting:
                mode_setting.value = "discovery"
            else:
                db.add(AppSetting(
                    key="autopilot_universe_mode",
                    value="discovery",
                    category="autopilot",
                ))
            await db.commit()

    # Send command to bot via Redis
    r = await get_redis()
    await r.publish(
        "bot:commands",
        json.dumps({"command": "autopilot_toggle", "enabled": enabled}),
    )

    # Auto-trigger a scan immediately when enabling
    if enabled:
        await r.publish("bot:commands", json.dumps({"command": "autopilot_scan_now"}))

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
        "scan_interval_minutes": int(settings_map.get("autopilot_scan_interval_minutes", "60")),
        "max_active_markets": int(settings_map.get("autopilot_max_active_markets", "3")),
        "min_score_threshold": float(settings_map.get("autopilot_min_score_threshold", "0.35")),
        "universe_mode": settings_map.get("autopilot_universe_mode", "discovery"),
        "search_terms": settings_map.get(
            "autopilot_search_terms",
            "EUR/USD,GBP/USD,US 500,Gold",
        ),
        "api_budget_per_cycle": int(settings_map.get("autopilot_api_budget_per_cycle", "15")),
        "shadow_mode": settings_map.get("autopilot_shadow_mode", "true").lower() in ("true", "1"),
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


@router.get("/performance")
async def get_autopilot_performance(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Get P&L performance breakdown for autopilot-managed strategies."""
    # Autopilot strategies are prefixed with "ap_"
    result = await db.execute(
        select(
            Trade.strategy_name,
            Trade.epic,
            sa_func.count(Trade.id).label("total_trades"),
            sa_func.sum(Trade.profit).label("total_pnl"),
            sa_func.count(Trade.id).filter(Trade.profit > 0).label("winning"),
            sa_func.count(Trade.id).filter(Trade.profit <= 0).label("losing"),
            sa_func.avg(Trade.profit).label("avg_pnl"),
        )
        .where(Trade.strategy_name.like("ap_%"))
        .group_by(Trade.strategy_name, Trade.epic)
        .order_by(sa_func.sum(Trade.profit).desc())
    )
    rows = result.all()

    strategies: dict[str, dict] = {}
    for row in rows:
        name = row.strategy_name
        if name not in strategies:
            strategies[name] = {
                "strategy_name": name,
                "epics": [],
                "total_trades": 0,
                "total_pnl": 0.0,
                "winning": 0,
                "losing": 0,
            }
        s = strategies[name]
        s["epics"].append(row.epic)
        s["total_trades"] += row.total_trades
        s["total_pnl"] += float(row.total_pnl or 0)
        s["winning"] += row.winning
        s["losing"] += row.losing

    for s in strategies.values():
        s["win_rate"] = round(s["winning"] / s["total_trades"] * 100, 1) if s["total_trades"] else 0
        s["total_pnl"] = round(s["total_pnl"], 2)

    return {
        "strategies": list(strategies.values()),
        "overall": {
            "total_trades": sum(s["total_trades"] for s in strategies.values()),
            "total_pnl": round(sum(s["total_pnl"] for s in strategies.values()), 2),
        },
    }
