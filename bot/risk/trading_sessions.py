"""Trading session hours filter.

Prevents order execution during illiquid hours (overnight gaps, weekends)
by checking whether the current UTC time falls within the active session
window for the relevant asset class.
"""

from __future__ import annotations

import datetime

# Session windows per asset class: (start_hour_utc, end_hour_utc)
# Hours are inclusive on start, exclusive on end.
SESSIONS: dict[str, tuple[int, int]] = {
    "CURRENCIES": (7, 21),   # London 07-17 + New York 12-21 combined
    "INDICES": (8, 21),      # European open to US close
    "COMMODITIES": (8, 21),  # London + New York sessions
}

DEFAULT_SESSION: tuple[int, int] = (8, 20)  # Conservative fallback


def classify_epic(epic: str, instrument_type: str = "") -> str:
    """Determine asset class from an IG epic string or instrument_type hint.

    IG epic prefixes:
      CS.D.<CCY>  -> FX / CURRENCIES
      IX.D.<IDX>  -> INDICES
      CO.D.<COM>  -> COMMODITIES  (e.g. CO.D.LCO... for Brent)
      CS.D.USCGC  -> COMMODITIES  (Gold via spread-bet)

    Falls back to *instrument_type* when the epic prefix is ambiguous.
    """
    upper_epic = epic.upper()
    upper_type = instrument_type.upper()

    # Explicit instrument_type takes priority when provided
    if upper_type:
        for key in SESSIONS:
            if key in upper_type:
                return key

    # Epic-prefix heuristics
    if upper_epic.startswith("IX.D.") or upper_epic.startswith("IX."):
        return "INDICES"
    if upper_epic.startswith("CO.D.") or upper_epic.startswith("CO."):
        return "COMMODITIES"
    # Gold / Silver spread-bet epics live under CS.D.USCGC / CS.D.USCSI
    if upper_epic.startswith("CS.D.USCGC") or upper_epic.startswith("CS.D.USCSI"):
        return "COMMODITIES"
    if upper_epic.startswith("CS.D."):
        return "CURRENCIES"

    return ""  # unknown — will use DEFAULT_SESSION


def is_market_open(epic: str, instrument_type: str = "") -> bool:
    """Return True if the market for *epic* is currently in its active session.

    Checks:
    1. Weekend (Saturday / Sunday) -> always closed.
    2. Current UTC hour against the session window for the asset class.
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    # Saturday=5, Sunday=6
    if now.weekday() >= 5:
        return False

    asset_class = classify_epic(epic, instrument_type)
    start_hour, end_hour = SESSIONS.get(asset_class, DEFAULT_SESSION)

    return start_hour <= now.hour < end_hour
