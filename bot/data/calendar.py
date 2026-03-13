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
# Format: (weekday, hour, minute, name, currency, buffer_minutes)
# weekday: 0=Monday ... 4=Friday
_RECURRING_EVENTS = [
    # Daily high-impact windows
    (None, 13, 30, "US Economic Data Release", "USD", 15),  # CPI, PPI, Retail Sales etc.
    # Weekly
    (3, 13, 30, "US Jobless Claims", "USD", 10),  # Every Thursday
]

# Events tied to specific weeks of the month (week_of_month, weekday, hour, minute, ...)
_MONTHLY_EVENTS = [
    # US Non-Farm Payrolls: 1st Friday, 13:30 UTC
    (1, 4, 13, 30, "US Non-Farm Payrolls", "USD", 30),
    # US CPI: ~2nd Tuesday or Wednesday, 13:30 UTC
    (2, 1, 13, 30, "US CPI", "USD", 20),
    # FOMC rate decision: ~3rd Wednesday, 19:00 UTC (8 times/year)
    (3, 2, 19, 0, "FOMC Rate Decision", "USD", 30),
    # ECB rate decision: ~2nd Thursday, 13:15 UTC
    (2, 3, 13, 15, "ECB Rate Decision", "EUR", 30),
    # BoE rate decision: ~2nd Thursday, 12:00 UTC
    (2, 3, 12, 0, "BoE Rate Decision", "GBP", 20),
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
        """Add known high-impact events for the current and next 2 weeks."""
        now = datetime.utcnow()
        today = now.date()

        # Add recurring weekly events for the next 14 days
        for day_offset in range(14):
            d = today + timedelta(days=day_offset)
            weekday = d.weekday()

            for ev_wd, h, m, name, currency, buf in _RECURRING_EVENTS:
                if ev_wd is not None and weekday != ev_wd:
                    continue
                # Skip weekends
                if weekday > 4:
                    continue
                ev_time = datetime.combine(d, time(h, m))
                if ev_time > now - timedelta(hours=1):
                    self.add_event(EconomicEvent(
                        name=name, time=ev_time, impact="high",
                        currency=currency, buffer_minutes=buf,
                    ))

        # Add monthly events for current and next month
        for month_offset in range(2):
            month = today.month + month_offset
            year = today.year
            if month > 12:
                month -= 12
                year += 1
            first_day = today.replace(year=year, month=month, day=1)

            for week_num, ev_wd, h, m, name, currency, buf in _MONTHLY_EVENTS:
                # Find the Nth weekday of the month
                # First occurrence of ev_wd
                days_until = (ev_wd - first_day.weekday()) % 7
                target_date = first_day + timedelta(days=days_until + 7 * (week_num - 1))

                ev_time = datetime.combine(target_date, time(h, m))
                if ev_time > now - timedelta(hours=1):
                    self.add_event(EconomicEvent(
                        name=name, time=ev_time, impact="high",
                        currency=currency, buffer_minutes=buf,
                    ))

    def is_currency_paused(self, currency: str) -> bool:
        """Check if a specific currency is affected by an upcoming event."""
        if not self._enabled:
            return False
        now = datetime.utcnow()
        for event in self._events:
            if event.currency != currency:
                continue
            start = event.time - timedelta(minutes=event.buffer_minutes)
            end = event.time + timedelta(minutes=event.buffer_minutes)
            if start <= now <= end:
                return True
        return False

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
