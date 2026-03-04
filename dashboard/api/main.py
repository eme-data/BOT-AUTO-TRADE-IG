from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dashboard.api.deps import close_redis
from dashboard.api.routers import (
    auth,
    bot_control,
    markets,
    metrics,
    notifications,
    positions,
    settings,
    strategies,
    trades,
    ws,
)
from dashboard.api.schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_redis()


app = FastAPI(
    title="IG Trading Bot Dashboard",
    version="0.1.0",
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
app.include_router(ws.router)


@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


# Serve React static files (in production)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")
