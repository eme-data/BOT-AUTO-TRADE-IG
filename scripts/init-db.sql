-- ============================================================
-- Initial database schema for BOT-AUTO-TRADE-IG
-- Requires TimescaleDB extension
-- ============================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- =====================
-- Admin users
-- =====================
CREATE TABLE IF NOT EXISTS admin_users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    totp_secret     VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================
-- Application settings (key-value, encrypted sensitive fields)
-- =====================
CREATE TABLE IF NOT EXISTS app_settings (
    key         VARCHAR(100) PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    encrypted   BOOLEAN DEFAULT FALSE,
    category    VARCHAR(50) NOT NULL DEFAULT 'general',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed default settings
INSERT INTO app_settings (key, value, encrypted, category) VALUES
    ('ig_api_key', '', TRUE, 'ig'),
    ('ig_username', '', TRUE, 'ig'),
    ('ig_password', '', TRUE, 'ig'),
    ('ig_acc_type', 'DEMO', FALSE, 'ig'),
    ('ig_acc_number', '', FALSE, 'ig'),
    ('bot_max_daily_loss', '500.0', FALSE, 'risk'),
    ('bot_max_position_size', '10.0', FALSE, 'risk'),
    ('bot_max_open_positions', '5', FALSE, 'risk'),
    ('bot_max_positions_per_epic', '1', FALSE, 'risk'),
    ('bot_max_risk_per_trade_pct', '2.0', FALSE, 'risk'),
    ('bot_default_stop_distance', '20', FALSE, 'risk'),
    ('bot_default_limit_distance', '40', FALSE, 'risk'),
    ('bot_log_level', 'INFO', FALSE, 'general'),
    ('bot_status', 'stopped', FALSE, 'general'),
    ('telegram_bot_token', '', TRUE, 'notifications'),
    ('telegram_chat_id', '', FALSE, 'notifications'),
    ('ai_enabled', 'false', FALSE, 'ai'),
    ('ai_api_key', '', TRUE, 'ai'),
    ('ai_model', 'claude-sonnet-4-6', FALSE, 'ai'),
    ('ai_max_tokens', '1024', FALSE, 'ai'),
    ('ai_pre_trade_enabled', 'true', FALSE, 'ai'),
    ('ai_market_review_enabled', 'true', FALSE, 'ai'),
    ('ai_sentiment_enabled', 'false', FALSE, 'ai'),
    ('ai_post_trade_enabled', 'true', FALSE, 'ai')
ON CONFLICT (key) DO NOTHING;

-- =====================
-- Watched markets
-- =====================
CREATE TABLE IF NOT EXISTS watched_markets (
    id              SERIAL PRIMARY KEY,
    epic            VARCHAR(100) UNIQUE NOT NULL,
    instrument_name VARCHAR(255) DEFAULT '',
    instrument_type VARCHAR(50) DEFAULT '',
    expiry          VARCHAR(20) DEFAULT '-',
    currency        VARCHAR(10) DEFAULT 'EUR',
    enabled         BOOLEAN DEFAULT TRUE,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_watched_epic ON watched_markets (epic);

-- =====================
-- OHLCV time-series data
-- =====================
CREATE TABLE IF NOT EXISTS ohlcv (
    time        TIMESTAMPTZ NOT NULL,
    epic        TEXT NOT NULL,
    resolution  TEXT NOT NULL,
    open        DOUBLE PRECISION NOT NULL,
    high        DOUBLE PRECISION NOT NULL,
    low         DOUBLE PRECISION NOT NULL,
    close       DOUBLE PRECISION NOT NULL,
    volume      BIGINT DEFAULT 0
);

SELECT create_hypertable('ohlcv', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_ohlcv_epic_time ON ohlcv (epic, time DESC);
CREATE INDEX IF NOT EXISTS idx_ohlcv_resolution ON ohlcv (resolution, epic, time DESC);

ALTER TABLE ohlcv SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'epic,resolution',
    timescaledb.compress_orderby = 'time DESC'
);
SELECT add_compression_policy('ohlcv', INTERVAL '7 days', if_not_exists => TRUE);

-- =====================
-- Tick data (real-time prices)
-- =====================
CREATE TABLE IF NOT EXISTS ticks (
    time        TIMESTAMPTZ NOT NULL,
    epic        TEXT NOT NULL,
    bid         DOUBLE PRECISION,
    offer       DOUBLE PRECISION,
    spread      DOUBLE PRECISION GENERATED ALWAYS AS (offer - bid) STORED
);

SELECT create_hypertable('ticks', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_ticks_epic_time ON ticks (epic, time DESC);

ALTER TABLE ticks SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'epic',
    timescaledb.compress_orderby = 'time DESC'
);
SELECT add_compression_policy('ticks', INTERVAL '1 day', if_not_exists => TRUE);

-- =====================
-- Trades (executed orders)
-- =====================
CREATE TABLE IF NOT EXISTS trades (
    id              BIGSERIAL PRIMARY KEY,
    deal_id         TEXT UNIQUE NOT NULL,
    deal_reference  TEXT,
    epic            TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    size            DOUBLE PRECISION NOT NULL,
    open_price      DOUBLE PRECISION,
    close_price     DOUBLE PRECISION,
    stop_level      DOUBLE PRECISION,
    limit_level     DOUBLE PRECISION,
    profit          DOUBLE PRECISION,
    currency        TEXT DEFAULT 'EUR',
    strategy_name   TEXT,
    status          TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED', 'AMENDED')),
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at       TIMESTAMPTZ,
    notes           TEXT,
    metadata        JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_trades_epic ON trades (epic);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades (strategy_name);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades (status);
CREATE INDEX IF NOT EXISTS idx_trades_opened_at ON trades (opened_at DESC);

-- =====================
-- Signals (strategy signals log)
-- =====================
CREATE TABLE IF NOT EXISTS signals (
    id              BIGSERIAL PRIMARY KEY,
    time            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    epic            TEXT NOT NULL,
    strategy_name   TEXT NOT NULL,
    signal_type     TEXT NOT NULL CHECK (signal_type IN ('BUY', 'SELL', 'CLOSE', 'HOLD')),
    confidence      DOUBLE PRECISION DEFAULT 0.0,
    indicators      JSONB DEFAULT '{}',
    executed        BOOLEAN DEFAULT FALSE,
    deal_id         TEXT
);

CREATE INDEX IF NOT EXISTS idx_signals_time ON signals (time DESC);
CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals (strategy_name, time DESC);

-- =====================
-- Strategy state
-- =====================
CREATE TABLE IF NOT EXISTS strategy_state (
    name            TEXT PRIMARY KEY,
    enabled         BOOLEAN DEFAULT TRUE,
    config          JSONB DEFAULT '{}',
    state           JSONB DEFAULT '{}',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================
-- Daily P&L summary
-- =====================
CREATE TABLE IF NOT EXISTS daily_pnl (
    date            DATE NOT NULL,
    account_id      TEXT NOT NULL,
    realized_pnl    DOUBLE PRECISION DEFAULT 0.0,
    unrealized_pnl  DOUBLE PRECISION DEFAULT 0.0,
    total_trades    INTEGER DEFAULT 0,
    winning_trades  INTEGER DEFAULT 0,
    losing_trades   INTEGER DEFAULT 0,
    PRIMARY KEY (date, account_id)
);

-- =====================
-- AI Analysis Logs
-- =====================
CREATE TABLE IF NOT EXISTS ai_analysis_logs (
    id                  BIGSERIAL PRIMARY KEY,
    epic                TEXT NOT NULL,
    mode                VARCHAR(32) NOT NULL,
    verdict             VARCHAR(16) NOT NULL,
    confidence          DOUBLE PRECISION DEFAULT 0.0,
    reasoning           TEXT,
    market_summary      TEXT,
    risk_warnings       JSONB,
    suggested_adjustments JSONB,
    signal_direction    VARCHAR(8),
    signal_strategy     VARCHAR(64),
    model_used          VARCHAR(64),
    tokens_used         INTEGER DEFAULT 0,
    latency_ms          INTEGER DEFAULT 0,
    deal_id             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_logs_created ON ai_analysis_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_logs_epic ON ai_analysis_logs (epic);
CREATE INDEX IF NOT EXISTS idx_ai_logs_mode ON ai_analysis_logs (mode);
