from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminUser, Trade
from dashboard.api.auth.jwt import get_current_user
from dashboard.api.deps import get_db
from dashboard.api.schemas import TradeResponse

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("", response_model=list[TradeResponse])
async def get_trades(
    status: str | None = None,
    strategy: str | None = None,
    epic: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get trades with optional filtering."""
    query = select(Trade).order_by(Trade.opened_at.desc())

    if status:
        query = query.where(Trade.status == status.upper())
    if strategy:
        query = query.where(Trade.strategy_name == strategy)
    if epic:
        query = query.where(Trade.epic == epic)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    trades = result.scalars().all()

    return [
        TradeResponse(
            id=t.id,
            deal_id=t.deal_id,
            epic=t.epic,
            direction=t.direction,
            size=t.size,
            open_price=t.open_price,
            close_price=t.close_price,
            profit=t.profit,
            strategy_name=t.strategy_name,
            status=t.status,
            opened_at=t.opened_at,
            closed_at=t.closed_at,
            notes=t.notes,
        )
        for t in trades
    ]


@router.get("/count")
async def get_trade_count(db: AsyncSession = Depends(get_db)):
    """Get total trade count."""
    result = await db.execute(select(func.count(Trade.id)))
    return {"count": result.scalar_one()}


@router.get("/export/csv")
async def export_trades_csv(
    status: str | None = None,
    strategy: str | None = None,
    epic: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Export all trades as CSV file."""
    query = select(Trade).order_by(Trade.opened_at.desc())
    if status:
        query = query.where(Trade.status == status.upper())
    if strategy:
        query = query.where(Trade.strategy_name == strategy)
    if epic:
        query = query.where(Trade.epic == epic)

    result = await db.execute(query)
    trades = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Deal ID", "Epic", "Direction", "Size", "Open Price",
        "Close Price", "P&L", "Strategy", "Status", "Opened At", "Closed At",
    ])
    for t in trades:
        writer.writerow([
            t.id, t.deal_id, t.epic, t.direction, t.size,
            t.open_price, t.close_price, t.profit,
            t.strategy_name or "", t.status,
            t.opened_at.isoformat() if t.opened_at else "",
            t.closed_at.isoformat() if t.closed_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trades.csv"},
    )


class TradeNotesUpdate(BaseModel):
    notes: str


@router.patch("/{trade_id}/notes")
async def update_trade_notes(
    trade_id: int,
    body: TradeNotesUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Update notes/journal entry for a specific trade."""
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(404, "Trade not found")

    await db.execute(
        update(Trade).where(Trade.id == trade_id).values(notes=body.notes)
    )
    await db.commit()
    return {"status": "ok"}
