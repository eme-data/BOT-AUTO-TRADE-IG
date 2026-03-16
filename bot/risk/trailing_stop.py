from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import structlog

from bot.broker.base import BrokerClient
from bot.broker.models import Direction, Position, Tick

logger = structlog.get_logger()

# ATR multiplier for trailing distance: trail_distance = ATR * multiplier
# 1.5x ATR balances between giving room to breathe and locking profit
ATR_TRAIL_MULTIPLIER = 1.5

# Profit thresholds for tightening the trail (as multiple of initial distance)
# Once profit reaches 2x trail distance, tighten to 75% of original trail
# Once profit reaches 3x trail distance, tighten to 50% (lock more profit)
TIGHTEN_THRESHOLDS = [
    (3.0, 0.50),  # at 3x profit → tighten trail to 50%
    (2.0, 0.75),  # at 2x profit → tighten trail to 75%
]

# Breakeven activation: move stop to entry when profit reaches 1x trail distance
BREAKEVEN_MULTIPLIER = 1.0


@dataclass
class TrailingStopState:
    """Tracks trailing stop state for one position."""
    deal_id: str
    epic: str
    direction: Direction
    entry_price: float
    trail_distance: float  # points to trail behind (base distance)
    initial_trail_distance: float = 0.0  # original distance for tightening calc
    highest_price: float = 0.0  # for BUY positions
    lowest_price: float = float("inf")  # for SELL positions
    current_stop: float | None = None
    breakeven_activated: bool = False
    last_updated: datetime = field(default_factory=datetime.now)


class TrailingStopManager:
    """
    Manages dynamic trailing stops for open positions.

    Features:
    - ATR-based trail distance (when ATR is provided)
    - Auto breakeven: moves stop to entry once profit >= 1x trail distance
    - Progressive tightening: trail distance shrinks as profit grows
    - For BUY positions: stop follows the highest price - trail_distance
    - For SELL positions: stop follows the lowest price + trail_distance
    """

    def __init__(self, broker: BrokerClient, default_trail_distance: float = 20.0):
        self.broker = broker
        self.default_trail_distance = default_trail_distance
        self._tracked: dict[str, TrailingStopState] = {}

    def track_position(
        self,
        deal_id: str,
        epic: str,
        direction: Direction,
        entry_price: float,
        trail_distance: float | None = None,
        atr: float | None = None,
        initial_stop: float | None = None,
    ) -> None:
        """Start tracking trailing stop for a position.

        If *atr* is provided, trail_distance = ATR * 1.5 (dynamic).
        Otherwise uses the explicit trail_distance or the default.
        """
        if atr and atr > 0:
            dist = round(atr * ATR_TRAIL_MULTIPLIER, 2)
            logger.info("trailing_stop_atr", deal_id=deal_id, atr=atr, computed_trail=dist)
        else:
            dist = trail_distance or self.default_trail_distance

        state = TrailingStopState(
            deal_id=deal_id,
            epic=epic,
            direction=direction,
            entry_price=entry_price,
            trail_distance=dist,
            initial_trail_distance=dist,
            current_stop=initial_stop,
        )

        if direction == Direction.BUY:
            state.highest_price = entry_price
        else:
            state.lowest_price = entry_price

        self._tracked[deal_id] = state
        logger.info("trailing_stop_tracking", deal_id=deal_id, epic=epic, trail_distance=dist)

    def untrack_position(self, deal_id: str) -> None:
        """Stop tracking a position."""
        self._tracked.pop(deal_id, None)

    def on_tick(self, tick: Tick) -> list[TrailingStopState]:
        """
        Process a tick and return list of positions that need stop updates.
        Call amend_positions() after to actually update the broker.
        """
        updates = []
        for state in self._tracked.values():
            if state.epic != tick.epic:
                continue

            mid = tick.mid
            updated = False

            # --- Breakeven logic ---
            if not state.breakeven_activated:
                profit = (mid - state.entry_price) if state.direction == Direction.BUY else (state.entry_price - mid)
                if profit >= state.initial_trail_distance * BREAKEVEN_MULTIPLIER:
                    # Move stop to entry price (breakeven)
                    be_stop = state.entry_price
                    if state.current_stop is None or (
                        state.direction == Direction.BUY and be_stop > state.current_stop
                    ) or (
                        state.direction == Direction.SELL and be_stop < state.current_stop
                    ):
                        state.current_stop = be_stop
                        state.breakeven_activated = True
                        state.last_updated = datetime.now()
                        updated = True
                        logger.info("trailing_stop_breakeven", deal_id=state.deal_id, epic=state.epic, stop=be_stop)

            # --- Progressive tightening ---
            profit_pts = (mid - state.entry_price) if state.direction == Direction.BUY else (state.entry_price - mid)
            for threshold_mult, trail_factor in TIGHTEN_THRESHOLDS:
                if profit_pts >= state.initial_trail_distance * threshold_mult:
                    new_trail = round(state.initial_trail_distance * trail_factor, 2)
                    if new_trail < state.trail_distance:
                        state.trail_distance = new_trail
                    break

            # --- Standard trailing logic ---
            new_stop = None
            if state.direction == Direction.BUY:
                if mid > state.highest_price:
                    state.highest_price = mid
                    new_stop = round(mid - state.trail_distance, 2)
            else:  # SELL
                if mid < state.lowest_price:
                    state.lowest_price = mid
                    new_stop = round(mid + state.trail_distance, 2)

            if new_stop is not None:
                # Only move stop in the favorable direction
                if state.current_stop is None:
                    state.current_stop = new_stop
                    updated = True
                elif state.direction == Direction.BUY and new_stop > state.current_stop:
                    state.current_stop = new_stop
                    state.last_updated = datetime.now()
                    updated = True
                elif state.direction == Direction.SELL and new_stop < state.current_stop:
                    state.current_stop = new_stop
                    state.last_updated = datetime.now()
                    updated = True

            if updated:
                updates.append(state)

        return updates

    async def amend_positions(self, updates: list[TrailingStopState]) -> None:
        """Amend stop levels on the broker for positions that need updating."""
        for state in updates:
            try:
                await self.broker.amend_position(
                    deal_id=state.deal_id,
                    stop_level=state.current_stop,
                )
                logger.info(
                    "trailing_stop_updated",
                    deal_id=state.deal_id,
                    epic=state.epic,
                    new_stop=state.current_stop,
                    trail_distance=state.trail_distance,
                    breakeven=state.breakeven_activated,
                    highest=state.highest_price if state.direction == Direction.BUY else None,
                    lowest=state.lowest_price if state.direction == Direction.SELL else None,
                )
            except Exception as e:
                logger.error("trailing_stop_amend_error", deal_id=state.deal_id, error=str(e))

    @property
    def tracked_count(self) -> int:
        return len(self._tracked)

    def get_tracked(self) -> dict[str, TrailingStopState]:
        return dict(self._tracked)
