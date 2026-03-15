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


class AutoPilotScoreResponse(BaseModel):
    epic: str
    instrument_name: str = ""
    total_score: float = 0.0
    trend_score: float = 0.0
    momentum_score: float = 0.0
    volatility_score: float = 0.0
    regime: str = "neutral"
    direction_bias: str = "neutral"
    timeframe_alignment: float = 0.0
    selected_strategy: str | None = None
    sentiment_long: float | None = None
    sentiment_short: float | None = None
    is_active: bool = False
    scored_at: str = ""


class AutoPilotStatusResponse(BaseModel):
    enabled: bool = False
    shadow_mode: bool = True
    status: str = "disabled"
    last_scan: str | None = None
    active_markets: int = 0
    scores: list[AutoPilotScoreResponse] = []
    vix_level: float | None = None
    vix_regime: str = "unknown"
    vix_multiplier: float = 1.0


class AutoPilotConfigRequest(BaseModel):
    enabled: bool | None = None
    scan_interval_minutes: int | None = None
    max_active_markets: int | None = None
    min_score_threshold: float | None = None
    universe_mode: str | None = None
    search_terms: str | None = None
    api_budget_per_cycle: int | None = None
    shadow_mode: bool | None = None
