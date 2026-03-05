from __future__ import annotations

import json
from datetime import datetime

import redis.asyncio as aioredis
import structlog

from bot.autopilot.models import AutoPilotConfig, MarketScore
from bot.autopilot.scanner import MarketScanner
from bot.autopilot.scorer import MarketScorer
from bot.autopilot.selector import StrategySelector
from bot.db.session import async_session_factory
from bot.strategies.macd_trend import MACDTrendStrategy
from bot.strategies.rsi_mean_reversion import RSIMeanReversionStrategy

logger = structlog.get_logger()

AP_PREFIX = "ap_"  # prefix for autopilot-managed strategies


class AutoPilotManager:
    """Orchestrates autonomous market scanning, scoring, and strategy activation."""

    def __init__(self, broker, registry, config: AutoPilotConfig, redis: aioredis.Redis):
        self.broker = broker
        self.registry = registry
        self.config = config
        self.redis = redis
        self.scanner = MarketScanner(broker)
        self.scorer = MarketScorer(broker)
        self.selector = StrategySelector()
        self._last_scores: list[MarketScore] = []
        self._active_strategies: dict[str, str] = {}  # epic -> strategy registry name

    async def run_scan_cycle(self) -> None:
        """Main autopilot cycle: scan -> score -> select -> activate."""
        if not self.config.enabled:
            return

        logger.info("autopilot_scan_start")
        await self._set_status("scanning")

        try:
            # 1. Get candidate markets
            async with async_session_factory() as session:
                candidates = await self.scanner.get_candidates(self.config, session)

            if not candidates:
                logger.info("autopilot_no_candidates")
                await self._set_status("idle")
                return

            # 2. Score each market (respecting API budget)
            api_budget = self.config.api_budget_per_cycle
            scores: list[MarketScore] = []

            for market in candidates:
                if api_budget < 3:
                    break
                score = await self.scorer.score_market(market.epic, market.instrument_name)
                scores.append(score)
                api_budget -= 3

            # 3. Rank by total score, filter by threshold
            scores.sort(key=lambda s: s.total_score, reverse=True)
            qualified = [s for s in scores if s.total_score >= self.config.min_score_threshold]

            # 4. Select top N markets (respecting max_active_markets)
            current_open = len(self._active_strategies)
            available_slots = max(0, self.config.max_active_markets - current_open)
            top_markets = qualified[:self.config.max_active_markets]

            # 5. Determine which strategies to add/remove
            new_epics = {s.epic for s in top_markets}
            old_epics = set(self._active_strategies.keys())

            # Remove strategies for markets no longer in top
            for epic in old_epics - new_epics:
                await self._deactivate_market(epic)

            # Activate strategies for new top markets
            for score in top_markets:
                if score.epic not in self._active_strategies:
                    await self._activate_market(score)

            # 6. Update scores with active status and publish
            for score in scores:
                if score.epic in self._active_strategies:
                    score.is_active = True
                    score.selected_strategy = self._active_strategies.get(score.epic, "").replace(AP_PREFIX, "")

            self._last_scores = scores
            await self._publish_scores(scores)
            await self._set_status("idle")

            logger.info(
                "autopilot_scan_complete",
                scored=len(scores),
                qualified=len(qualified),
                active=len(self._active_strategies),
            )

        except Exception as e:
            logger.error("autopilot_scan_error", error=str(e))
            await self._set_status("error")

    async def _activate_market(self, score: MarketScore) -> None:
        """Create and register a strategy for the given market."""
        strategy_type, config = self.selector.select(score)
        registry_name = f"{AP_PREFIX}{strategy_type}_{score.epic.replace('.', '_')}"

        # Create strategy instance
        strategy = self._create_strategy(strategy_type, config)
        if not strategy:
            return

        strategy.name = registry_name
        strategy.enabled = True
        self.registry.register(strategy)
        self._active_strategies[score.epic] = registry_name
        score.is_active = True
        score.selected_strategy = strategy_type

        logger.info(
            "autopilot_market_activated",
            epic=score.epic,
            strategy=strategy_type,
            score=score.total_score,
            regime=score.regime,
        )

    async def _deactivate_market(self, epic: str) -> None:
        """Remove autopilot strategy for a market."""
        registry_name = self._active_strategies.pop(epic, None)
        if registry_name:
            self.registry.unregister(registry_name)
            logger.info("autopilot_market_deactivated", epic=epic, strategy=registry_name)

    async def deactivate_all(self) -> None:
        """Remove all autopilot-managed strategies."""
        for epic in list(self._active_strategies.keys()):
            await self._deactivate_market(epic)
        self._last_scores = []
        await self._set_status("disabled")

    def _create_strategy(self, name: str, config: dict):
        strategies = {
            "rsi_mean_reversion": RSIMeanReversionStrategy,
            "macd_trend": MACDTrendStrategy,
        }
        cls = strategies.get(name)
        if cls:
            return cls(config)
        return None

    async def _set_status(self, status: str) -> None:
        try:
            await self.redis.set("autopilot:status", status)
            await self.redis.set("autopilot:last_scan", datetime.utcnow().isoformat())
        except Exception:
            pass

    async def _publish_scores(self, scores: list[MarketScore]) -> None:
        """Publish scores to Redis for dashboard consumption."""
        try:
            data = [
                {
                    "epic": s.epic,
                    "instrument_name": s.instrument_name,
                    "total_score": s.total_score,
                    "trend_score": s.trend_score,
                    "momentum_score": s.momentum_score,
                    "volatility_score": s.volatility_score,
                    "regime": s.regime,
                    "direction_bias": s.direction_bias,
                    "timeframe_alignment": s.timeframe_alignment,
                    "selected_strategy": s.selected_strategy,
                    "is_active": s.is_active,
                    "scored_at": s.scored_at.isoformat(),
                }
                for s in scores
            ]
            await self.redis.set("autopilot:scores", json.dumps(data), ex=3600)
        except Exception:
            pass

    def get_last_scores(self) -> list[MarketScore]:
        return self._last_scores
