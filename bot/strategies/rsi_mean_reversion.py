from __future__ import annotations

import pandas as pd
import pandas_ta as ta

from bot.broker.models import Tick
from bot.strategies.base import AbstractStrategy, SignalResult


class RSIMeanReversionStrategy(AbstractStrategy):
    """
    RSI Mean Reversion Strategy.

    Buys when RSI drops below oversold level, sells when RSI rises above overbought level.
    Uses EMA as a trend filter to avoid counter-trend trades.
    """

    def __init__(self, config: dict | None = None):
        default_config = {
            "epics": [],
            "rsi_period": 14,
            "oversold": 30,
            "overbought": 70,
            "ema_period": 200,
            "resolution": "HOUR",
            "history_bars": 250,
            "stop_distance": 20,
            "limit_distance": 40,
            "size": 1.0,
        }
        merged = {**default_config, **(config or {})}
        super().__init__(name="rsi_mean_reversion", config=merged)
        self._last_rsi: dict[str, float] = {}

    def on_tick(self, tick: Tick) -> SignalResult | None:
        # This strategy operates on bars, not ticks
        return None

    def on_bar(self, epic: str, df: pd.DataFrame) -> SignalResult | None:
        if len(df) < self.config["ema_period"]:
            return None

        # Compute indicators
        rsi = ta.rsi(df["close"], length=self.config["rsi_period"])
        ema = ta.ema(df["close"], length=self.config["ema_period"])

        if rsi is None or ema is None or rsi.empty or ema.empty:
            return None

        current_rsi = rsi.iloc[-1]
        current_ema = ema.iloc[-1]
        current_price = df["close"].iloc[-1]
        prev_rsi = rsi.iloc[-2] if len(rsi) > 1 else current_rsi

        self._last_rsi[epic] = current_rsi

        indicators = {
            "rsi": round(current_rsi, 2),
            "ema": round(current_ema, 2),
            "price": round(current_price, 2),
        }

        # BUY: RSI crosses above oversold AND price above EMA (uptrend)
        if prev_rsi <= self.config["oversold"] < current_rsi and current_price > current_ema:
            return SignalResult(
                signal_type="BUY",
                epic=epic,
                confidence=min(1.0, (self.config["oversold"] - prev_rsi + 10) / 30),
                stop_distance=self.config["stop_distance"],
                limit_distance=self.config["limit_distance"],
                size=self.config["size"],
                indicators=indicators,
                reason=f"RSI crossed above {self.config['oversold']} (was {prev_rsi:.1f}), price above EMA",
            )

        # SELL: RSI crosses below overbought AND price below EMA (downtrend)
        if prev_rsi >= self.config["overbought"] > current_rsi and current_price < current_ema:
            return SignalResult(
                signal_type="SELL",
                epic=epic,
                confidence=min(1.0, (prev_rsi - self.config["overbought"] + 10) / 30),
                stop_distance=self.config["stop_distance"],
                limit_distance=self.config["limit_distance"],
                size=self.config["size"],
                indicators=indicators,
                reason=f"RSI crossed below {self.config['overbought']} (was {prev_rsi:.1f}), price below EMA",
            )

        return SignalResult(signal_type="HOLD", epic=epic, indicators=indicators)

    def get_required_epics(self) -> list[str]:
        return self.config.get("epics", [])

    def get_required_resolution(self) -> str:
        return self.config.get("resolution", "HOUR")

    def get_required_history(self) -> int:
        return self.config.get("history_bars", 250)

    def get_config_schema(self) -> dict:
        return {
            "epics": {"type": "list", "description": "List of IG epics to trade"},
            "rsi_period": {"type": "int", "default": 14, "min": 2, "max": 50},
            "oversold": {"type": "int", "default": 30, "min": 10, "max": 40},
            "overbought": {"type": "int", "default": 70, "min": 60, "max": 90},
            "ema_period": {"type": "int", "default": 200, "min": 10, "max": 500},
            "resolution": {"type": "str", "options": ["MINUTE_5", "MINUTE_15", "HOUR", "HOUR_4", "DAY"]},
            "stop_distance": {"type": "int", "default": 20},
            "limit_distance": {"type": "int", "default": 40},
            "size": {"type": "float", "default": 1.0, "min": 0.1},
        }
