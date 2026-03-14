-- Migration: Add AI analysis and MFA support
-- Run this on existing databases that were created before this update

-- 1. Add TOTP secret column to admin_users
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(64);

-- 2. Add SHADOW status to trades (if not already there)
ALTER TABLE trades DROP CONSTRAINT IF EXISTS trades_status_check;
ALTER TABLE trades ADD CONSTRAINT trades_status_check CHECK (status IN ('OPEN', 'CLOSED', 'AMENDED', 'SHADOW'));

-- 3. Create AI analysis logs table
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

-- 4. Seed AI settings
INSERT INTO app_settings (key, value, encrypted, category) VALUES
    ('ai_enabled', 'false', FALSE, 'ai'),
    ('ai_api_key', '', TRUE, 'ai'),
    ('ai_model', 'claude-sonnet-4-6', FALSE, 'ai'),
    ('ai_max_tokens', '1024', FALSE, 'ai'),
    ('ai_pre_trade_enabled', 'true', FALSE, 'ai'),
    ('ai_market_review_enabled', 'true', FALSE, 'ai'),
    ('ai_sentiment_enabled', 'false', FALSE, 'ai'),
    ('ai_post_trade_enabled', 'true', FALSE, 'ai')
ON CONFLICT (key) DO NOTHING;
