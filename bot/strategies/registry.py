from __future__ import annotations

import structlog

from bot.broker.models import Tick
from bot.strategies.base import AbstractStrategy, SignalResult

logger = structlog.get_logger()


class StrategyRegistry:
    """Registry for managing pluggable strategies."""

    def __init__(self):
        self._strategies: dict[str, AbstractStrategy] = {}

    def register(self, strategy: AbstractStrategy) -> None:
        self._strategies[strategy.name] = strategy
        logger.info("strategy_registered", name=strategy.name, type=type(strategy).__name__)

    def unregister(self, name: str) -> None:
        self._strategies.pop(name, None)
        logger.info("strategy_unregistered", name=name)

    def get(self, name: str) -> AbstractStrategy | None:
        return self._strategies.get(name)

    def get_all(self) -> list[AbstractStrategy]:
        return list(self._strategies.values())

    def get_enabled(self) -> list[AbstractStrategy]:
        return [s for s in self._strategies.values() if s.enabled]

    def get_all_required_epics(self) -> set[str]:
        epics = set()
        for strategy in self.get_enabled():
            epics.update(strategy.get_required_epics())
        return epics

    def on_tick(self, tick: Tick) -> list[tuple[str, SignalResult]]:
        """Dispatch tick to all enabled strategies. Returns list of (strategy_name, signal)."""
        signals = []
        for strategy in self.get_enabled():
            if tick.epic in strategy.get_required_epics():
                try:
                    result = strategy.on_tick(tick)
                    if result and result.signal_type != "HOLD":
                        signals.append((strategy.name, result))
                        logger.info(
                            "signal_generated",
                            strategy=strategy.name,
                            epic=tick.epic,
                            signal=result.signal_type,
                            confidence=result.confidence,
                        )
                except Exception as e:
                    logger.error("strategy_tick_error", strategy=strategy.name, error=str(e))
        return signals

    def enable(self, name: str) -> bool:
        strategy = self._strategies.get(name)
        if strategy:
            strategy.enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        strategy = self._strategies.get(name)
        if strategy:
            strategy.enabled = False
            return True
        return False
