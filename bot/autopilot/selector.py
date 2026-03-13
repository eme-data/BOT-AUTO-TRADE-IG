from __future__ import annotations

from bot.autopilot.models import MarketScore


class StrategySelector:
    """Selects the best strategy for a market based on its regime and score."""

    def select(self, score: MarketScore) -> tuple[str, dict]:
        """Return (strategy_name, config_overrides) for the given market score."""
        # Score-based size factor: high score → normal size, low score → reduced
        # Range: 0.5 (at threshold 0.35) to 1.0 (at score 0.80+)
        size_factor = min(1.0, max(0.5, (score.total_score - 0.35) / 0.45 * 0.5 + 0.5))
        base = {
            "epics": [score.epic],
            "resolution": "HOUR",
            "score": score.total_score,
            "size_factor": round(size_factor, 2),
        }

        if score.regime == "trending":
            return "macd_trend", {
                **base,
                "atr_multiplier": 2.5 if score.volatility_score > 0.7 else 2.0,
                "limit_ratio": 2.5,
            }

        if score.regime == "ranging":
            return "rsi_mean_reversion", {
                **base,
                "oversold": 25,
                "overbought": 75,
                "stop_distance": 15,
                "limit_distance": 30,
            }

        # Volatile regime: choose based on momentum characteristics
        # High momentum + clear direction → MACD can catch the move
        if score.momentum_score > 0.6 and score.direction_bias != "neutral":
            return "macd_trend", {
                **base,
                "atr_multiplier": 3.0,  # wider stops for volatility
                "limit_ratio": 2.0,
            }

        # Volatile but momentum fading or directionless → mean reversion
        return "rsi_mean_reversion", {
            **base,
            "oversold": 30,
            "overbought": 70,
            "stop_distance": 20,
            "limit_distance": 40,
        }
