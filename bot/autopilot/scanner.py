from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.autopilot.models import AutoPilotConfig
from bot.broker.ig_rest import IGRestClient
from bot.broker.models import MarketInfo
from bot.db.models import WatchedMarket

logger = structlog.get_logger()


class MarketScanner:
    """Discovers and filters tradeable markets."""

    def __init__(self, broker: IGRestClient):
        self.broker = broker

    async def get_candidates(
        self, config: AutoPilotConfig, session: AsyncSession
    ) -> list[MarketInfo]:
        """Get candidate markets based on universe mode."""
        if config.universe_mode == "discovery":
            return await self._discovery_scan(config)
        return await self._watchlist_scan(session)

    async def _watchlist_scan(self, session: AsyncSession) -> list[MarketInfo]:
        """Scan markets from the user's watchlist."""
        result = await session.execute(
            select(WatchedMarket).where(WatchedMarket.enabled.is_(True))
        )
        watched = result.scalars().all()

        markets = []
        for wm in watched:
            try:
                info = await self.broker.get_market_info(wm.epic)
                if info.market_status == "TRADEABLE":
                    markets.append(info)
                await asyncio.sleep(1)  # rate limit
            except Exception as e:
                logger.debug("watchlist_scan_error", epic=wm.epic, error=str(e))

        logger.info("watchlist_scan_complete", total=len(watched), tradeable=len(markets))
        return markets

    async def _discovery_scan(self, config: AutoPilotConfig) -> list[MarketInfo]:
        """Discover markets by searching IG with configured terms."""
        seen_epics: set[str] = set()
        markets: list[MarketInfo] = []

        for term in config.search_terms:
            try:
                results = await self.broker.search_markets(term)
                for info in results:
                    if info.epic not in seen_epics and info.market_status == "TRADEABLE":
                        seen_epics.add(info.epic)
                        markets.append(info)
                await asyncio.sleep(1.5)
            except Exception as e:
                logger.debug("discovery_scan_error", term=term, error=str(e))

        logger.info("discovery_scan_complete", terms=len(config.search_terms), tradeable=len(markets))
        return markets
