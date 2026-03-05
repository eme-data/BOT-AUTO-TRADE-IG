from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PositionResponse(BaseModel):
    deal_id: str
    epic: str
    direction: str
    size: float
    open_level: float
    stop_level: float | None = None
    limit_level: float | None = None
    currency: str = "EUR"
    profit: float = 0.0


class TradeResponse(BaseModel):
    id: int
    deal_id: str
    epic: str
    direction: str
    size: float
    open_price: float | None = None
    close_price: float | None = None
    profit: float | None = None
    strategy_name: str | None = None
    status: str
    opened_at: datetime
    closed_at: datetime | None = None
    notes: str | None = None


class SignalResponse(BaseModel):
    id: int
    time: datetime
    epic: str
    strategy_name: str
    signal_type: str
    confidence: float
    indicators: dict
    executed: bool


class StrategyResponse(BaseModel):
    name: str
    enabled: bool
    config: dict
    config_schema: dict = {}


class StrategyUpdateRequest(BaseModel):
    enabled: bool | None = None
    config: dict | None = None


class MetricsResponse(BaseModel):
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    open_positions: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    account_balance: float = 0.0


class AccountResponse(BaseModel):
    balance: float = 0.0
    deposit: float = 0.0
    profit_loss: float = 0.0
    available: float = 0.0
    currency: str = "EUR"


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.2.0"
    db: str = "unknown"
    redis: str = "unknown"
    bot: str = "unknown"
