from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Trade
from dashboard.api.deps import get_db
from dashboard.api.schemas import PositionResponse

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("", response_model=list[PositionResponse])
async def get_open_positions(db: AsyncSession = Depends(get_db)):
    """Get all open positions from the database."""
    result = await db.execute(
        select(Trade).where(Trade.status == "OPEN").order_by(Trade.opened_at.desc())
    )
    trades = result.scalars().all()
    return [
        PositionResponse(
            deal_id=t.deal_id,
            epic=t.epic,
            direction=t.direction,
            size=t.size,
            open_level=t.open_price or 0.0,
            stop_level=t.stop_level,
            limit_level=t.limit_level,
            currency=t.currency,
            profit=t.profit or 0.0,
        )
        for t in trades
    ]
