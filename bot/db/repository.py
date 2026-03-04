from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import DailyPnL, Signal, StrategyState, Trade


class TradeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, trade: Trade) -> Trade:
        self.session.add(trade)
        await self.session.commit()
        await self.session.refresh(trade)
        return trade

    async def get_by_deal_id(self, deal_id: str) -> Trade | None:
        result = await self.session.execute(select(Trade).where(Trade.deal_id == deal_id))
        return result.scalar_one_or_none()

    async def get_open_trades(self) -> list[Trade]:
        result = await self.session.execute(
            select(Trade).where(Trade.status == "OPEN").order_by(Trade.opened_at.desc())
        )
        return list(result.scalars().all())

    async def close_trade(self, deal_id: str, close_price: float, profit: float) -> None:
        await self.session.execute(
            update(Trade)
            .where(Trade.deal_id == deal_id)
            .values(status="CLOSED", close_price=close_price, profit=profit, closed_at=datetime.now())
        )
        await self.session.commit()

    async def get_trades_since(self, since: datetime) -> list[Trade]:
        result = await self.session.execute(
            select(Trade).where(Trade.opened_at >= since).order_by(Trade.opened_at.desc())
        )
        return list(result.scalars().all())

    async def get_recent_trades(self, limit: int = 50) -> list[Trade]:
        result = await self.session.execute(
            select(Trade).order_by(Trade.opened_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


class SignalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, signal: Signal) -> Signal:
        self.session.add(signal)
        await self.session.commit()
        await self.session.refresh(signal)
        return signal

    async def get_recent(self, strategy_name: str | None = None, limit: int = 50) -> list[Signal]:
        query = select(Signal).order_by(Signal.time.desc()).limit(limit)
        if strategy_name:
            query = query.where(Signal.strategy_name == strategy_name)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class StrategyStateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, name: str) -> StrategyState | None:
        result = await self.session.execute(select(StrategyState).where(StrategyState.name == name))
        return result.scalar_one_or_none()

    async def get_all_enabled(self) -> list[StrategyState]:
        result = await self.session.execute(
            select(StrategyState).where(StrategyState.enabled.is_(True))
        )
        return list(result.scalars().all())

    async def upsert(self, name: str, enabled: bool = True, config: dict | None = None, state: dict | None = None) -> StrategyState:
        existing = await self.get(name)
        if existing:
            if config is not None:
                existing.config = config
            if state is not None:
                existing.state = state
            existing.enabled = enabled
        else:
            existing = StrategyState(name=name, enabled=enabled, config=config or {}, state=state or {})
            self.session.add(existing)
        await self.session.commit()
        return existing


class DailyPnLRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_today(self, account_id: str) -> DailyPnL | None:
        today = datetime.now().date()
        result = await self.session.execute(
            select(DailyPnL).where(DailyPnL.date == today, DailyPnL.account_id == account_id)
        )
        return result.scalar_one_or_none()

    async def get_range(self, account_id: str, start: datetime, end: datetime) -> list[DailyPnL]:
        result = await self.session.execute(
            select(DailyPnL)
            .where(DailyPnL.account_id == account_id, DailyPnL.date >= start, DailyPnL.date <= end)
            .order_by(DailyPnL.date)
        )
        return list(result.scalars().all())
