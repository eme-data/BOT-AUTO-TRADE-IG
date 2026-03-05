from __future__ import annotations

from bot.autopilot.models import MarketScore


class StrategySelector:
    """Selects the best strategy for a market based on its regime and score."""

    def select(self, score: MarketScore) -> tuple[str, dict]:
        """Return (strategy_name, config_overrides) for the given market score."""
        if score.regime == "trending":
            return "macd_trend", {
                "epics": [score.epic],
                "resolution": "HOUR",
                "atr_multiplier": 2.5 if score.volatility_score > 0.7 else 2.0,
                "limit_ratio": 2.5,
            }

        if score.regime == "ranging":
            return "rsi_mean_reversion", {
                "epics": [score.epic],
                "resolution": "HOUR",
                "oversold": 25,
                "overbought": 75,
                "stop_distance": 15,
                "limit_distance": 30,
            }

        # Volatile / neutral -> conservative trend following
        return "macd_trend", {
            "epics": [score.epic],
            "resolution": "HOUR",
            "atr_multiplier": 3.0,
            "limit_ratio": 2.0,
        }
