"""VIX-based position sizing adjustment.

Fetches VIX level from IG and returns a multiplier to scale position sizes
down during high-volatility periods.
"""
from __future__ import annotations

import time
from typing import Tuple

import structlog

from bot.broker.base import BrokerClient

logger = structlog.get_logger()

# IG epic for the CBOE Volatility Index (VIX)
VIX_EPIC = "IX.D.VIX.DAILY.IP"

# Cache TTL: 1 hour
CACHE_TTL = 3600

# VIX bands → position size multiplier
VIX_BANDS: list[Tuple[float, float, str]] = [
    # (max_vix, multiplier, regime_label)
    (15, 1.0, "calm"),
    (25, 0.8, "normal"),
    (35, 0.5, "elevated"),
    (999, 0.3, "extreme"),
]


class VixMonitor:
    """Monitors VIX level and provides position sizing adjustments."""

    def __init__(self, broker: BrokerClient):
        self.broker = broker
        self._cached_vix: float | None = None
        self._cached_at: float = 0

    @property
    def vix_level(self) -> float | None:
        """Return the last known VIX level (may be stale)."""
        return self._cached_vix

    @property
    def vix_regime(self) -> str:
        """Return the current volatility regime label."""
        if self._cached_vix is None:
            return "unknown"
        for max_vix, _, label in VIX_BANDS:
            if self._cached_vix < max_vix:
                return label
        return "extreme"

    async def fetch_vix(self) -> float | None:
        """Fetch current VIX level from IG, with 1-hour cache."""
        now = time.monotonic()
        if self._cached_vix is not None and (now - self._cached_at) < CACHE_TTL:
            return self._cached_vix

        try:
            info = await self.broker.get_market_info(VIX_EPIC)
            # Mid price = (bid + offer) / 2
            vix = (info.bid + info.offer) / 2 if info.bid and info.offer else info.bid or info.offer
            if vix and vix > 0:
                self._cached_vix = vix
                self._cached_at = now
                logger.info("vix_fetched", level=round(vix, 2), regime=self.vix_regime)
                return vix
        except Exception as e:
            logger.debug("vix_fetch_failed", error=str(e))

        return self._cached_vix  # return stale value if available

    async def get_adjustment(self) -> float:
        """Return position size multiplier based on current VIX.

        Returns 1.0 (no adjustment) if VIX cannot be fetched.
        """
        vix = await self.fetch_vix()
        if vix is None:
            return 1.0

        for max_vix, multiplier, label in VIX_BANDS:
            if vix < max_vix:
                return multiplier
        return 0.3  # fallback for extreme
