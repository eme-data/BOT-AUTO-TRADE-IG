from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text

from dashboard.api.deps import close_redis, get_redis
from dashboard.api.routers import (
    accounts,
    ai,
    auth,
    autopilot,
    backtest,
    bot_control,
    calendar,
    markets,
    metrics,
    notifications,
    positions,
    reports,
    settings,
    strategies,
    trades,
    users,
    ws,
)
from dashboard.api.schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _ensure_admin_account()
    yield
    await close_redis()


async def _ensure_admin_account():
    """Create the initial admin account from ADMIN_USERNAME/ADMIN_PASSWORD env vars."""
    import logging
    import os

    from sqlalchemy import func, select

    from bot.db.models import AdminUser
    from bot.db.session import async_session_factory
    from dashboard.api.auth.jwt import hash_password

    log = logging.getLogger(__name__)
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "").strip()
    if not username or not password:
        return

    try:
        async with async_session_factory() as session:
            result = await session.execute(select(func.count(AdminUser.id)))
            if result.scalar_one() > 0:
                return

            user = AdminUser(
                username=username,
                hashed_password=hash_password(password),
            )
            session.add(user)
            await session.commit()
            log.info("Admin account '%s' created from environment variables.", username)
    except Exception as exc:
        log.warning("Could not auto-create admin account: %s", exc)


app = FastAPI(
    title="Altior Holding - Auto-Trade IG",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public routes (no auth required)
app.include_router(auth.router)

# Protected routes (JWT auth via get_current_user dependency in each router)
app.include_router(positions.router)
app.include_router(trades.router)
app.include_router(strategies.router)
app.include_router(metrics.router)
app.include_router(settings.router)
app.include_router(markets.router)
app.include_router(bot_control.router)
app.include_router(notifications.router)
app.include_router(backtest.router)
app.include_router(users.router)
app.include_router(autopilot.router)
app.include_router(ai.router)
app.include_router(calendar.router)
app.include_router(accounts.router)
app.include_router(reports.router)
app.include_router(ws.router)


@app.get("/api/health", response_model=HealthResponse)
async def health():
    from bot.db.session import async_session_factory

    db_status = "ok"
    redis_status = "ok"
    bot_status = "unknown"

    # Check DB
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    # Check Redis + bot status
    try:
        r = await get_redis()
        await r.ping()
        raw = await r.get("bot:current_status")
        bot_status = raw or "stopped"
    except Exception:
        redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return HealthResponse(status=overall, db=db_status, redis=redis_status, bot=bot_status)


# Serve React static files (in production)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")
