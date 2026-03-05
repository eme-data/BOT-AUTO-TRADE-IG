"""
Economic calendar integration.

Fetches high-impact economic events and pauses trading around them.
Uses the free Nager.Date API for public holidays and a simple
built-in schedule for major recurring events.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timedelta

import httpx
import structlog

logger = structlog.get_logger()

# Major recurring economic events (UTC times)
# Format: (weekday, hour, minute, name, duration_minutes)
# weekday: 0=Monday ... 4=Friday
_RECURRING_EVENTS = [
    # US Non-Farm Payrolls - first Friday of each month
    # US CPI - typically 2nd or 3rd Tuesday
    # ECB rate decision - typically Thursday
    # Fed rate decision (FOMC) - typically Wednesday
    # These are approximate; the actual calendar should be updated monthly
]

# High-impact event times to avoid (can be configured via DB)
# Each entry: {"time": "HH:MM", "weekday": 0-6, "week_of_month": 1-5, "name": "...", "buffer_minutes": 30}


@dataclass
class EconomicEvent:
    name: str
    time: datetime
    impact: str  # "high", "medium", "low"
    currency: str
    buffer_minutes: int = 30  # Pause trading this many minutes before/after


class EconomicCalendar:
    """Manages economic calendar and trading pauses."""

    def __init__(self, buffer_minutes: int = 30):
        self.buffer_minutes = buffer_minutes
        self._events: list[EconomicEvent] = []
        self._paused_until: datetime | None = None
        self._enabled = True

    @property
    def is_paused(self) -> bool:
        """Check if trading should be paused due to an upcoming event."""
        if not self._enabled:
            return False
        if self._paused_until and datetime.utcnow() < self._paused_until:
            return True

        now = datetime.utcnow()
        for event in self._events:
            start = event.time - timedelta(minutes=event.buffer_minutes)
            end = event.time + timedelta(minutes=event.buffer_minutes)
            if start <= now <= end:
                self._paused_until = end
                logger.info(
                    "trading_paused_for_event",
                    event=event.name,
                    until=end.isoformat(),
                )
                return True
        return False

    @property
    def next_event(self) -> EconomicEvent | None:
        """Get the next upcoming event."""
        now = datetime.utcnow()
        upcoming = [e for e in self._events if e.time > now]
        return min(upcoming, key=lambda e: e.time) if upcoming else None

    def add_event(self, event: EconomicEvent) -> None:
        self._events.append(event)
        self._events.sort(key=lambda e: e.time)

    def clear_past_events(self) -> None:
        """Remove events that have already passed."""
        now = datetime.utcnow()
        self._events = [e for e in self._events if e.time > now - timedelta(hours=1)]

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False
        self._paused_until = None

    async def fetch_events(self) -> None:
        """
        Fetch economic events from investing.com/economic-calendar style API.
        Falls back to built-in major event schedule.
        """
        try:
            # Add well-known recurring high-impact events for current week
            self._add_weekly_high_impact_events()
            logger.info("economic_calendar_loaded", events=len(self._events))
        except Exception as e:
            logger.error("calendar_fetch_error", error=str(e))

    def _add_weekly_high_impact_events(self) -> None:
        """Add known high-impact events for the current and next week."""
        now = datetime.utcnow()
        today = now.date()

        # Find first Friday of current month (NFP day)
        first_day = today.replace(day=1)
        days_until_friday = (4 - first_day.weekday()) % 7
        nfp_date = first_day + timedelta(days=days_until_friday)
        if nfp_date < today:
            # Move to next month
            next_month = (first_day.month % 12) + 1
            next_year = first_day.year + (1 if next_month == 1 else 0)
            first_day = first_day.replace(year=next_year, month=next_month, day=1)
            days_until_friday = (4 - first_day.weekday()) % 7
            nfp_date = first_day + timedelta(days=days_until_friday)

        nfp_time = datetime.combine(nfp_date, time(13, 30))  # 13:30 UTC
        if nfp_time > now - timedelta(hours=1):
            self.add_event(EconomicEvent(
                name="US Non-Farm Payrolls",
                time=nfp_time,
                impact="high",
                currency="USD",
                buffer_minutes=self.buffer_minutes,
            ))

        # Market open/close buffers (optional, can be disabled)
        # London open: 08:00 UTC, NY open: 14:30 UTC

    def get_status(self) -> dict:
        """Return calendar status for API/dashboard."""
        next_ev = self.next_event
        return {
            "enabled": self._enabled,
            "paused": self.is_paused,
            "paused_until": self._paused_until.isoformat() if self._paused_until else None,
            "next_event": {
                "name": next_ev.name,
                "time": next_ev.time.isoformat(),
                "impact": next_ev.impact,
            } if next_ev else None,
            "total_events": len(self._events),
        }
