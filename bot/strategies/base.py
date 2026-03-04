from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd

from bot.broker.models import Direction, Tick


@dataclass
class SignalResult:
    """Result produced by a strategy evaluation."""
    signal_type: str  # BUY, SELL, CLOSE, HOLD
    epic: str
    confidence: float = 0.0
    stop_distance: int | None = None
    limit_distance: int | None = None
    size: float | None = None
    indicators: dict = field(default_factory=dict)
    reason: str = ""


class AbstractStrategy(ABC):
    """Base class for all trading strategies."""

    def __init__(self, name: str, config: dict | None = None):
        self.name = name
        self.config = config or {}
        self.enabled = True

    @abstractmethod
    def on_tick(self, tick: Tick) -> SignalResult | None:
        """Process a real-time tick. Return a signal or None."""

    @abstractmethod
    def on_bar(self, epic: str, df: pd.DataFrame) -> SignalResult | None:
        """Process a new completed bar (candle). df contains historical OHLCV + indicators."""

    @abstractmethod
    def get_required_epics(self) -> list[str]:
        """Return list of epics this strategy needs to subscribe to."""

    @abstractmethod
    def get_required_resolution(self) -> str:
        """Return the candle resolution needed (MINUTE, MINUTE_5, HOUR, DAY, etc.)."""

    @abstractmethod
    def get_required_history(self) -> int:
        """Return number of historical bars needed for indicator warmup."""

    def get_config_schema(self) -> dict:
        """Return a dict describing configurable parameters."""
        return {}

    def update_config(self, config: dict) -> None:
        self.config.update(config)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} enabled={self.enabled}>"
