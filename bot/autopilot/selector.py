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
            "resolution": "MINUTE_15",
            "score": score.total_score,
            "size_factor": round(size_factor, 2),
        }

        if score.regime == "trending":
            return "macd_trend", {
                **base,
                "atr_multiplier": 1.5,
                "limit_ratio": 2.0,
            }

        if score.regime == "ranging":
            return "rsi_mean_reversion", {
                **base,
                "oversold": 35,
                "overbought": 65,
                "ema_period": 50,
                "stop_distance": 15,
                "limit_distance": 30,
            }

        # Volatile regime: use MACD (crossovers happen more often than RSI extremes)
        return "macd_trend", {
            **base,
            "atr_multiplier": 1.5,
            "limit_ratio": 2.0,
        }
