from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminUser, Trade
from dashboard.api.auth.jwt import get_current_user
from dashboard.api.deps import get_db, get_redis
from dashboard.api.schemas import AccountResponse, MetricsResponse

router = APIRouter(prefix="/api/metrics", tags=["metrics"])
log = logging.getLogger(__name__)

# Lock to prevent concurrent IG session creation
_ig_lock = asyncio.Lock()


@router.get("", response_model=MetricsResponse)
async def get_metrics(db: AsyncSession = Depends(get_db)):
    """Get trading metrics summary."""
    # Open positions count
    open_result = await db.execute(
        select(func.count(Trade.id)).where(Trade.status == "OPEN")
    )
    open_count = open_result.scalar_one()

    # Total trades
    total_result = await db.execute(select(func.count(Trade.id)))
    total_trades = total_result.scalar_one()

    # Closed trades stats
    closed_result = await db.execute(
        select(
            func.count(Trade.id),
            func.sum(Trade.profit),
            func.count(Trade.id).filter(Trade.profit > 0),
            func.count(Trade.id).filter(Trade.profit <= 0),
        ).where(Trade.status == "CLOSED")
    )
    row = closed_result.one()
    closed_count = row[0] or 0
    total_pnl = float(row[1] or 0)
    winning = row[2] or 0
    losing = row[3] or 0
    win_rate = (winning / closed_count * 100) if closed_count > 0 else 0.0

    # Today's P&L
    from datetime import date
    today_result = await db.execute(
        select(func.sum(Trade.profit)).where(
            Trade.status == "CLOSED",
            func.date(Trade.closed_at) == date.today(),
        )
    )
    daily_pnl = float(today_result.scalar_one() or 0)

    # Account balance from IG (cached in Redis)
    account_balance = 0.0
    try:
        r = await get_redis()
        cached = await r.get("ig:account_balance")
        if cached:
            account_balance = float(cached)
        else:
            account_balance = await _fetch_ig_balance(db, r)
    except Exception as exc:
        log.debug("Could not fetch account balance: %s", exc)

    return MetricsResponse(
        daily_pnl=round(daily_pnl, 2),
        total_pnl=round(total_pnl, 2),
        open_positions=open_count,
        total_trades=total_trades,
        winning_trades=winning,
        losing_trades=losing,
        win_rate=round(win_rate, 1),
        account_balance=round(account_balance, 2),
    )


@router.get("/pnl-history")
async def get_pnl_history(
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Get daily P&L history for the equity curve chart."""
    result = await db.execute(
        select(
            cast(Trade.closed_at, Date).label("day"),
            func.sum(Trade.profit).label("pnl"),
            func.count(Trade.id).label("trades"),
        )
        .where(Trade.status == "CLOSED", Trade.closed_at.isnot(None))
        .group_by(cast(Trade.closed_at, Date))
        .order_by(cast(Trade.closed_at, Date))
        .limit(days)
    )
    rows = result.all()

    # Build cumulative P&L
    cumulative = 0.0
    history = []
    for row in rows:
        daily = float(row.pnl or 0)
        cumulative += daily
        history.append({
            "date": str(row.day),
            "daily_pnl": round(daily, 2),
            "cumulative_pnl": round(cumulative, 2),
            "trades": row.trades,
        })

    return history


def _fetch_ig_account_sync(creds: dict, acc_number: str) -> dict | None:
    """Synchronous IG API call — runs in a thread to avoid blocking the event loop."""
    from trading_ig import IGService

    ig = IGService(
        creds["username"],
        creds["password"],
        creds["api_key"],
        creds.get("acc_type", "DEMO"),
        use_rate_limiter=True,
    )
    ig.create_session(version="2")
    accounts = ig.fetch_accounts()
    ig.logout()

    for _, row in accounts.iterrows():
        if (acc_number and row.get("accountId") == acc_number) or row.get("preferred", False):
            return {
                "balance": float(row.get("balance", 0)),
                "deposit": float(row.get("deposit", 0)),
                "profit_loss": float(row.get("profitLoss", 0)),
                "available": float(row.get("available", 0)),
                "currency": str(row.get("currency", "EUR")),
            }
    return None


async def _get_cached_account(db: AsyncSession) -> dict | None:
    """Get account info from Redis cache, or fetch from IG (with lock to avoid parallel calls)."""
    r = await get_redis()

    # Check cache first (no lock needed for reads)
    cached = await r.get("ig:account_info")
    if cached:
        return json.loads(cached)

    # Acquire lock to prevent concurrent IG session creation
    async with _ig_lock:
        # Double-check cache after acquiring lock
        cached = await r.get("ig:account_info")
        if cached:
            return json.loads(cached)

        from dashboard.api.routers.settings import get_ig_credentials

        creds = await get_ig_credentials(db)
        if not creds.get("api_key") or not creds.get("username"):
            return None

        acc_number = creds.get("acc_number", "")

        # Run synchronous IG call in thread pool
        account_data = await asyncio.to_thread(
            _fetch_ig_account_sync, creds, acc_number
        )

        if account_data:
            await r.set("ig:account_info", json.dumps(account_data), ex=60)
            await r.set("ig:account_balance", str(account_data["balance"]), ex=60)

        return account_data


async def _fetch_ig_balance(db: AsyncSession, redis) -> float:
    """Fetch account balance from IG (uses shared cache)."""
    account_data = await _get_cached_account(db)
    return account_data["balance"] if account_data else 0.0


@router.get("/account", response_model=AccountResponse)
async def get_account(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Get IG account details (balance, deposit, available, P&L)."""
    try:
        account_data = await _get_cached_account(db)
        if account_data:
            return AccountResponse(**account_data)
    except Exception as exc:
        log.warning("Could not fetch IG account: %s", exc)

    return AccountResponse()
