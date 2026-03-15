from __future__ import annotations

from datetime import datetime, timedelta

import structlog

from bot.broker.base import BrokerClient
from bot.broker.models import Direction, OrderRequest, Position
from bot.risk.models import RiskConfig
from bot.risk.vix_monitor import VixMonitor
from bot.strategies.base import SignalResult

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Correlation groups – epics sharing a group should not be open in the same
# direction at the same time.  Keys are group names, values are substring
# patterns matched against the uppercase epic string.
# ---------------------------------------------------------------------------
CORRELATION_GROUPS: dict[str, list[str]] = {
    # FX – USD longs (selling USD): these pairs move together
    "fx_usd_long": ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"],
    # FX – USD shorts (buying USD / safe-haven JPY)
    "fx_jpy": ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY"],
    # Commodities – precious metals
    "precious_metals": ["GOLD", "XAUUSD", "SILVER", "XAGUSD"],
    # Commodities – energy
    "energy": ["OIL", "BRENT", "CRUDE", "NGAS"],
    # US indices
    "us_indices": ["US500", "SPTRD", "WALL", "DOW", "USTECH", "NDAQ", "US 500", "WALL STREET", "US TECH"],
    # European indices
    "eu_indices": ["FTSE", "DAX", "GERMANY", "CAC", "FRANCE"],
}


def _get_correlation_group(epic: str) -> str | None:
    """Return the correlation group name for *epic*, or None if it doesn't
    belong to any known group."""
    epic_upper = epic.upper()
    for group_name, patterns in CORRELATION_GROUPS.items():
        for pattern in patterns:
            if pattern in epic_upper:
                return group_name
    return None


class RiskManager:
    """Manages risk by validating signals before execution."""

    def __init__(self, broker: BrokerClient, config: RiskConfig | None = None):
        self.broker = broker
        self.config = config or RiskConfig()
        self.vix_monitor = VixMonitor(broker)
        self._daily_pnl: float = 0.0
        self._daily_reset: datetime = datetime.now()

    async def validate_signal(self, signal: SignalResult) -> OrderRequest | None:
        """Validate a signal against risk rules. Returns OrderRequest if approved, None if rejected."""

        # Reset daily P&L counter at midnight
        now = datetime.now()
        if now.date() > self._daily_reset.date():
            self._daily_pnl = 0.0
            self._daily_reset = now

        # Check daily loss limit
        if self._daily_pnl <= -self.config.max_daily_loss:
            logger.warning("risk_daily_loss_exceeded", pnl=self._daily_pnl, limit=self.config.max_daily_loss)
            return None

        # Get current positions
        positions = await self.broker.get_open_positions()

        # Check max open positions
        if len(positions) >= self.config.max_open_positions:
            logger.warning("risk_max_positions", count=len(positions), limit=self.config.max_open_positions)
            return None

        # Check max positions per epic
        epic_positions = [p for p in positions if p.epic == signal.epic]
        if len(epic_positions) >= self.config.max_positions_per_epic:
            logger.warning("risk_max_per_epic", epic=signal.epic, count=len(epic_positions))
            return None

        # Check for opposite direction (avoid hedging)
        for pos in epic_positions:
            if (signal.signal_type == "BUY" and pos.direction == Direction.SELL) or \
               (signal.signal_type == "SELL" and pos.direction == Direction.BUY):
                logger.info("risk_opposite_position_exists", epic=signal.epic, direction=pos.direction)
                return None

        # Check correlation – block same-direction trades on correlated epics
        signal_group = _get_correlation_group(signal.epic)
        if signal_group is not None:
            signal_direction = Direction.BUY if signal.signal_type == "BUY" else Direction.SELL
            for pos in positions:
                if pos.epic == signal.epic:
                    continue  # same-epic is already handled above
                if _get_correlation_group(pos.epic) == signal_group and pos.direction == signal_direction:
                    logger.warning(
                        "risk_correlated_position",
                        epic=signal.epic,
                        conflicting_epic=pos.epic,
                        group=signal_group,
                        direction=signal_direction.value,
                    )
                    return None

        # Calculate position size
        size = await self._calculate_size(signal)
        if size <= 0:
            return None

        # Build order
        direction = Direction.BUY if signal.signal_type == "BUY" else Direction.SELL
        stop_distance = signal.stop_distance or self.config.default_stop_distance
        limit_distance = signal.limit_distance or self.config.default_limit_distance

        return OrderRequest(
            epic=signal.epic,
            direction=direction,
            size=size,
            stop_distance=stop_distance,
            limit_distance=limit_distance,
        )

    async def _calculate_size(self, signal: SignalResult) -> float:
        """Calculate position size based on risk rules."""
        if signal.size:
            return min(signal.size, self.config.max_position_size)

        # Risk-based sizing: risk X% of balance per trade
        try:
            balance = await self.broker.get_account_balance()
            account_balance = balance.get("balance", 0)
            if account_balance <= 0:
                return self.config.max_position_size

            risk_amount = account_balance * (self.config.max_risk_per_trade_pct / 100)
            stop_distance = signal.stop_distance or self.config.default_stop_distance

            if stop_distance > 0:
                size = risk_amount / stop_distance
                size = min(size, self.config.max_position_size)

                # Apply VIX-based adjustment
                vix_mult = await self.vix_monitor.get_adjustment()
                if vix_mult < 1.0:
                    logger.info(
                        "vix_size_adjustment",
                        original=round(size, 2),
                        multiplier=vix_mult,
                        adjusted=round(size * vix_mult, 2),
                        vix=self.vix_monitor.vix_level,
                        regime=self.vix_monitor.vix_regime,
                    )
                    size *= vix_mult

                return size
        except Exception as e:
            logger.error("size_calculation_error", error=str(e))

        return min(1.0, self.config.max_position_size)

    def update_daily_pnl(self, profit: float) -> None:
        self._daily_pnl += profit
        logger.info("daily_pnl_updated", daily_pnl=self._daily_pnl, trade_pnl=profit)

    async def check_and_close_losing_positions(self) -> list[str]:
        """Check for positions that should be closed based on risk rules."""
        closed = []
        positions = await self.broker.get_open_positions()
        for pos in positions:
            # Emergency close if daily loss exceeded
            if self._daily_pnl <= -self.config.max_daily_loss:
                result = await self.broker.close_position(pos.deal_id, pos.direction.value, pos.size)
                closed.append(pos.deal_id)
                logger.warning("emergency_close", deal_id=pos.deal_id, reason="daily_loss_limit")
        return closed
