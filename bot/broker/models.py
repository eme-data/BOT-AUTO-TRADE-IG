from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass
class Tick:
    epic: str
    bid: float
    offer: float
    time: datetime
    spread: float = 0.0

    def __post_init__(self):
        self.spread = self.offer - self.bid

    @property
    def mid(self) -> float:
        return (self.bid + self.offer) / 2


@dataclass
class MarketInfo:
    epic: str
    instrument_name: str
    instrument_type: str
    expiry: str
    bid: float
    offer: float
    high: float
    low: float
    percentage_change: float
    market_status: str
    min_deal_size: float = 0.0
    min_stop_distance: float = 0.0
    lot_size: float = 1.0
    currency: str = "EUR"
    scaling_factor: float = 1.0


@dataclass
class Position:
    deal_id: str
    epic: str
    direction: Direction
    size: float
    open_level: float
    stop_level: float | None = None
    limit_level: float | None = None
    currency: str = "EUR"
    created_at: datetime | None = None
    profit: float = 0.0


@dataclass
class OrderRequest:
    epic: str
    direction: Direction
    size: float
    order_type: OrderType = OrderType.MARKET
    currency: str = "EUR"
    expiry: str = "DFB"
    stop_distance: int | None = None
    limit_distance: int | None = None
    level: float | None = None
    force_open: bool = False
    guaranteed_stop: bool = False


@dataclass
class OrderResult:
    deal_reference: str
    deal_id: str | None = None
    status: str = "UNKNOWN"
    reason: str = ""
    affected_deals: list[dict] = field(default_factory=list)


@dataclass
class OHLCV:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
