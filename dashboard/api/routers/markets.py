from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminUser, WatchedMarket
from dashboard.api.auth.jwt import get_current_user
from dashboard.api.deps import get_db
from dashboard.api.routers.settings import get_ig_credentials

router = APIRouter(prefix="/api/markets", tags=["markets"])


class MarketSearchResult(BaseModel):
    epic: str
    instrument_name: str
    instrument_type: str
    expiry: str
    bid: float
    offer: float
    market_status: str
    is_watched: bool = False


class WatchedMarketResponse(BaseModel):
    id: int
    epic: str
    instrument_name: str
    instrument_type: str
    expiry: str
    currency: str
    enabled: bool


class AddMarketRequest(BaseModel):
    epic: str
    instrument_name: str = ""
    instrument_type: str = ""
    expiry: str = "-"
    currency: str = "EUR"


# ---- Search markets on IG ----

@router.get("/search", response_model=list[MarketSearchResult])
async def search_markets(
    term: str = Query(..., min_length=2, description="Search term"),
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Search for markets on IG by keyword."""
    creds = await get_ig_credentials(db)
    if not all([creds["api_key"], creds["username"], creds["password"]]):
        raise HTTPException(status_code=400, detail="IG credentials not configured. Go to Settings > IG Account.")

    try:
        from trading_ig import IGService

        ig = IGService(creds["username"], creds["password"], creds["api_key"], creds["acc_type"], use_rate_limiter=True)
        ig.create_session(version="2")
        results = ig.search_markets(term)
        ig.logout()

        # Get watched epics for marking
        watched_result = await db.execute(select(WatchedMarket.epic))
        watched_epics = {row[0] for row in watched_result.fetchall()}

        markets = []
        for _, row in results.iterrows():
            epic = row.get("epic", "")
            markets.append(
                MarketSearchResult(
                    epic=epic,
                    instrument_name=row.get("instrumentName", ""),
                    instrument_type=row.get("instrumentType", ""),
                    expiry=row.get("expiry", "-"),
                    bid=float(row.get("bid", 0) or 0),
                    offer=float(row.get("offer", 0) or 0),
                    market_status=row.get("marketStatus", ""),
                    is_watched=epic in watched_epics,
                )
            )
        return markets

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"IG search failed: {str(e)}")


# ---- Watched markets (watchlist) ----

@router.get("/watched", response_model=list[WatchedMarketResponse])
async def get_watched_markets(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Get all watched markets."""
    result = await db.execute(select(WatchedMarket).order_by(WatchedMarket.instrument_name))
    markets = result.scalars().all()
    return [
        WatchedMarketResponse(
            id=m.id,
            epic=m.epic,
            instrument_name=m.instrument_name,
            instrument_type=m.instrument_type,
            expiry=m.expiry,
            currency=m.currency,
            enabled=m.enabled,
        )
        for m in markets
    ]


@router.post("/watched", response_model=WatchedMarketResponse)
async def add_watched_market(
    req: AddMarketRequest,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Add a market to the watchlist."""
    # Check if already exists
    existing = await db.execute(select(WatchedMarket).where(WatchedMarket.epic == req.epic))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Market {req.epic} is already in your watchlist")

    market = WatchedMarket(
        epic=req.epic,
        instrument_name=req.instrument_name,
        instrument_type=req.instrument_type,
        expiry=req.expiry,
        currency=req.currency,
    )
    db.add(market)
    await db.commit()
    await db.refresh(market)

    return WatchedMarketResponse(
        id=market.id,
        epic=market.epic,
        instrument_name=market.instrument_name,
        instrument_type=market.instrument_type,
        expiry=market.expiry,
        currency=market.currency,
        enabled=market.enabled,
    )


@router.put("/watched/{market_id}")
async def toggle_watched_market(
    market_id: int,
    enabled: bool,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Enable or disable a watched market."""
    result = await db.execute(select(WatchedMarket).where(WatchedMarket.id == market_id))
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    market.enabled = enabled
    await db.commit()
    return {"message": f"Market {market.epic} {'enabled' if enabled else 'disabled'}"}


@router.delete("/watched/{market_id}")
async def remove_watched_market(
    market_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Remove a market from the watchlist."""
    result = await db.execute(select(WatchedMarket).where(WatchedMarket.id == market_id))
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    await db.delete(market)
    await db.commit()
    return {"message": f"Market {market.epic} removed"}
