from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.repository import StrategyStateRepository
from dashboard.api.deps import get_db
from dashboard.api.schemas import StrategyResponse, StrategyUpdateRequest

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategyResponse])
async def get_strategies(db: AsyncSession = Depends(get_db)):
    """Get all registered strategies."""
    repo = StrategyStateRepository(db)
    # Get all strategy states (not just enabled)
    from sqlalchemy import select
    from bot.db.models import StrategyState
    result = await db.execute(select(StrategyState))
    states = result.scalars().all()

    return [
        StrategyResponse(
            name=s.name,
            enabled=s.enabled,
            config=s.config,
        )
        for s in states
    ]


@router.get("/{name}", response_model=StrategyResponse)
async def get_strategy(name: str, db: AsyncSession = Depends(get_db)):
    """Get a specific strategy by name."""
    repo = StrategyStateRepository(db)
    state = await repo.get(name)
    if not state:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")

    return StrategyResponse(
        name=state.name,
        enabled=state.enabled,
        config=state.config,
    )


@router.put("/{name}", response_model=StrategyResponse)
async def update_strategy(name: str, req: StrategyUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Update strategy configuration."""
    repo = StrategyStateRepository(db)
    state = await repo.get(name)
    if not state:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")

    updated = await repo.upsert(
        name=name,
        enabled=req.enabled if req.enabled is not None else state.enabled,
        config=req.config if req.config is not None else state.config,
    )

    return StrategyResponse(
        name=updated.name,
        enabled=updated.enabled,
        config=updated.config,
    )
