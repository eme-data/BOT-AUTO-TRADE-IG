from __future__ import annotations

import asyncio
from datetime import datetime

import pandas as pd
import structlog

from bot.autopilot.models import MarketScore
from bot.broker.ig_rest import IGRestClient
from bot.data.indicators import add_all_indicators

logger = structlog.get_logger()

# Timeframe weights: daily most important, then H4, then H1
TF_WEIGHTS = {"DAY": 0.40, "HOUR_4": 0.35, "HOUR": 0.25}


class MarketScorer:
    """Scores markets using multi-timeframe technical analysis."""

    def __init__(self, broker: IGRestClient):
        self.broker = broker

    async def score_market(self, epic: str, instrument_name: str = "") -> MarketScore:
        """Fetch H1/H4/D1 data and compute composite score."""
        scores_by_tf: dict[str, dict] = {}

        for tf in ("HOUR", "HOUR_4", "DAY"):
            try:
                bars = await self.broker.get_historical_prices(epic, tf, 100)
                if len(bars) < 50:
                    continue
                df = self._bars_to_df(bars)
                df = add_all_indicators(df)
                scores_by_tf[tf] = self._score_timeframe(df)
                await asyncio.sleep(1.5)  # rate limit spacing
            except Exception as e:
                logger.debug("score_tf_error", epic=epic, tf=tf, error=str(e))

        if not scores_by_tf:
            return MarketScore(epic=epic, instrument_name=instrument_name)

        return self._combine_scores(epic, instrument_name, scores_by_tf)

    def _bars_to_df(self, bars) -> pd.DataFrame:
        """Convert OHLCV list to pandas DataFrame."""
        data = []
        for b in bars:
            data.append({
                "time": b.time,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            })
        df = pd.DataFrame(data)
        if not df.empty:
            df.set_index("time", inplace=True)
            df.sort_index(inplace=True)
        return df

    def _score_timeframe(self, df: pd.DataFrame) -> dict:
        """Score a single timeframe."""
        price = df["close"].iloc[-1]

        # --- Trend Score ---
        adx = self._safe_get(df, "ADX_14")
        ema_20 = self._safe_get(df, "EMA_20")
        ema_50 = self._safe_get(df, "EMA_50")
        ema_200 = self._safe_get(df, "EMA_200")

        # ADX component: 0 at ADX=10, 1 at ADX=40+
        adx_score = max(0.0, min(1.0, (adx - 10) / 30)) if adx else 0.0

        # EMA alignment
        bullish = ema_20 and ema_50 and ema_200 and price > ema_20 > ema_50 > ema_200
        bearish = ema_20 and ema_50 and ema_200 and price < ema_20 < ema_50 < ema_200
        ema_score = 1.0 if (bullish or bearish) else 0.4

        trend_score = (adx_score * 0.6) + (ema_score * 0.4)

        # --- Momentum Score ---
        rsi = self._safe_get(df, "RSI_14") or 50
        rsi_trend = 1.0 - abs(rsi - 50) / 50
        rsi_reversion = abs(rsi - 50) / 50

        macd_h = self._safe_series(df, "MACDh_12_26_9")
        macd_momentum = 0.5
        if macd_h is not None and len(macd_h) >= 2:
            cur_h, prev_h = macd_h.iloc[-1], macd_h.iloc[-2]
            if abs(cur_h) > abs(prev_h):
                macd_momentum = 0.8
            else:
                macd_momentum = 0.3

        momentum_score = (max(rsi_trend, rsi_reversion) * 0.5) + (macd_momentum * 0.5)

        # --- Volatility Score ---
        atr = self._safe_get(df, "ATRr_14") or self._safe_get(df, "atr_14") or 0
        atr_pct = (atr / price * 100) if price > 0 else 0

        if 0.5 <= atr_pct <= 2.0:
            vol_score = 1.0
        elif atr_pct < 0.5:
            vol_score = atr_pct / 0.5 if atr_pct > 0 else 0.0
        else:
            vol_score = max(0.2, 1.0 - (atr_pct - 2.0) / 3.0)

        # --- Regime ---
        if adx and adx > 25 and (bullish or bearish):
            regime = "trending"
        elif adx and adx < 20:
            regime = "ranging"
        else:
            regime = "volatile"

        direction = "bullish" if ema_50 and price > ema_50 else (
            "bearish" if ema_50 and price < ema_50 else "neutral"
        )

        return {
            "trend": trend_score,
            "momentum": momentum_score,
            "volatility": vol_score,
            "regime": regime,
            "direction": direction,
        }

    def _combine_scores(
        self, epic: str, instrument_name: str, scores_by_tf: dict[str, dict]
    ) -> MarketScore:
        """Combine multi-timeframe scores into a composite MarketScore."""
        trend = sum(
            s["trend"] * TF_WEIGHTS.get(tf, 0.33)
            for tf, s in scores_by_tf.items()
        )
        momentum = sum(
            s["momentum"] * TF_WEIGHTS.get(tf, 0.33)
            for tf, s in scores_by_tf.items()
        )
        volatility = sum(
            s["volatility"] * TF_WEIGHTS.get(tf, 0.33)
            for tf, s in scores_by_tf.items()
        )

        # Timeframe alignment: bonus if all agree on direction
        directions = [s["direction"] for s in scores_by_tf.values()]
        alignment = 1.0 if len(set(directions)) == 1 and directions[0] != "neutral" else 0.5

        # Dominant regime from daily (or highest available)
        for tf_pref in ("DAY", "HOUR_4", "HOUR"):
            if tf_pref in scores_by_tf:
                regime = scores_by_tf[tf_pref]["regime"]
                break
        else:
            regime = "neutral"

        direction = directions[0] if len(set(directions)) == 1 else "neutral"

        total = (trend * 0.35) + (momentum * 0.25) + (volatility * 0.15) + (alignment * 0.25)

        return MarketScore(
            epic=epic,
            instrument_name=instrument_name,
            total_score=round(total, 3),
            trend_score=round(trend, 3),
            momentum_score=round(momentum, 3),
            volatility_score=round(volatility, 3),
            regime=regime,
            direction_bias=direction,
            timeframe_alignment=round(alignment, 3),
            scored_at=datetime.utcnow(),
        )

    @staticmethod
    def _safe_get(df: pd.DataFrame, col: str) -> float | None:
        """Safely get last value of a column."""
        if col in df.columns:
            val = df[col].iloc[-1]
            if pd.notna(val):
                return float(val)
        return None

    @staticmethod
    def _safe_series(df: pd.DataFrame, col: str) -> pd.Series | None:
        if col in df.columns:
            return df[col].dropna()
        return None
