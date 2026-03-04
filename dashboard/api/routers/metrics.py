from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Trade
from dashboard.api.deps import get_db
from dashboard.api.schemas import MetricsResponse

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


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

    return MetricsResponse(
        daily_pnl=round(daily_pnl, 2),
        total_pnl=round(total_pnl, 2),
        open_positions=open_count,
        total_trades=total_trades,
        winning_trades=winning,
        losing_trades=losing,
        win_rate=round(win_rate, 1),
    )
