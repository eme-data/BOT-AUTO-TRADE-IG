from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MarketScore:
    """Composite score for a market opportunity."""

    epic: str
    instrument_name: str = ""
    total_score: float = 0.0
    trend_score: float = 0.0
    momentum_score: float = 0.0
    volatility_score: float = 0.0
    regime: str = "neutral"  # trending, ranging, volatile, neutral
    direction_bias: str = "neutral"  # bullish, bearish, neutral
    timeframe_alignment: float = 0.0
    selected_strategy: str | None = None
    strategy_config: dict = field(default_factory=dict)
    is_active: bool = False
    scored_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AutoPilotConfig:
    """Configuration for the auto-pilot mode."""

    enabled: bool = False
    scan_interval_minutes: int = 30
    max_active_markets: int = 3
    min_score_threshold: float = 0.5
    universe_mode: str = "discovery"  # watchlist or discovery
    search_terms: list[str] = field(
        default_factory=lambda: [
            "EUR/USD", "GBP/USD", "USD/JPY",
            "US 500", "FTSE 100", "Germany 40",
            "Gold", "Oil",
        ]
    )
    prefer_trend_following: bool = True
    api_budget_per_cycle: int = 30
