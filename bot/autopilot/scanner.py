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

# Market types suitable for autopilot trading (exclude ETFs, shares, etc.)
ALLOWED_TYPES = {"CURRENCIES", "INDICES", "COMMODITIES", "RATES", "BUNGEE"}


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
        all_markets: list[MarketInfo] = []

        rejected_types: dict[str, int] = {}
        for term in config.search_terms:
            try:
                results = await self.broker.search_markets(term)
                for info in results:
                    if info.epic in seen_epics:
                        continue
                    if info.market_status != "TRADEABLE":
                        continue
                    if info.instrument_type not in ALLOWED_TYPES:
                        rejected_types[info.instrument_type] = rejected_types.get(info.instrument_type, 0) + 1
                        continue
                    seen_epics.add(info.epic)
                    all_markets.append(info)
                await asyncio.sleep(1.5)
            except Exception as e:
                logger.warning("discovery_scan_error", term=term, error=str(e))

        if rejected_types:
            logger.info("discovery_rejected_types", rejected=rejected_types)

        # Deduplicate: keep only one variant per underlying market
        # Group by base name (strip "Mini", "Forward", size suffixes)
        markets = self._deduplicate_markets(all_markets)

        type_counts: dict[str, int] = {}
        for m in markets:
            type_counts[m.instrument_type] = type_counts.get(m.instrument_type, 0) + 1
        logger.info("discovery_scan_complete", terms=len(config.search_terms), raw=len(all_markets), deduplicated=len(markets), types=type_counts)
        return markets

    @staticmethod
    def _deduplicate_markets(markets: list[MarketInfo]) -> list[MarketInfo]:
        """Keep one instrument per underlying market (prefer Mini/smallest deal size)."""
        import re
        # Map translated/localized names to canonical English names
        _NAME_ALIASES = {
            "or": "gold", "or au comptant": "gold", "spot gold": "gold",
            "argent": "silver", "argent au comptant": "silver", "spot silver": "silver",
            "pétrole": "oil", "petrole": "oil", "crude oil": "oil",
            "us 500": "us 500", "s&p 500": "us 500",
            "wall street": "wall street", "dow jones": "wall street",
            "france 40": "france 40", "cac 40": "france 40",
            "germany 40": "germany 40", "dax 40": "germany 40",
            "ftse 100": "ftse 100", "uk 100": "ftse 100",
        }

        groups: dict[str, list[MarketInfo]] = {}
        for m in markets:
            # Normalize name: remove "Mini", "(1€)", "(50$)", "(250$)", "Cash", "au comptant" etc.
            base = re.sub(r'\s*(Mini|Forward|Cash|au comptant|Spot)\s*', ' ', m.instrument_name, flags=re.IGNORECASE)
            base = re.sub(r'\s*\([^)]*\)\s*', ' ', base)  # remove parenthetical like (1€)
            base = re.sub(r'\s+', ' ', base).strip().lower()
            # Apply alias mapping to unify translated names
            base = _NAME_ALIASES.get(base, base)
            if base not in groups:
                groups[base] = []
            groups[base].append(m)

        result: list[MarketInfo] = []
        for base, variants in groups.items():
            # Prefer "Mini" variant (smaller deal size), otherwise first one
            mini = [v for v in variants if "mini" in v.instrument_name.lower()]
            chosen = mini[0] if mini else variants[0]
            result.append(chosen)
            if len(variants) > 1:
                logger.debug("dedup_market", base=base, kept=chosen.epic, dropped=[v.epic for v in variants if v != chosen])

        return result
