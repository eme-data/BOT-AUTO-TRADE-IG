from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Double,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# =====================
# Admin user (single admin account)
# =====================
class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =====================
# Application settings (key-value, sensitive values encrypted)
# =====================
class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# =====================
# Watched markets (selected epics)
# =====================
class WatchedMarket(Base):
    __tablename__ = "watched_markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    epic: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    instrument_name: Mapped[str] = mapped_column(String(255), default="")
    instrument_type: Mapped[str] = mapped_column(String(50), default="")
    expiry: Mapped[str] = mapped_column(String(20), default="-")
    currency: Mapped[str] = mapped_column(String(10), default="EUR")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_watched_epic", "epic"),
    )


# =====================
# Trades
# =====================
class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    deal_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    deal_reference: Mapped[str | None] = mapped_column(String)
    epic: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[float] = mapped_column(Double, nullable=False)
    open_price: Mapped[float | None] = mapped_column(Double)
    close_price: Mapped[float | None] = mapped_column(Double)
    stop_level: Mapped[float | None] = mapped_column(Double)
    limit_level: Mapped[float | None] = mapped_column(Double)
    profit: Mapped[float | None] = mapped_column(Double)
    currency: Mapped[str] = mapped_column(String, default="EUR")
    strategy_name: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="OPEN")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_trades_epic", "epic"),
        Index("idx_trades_strategy", "strategy_name"),
        Index("idx_trades_status", "status"),
        Index("idx_trades_opened_at", opened_at.desc()),
    )


# =====================
# Signals
# =====================
class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    epic: Mapped[str] = mapped_column(String, nullable=False)
    strategy_name: Mapped[str] = mapped_column(String, nullable=False)
    signal_type: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Double, default=0.0)
    indicators: Mapped[dict] = mapped_column(JSONB, default=dict)
    executed: Mapped[bool] = mapped_column(Boolean, default=False)
    deal_id: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        Index("idx_signals_time", time.desc()),
        Index("idx_signals_strategy", "strategy_name", time.desc()),
    )


# =====================
# Strategy state
# =====================
class StrategyState(Base):
    __tablename__ = "strategy_state"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    state: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# =====================
# Daily P&L
# =====================
class DailyPnL(Base):
    __tablename__ = "daily_pnl"

    date: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    realized_pnl: Mapped[float] = mapped_column(Double, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Double, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)


# =====================
# AI Analysis Logs
# =====================
class AIAnalysisLog(Base):
    __tablename__ = "ai_analysis_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    epic: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Double, default=0.0)
    reasoning: Mapped[str | None] = mapped_column(Text)
    market_summary: Mapped[str | None] = mapped_column(Text)
    risk_warnings: Mapped[dict | None] = mapped_column(JSONB)
    suggested_adjustments: Mapped[dict | None] = mapped_column(JSONB)
    signal_direction: Mapped[str | None] = mapped_column(String(8))
    signal_strategy: Mapped[str | None] = mapped_column(String(64))
    model_used: Mapped[str | None] = mapped_column(String(64))
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    deal_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_ai_logs_created", created_at.desc()),
        Index("idx_ai_logs_epic", "epic"),
        Index("idx_ai_logs_mode", "mode"),
    )
