from __future__ import annotations

import pandas as pd
import pandas_ta as ta

from bot.broker.models import Tick
from bot.strategies.base import AbstractStrategy, SignalResult


class MACDTrendStrategy(AbstractStrategy):
    """
    MACD Trend Following Strategy.

    Enters long when MACD line crosses above signal line (bullish crossover).
    Enters short when MACD line crosses below signal line (bearish crossover).
    Uses ATR for dynamic stop-loss placement.
    """

    def __init__(self, config: dict | None = None):
        default_config = {
            "epics": [],
            "fast_period": 12,
            "slow_period": 26,
            "signal_period": 9,
            "atr_period": 14,
            "atr_multiplier": 1.5,
            "resolution": "HOUR",
            "history_bars": 100,
            "size": 1.0,
            "limit_ratio": 2.0,  # risk:reward ratio
        }
        merged = {**default_config, **(config or {})}
        super().__init__(name="macd_trend", config=merged)

    def on_tick(self, tick: Tick) -> SignalResult | None:
        return None

    def on_bar(self, epic: str, df: pd.DataFrame) -> SignalResult | None:
        min_bars = self.config["slow_period"] + self.config["signal_period"] + 5
        if len(df) < min_bars:
            return None

        # Compute MACD
        macd_result = ta.macd(
            df["close"],
            fast=self.config["fast_period"],
            slow=self.config["slow_period"],
            signal=self.config["signal_period"],
        )
        if macd_result is None or macd_result.empty:
            return None

        macd_col = f"MACD_{self.config['fast_period']}_{self.config['slow_period']}_{self.config['signal_period']}"
        signal_col = f"MACDs_{self.config['fast_period']}_{self.config['slow_period']}_{self.config['signal_period']}"
        hist_col = f"MACDh_{self.config['fast_period']}_{self.config['slow_period']}_{self.config['signal_period']}"

        if macd_col not in macd_result.columns:
            return None

        macd_line = macd_result[macd_col]
        signal_line = macd_result[signal_col]
        histogram = macd_result[hist_col]

        # Compute ATR for dynamic stops
        atr = ta.atr(df["high"], df["low"], df["close"], length=self.config["atr_period"])
        if atr is None or atr.empty:
            return None

        current_macd = macd_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        current_signal = signal_line.iloc[-1]
        prev_signal = signal_line.iloc[-2]
        current_atr = atr.iloc[-1]
        current_price = df["close"].iloc[-1]

        indicators = {
            "macd": round(current_macd, 6),
            "signal": round(current_signal, 6),
            "histogram": round(histogram.iloc[-1], 6),
            "atr": round(current_atr, 6),
            "price": round(current_price, 5),
        }

        # Convert ATR to IG points for stop/limit distance
        # IG uses points (e.g., EUR/USD 1 pip = 1 point, Gold 1 point = 0.1)
        # For FX pairs (price < 50), ATR in price needs to be converted to points
        if current_price < 50:
            # FX pair: ATR 0.003 = 30 points (multiply by 10000 for 4-decimal pairs)
            atr_points = current_atr * 10000
        elif current_price < 500:
            # Indices like DAX: already in points
            atr_points = current_atr
        else:
            # Gold, large indices: ATR is already roughly in points
            atr_points = current_atr

        stop_distance = max(10, round(atr_points * self.config["atr_multiplier"]))
        limit_distance = round(stop_distance * self.config["limit_ratio"])

        # Apply score-based size factor from autopilot (defaults to 1.0)
        size_factor = self.config.get("size_factor", 1.0)
        effective_size = round(self.config["size"] * size_factor, 2)

        # Bullish crossover: MACD crosses above signal
        if prev_macd <= prev_signal and current_macd > current_signal:
            return SignalResult(
                signal_type="BUY",
                epic=epic,
                confidence=min(1.0, abs(current_macd - current_signal) / current_atr) if current_atr > 0 else 0.5,
                stop_distance=stop_distance,
                limit_distance=limit_distance,
                size=effective_size,
                indicators=indicators,
                reason="MACD bullish crossover",
            )

        # Bearish crossover: MACD crosses below signal
        if prev_macd >= prev_signal and current_macd < current_signal:
            return SignalResult(
                signal_type="SELL",
                epic=epic,
                confidence=min(1.0, abs(current_macd - current_signal) / current_atr) if current_atr > 0 else 0.5,
                stop_distance=stop_distance,
                limit_distance=limit_distance,
                size=effective_size,
                indicators=indicators,
                reason="MACD bearish crossover",
            )

        return SignalResult(signal_type="HOLD", epic=epic, indicators=indicators)

    def get_required_epics(self) -> list[str]:
        return self.config.get("epics", [])

    def get_required_resolution(self) -> str:
        return self.config.get("resolution", "HOUR")

    def get_required_history(self) -> int:
        return self.config.get("history_bars", 100)

    def get_config_schema(self) -> dict:
        return {
            "epics": {"type": "list", "description": "List of IG epics to trade"},
            "fast_period": {"type": "int", "default": 12, "min": 2, "max": 50},
            "slow_period": {"type": "int", "default": 26, "min": 10, "max": 100},
            "signal_period": {"type": "int", "default": 9, "min": 2, "max": 50},
            "atr_period": {"type": "int", "default": 14, "min": 5, "max": 50},
            "atr_multiplier": {"type": "float", "default": 2.0, "min": 0.5, "max": 5.0},
            "resolution": {"type": "str", "options": ["MINUTE_5", "MINUTE_15", "HOUR", "HOUR_4", "DAY"]},
            "size": {"type": "float", "default": 1.0, "min": 0.1},
            "limit_ratio": {"type": "float", "default": 2.0, "min": 1.0, "max": 5.0},
        }
