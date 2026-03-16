-- Multi-account support migration
-- Run: docker exec -i bot-auto-trade-ig-timescaledb-1 psql -U trader -d trading_db < scripts/migrate-multi-account.sql

CREATE TABLE IF NOT EXISTS ig_accounts (
    id SERIAL PRIMARY KEY,
    label VARCHAR(100) NOT NULL,
    api_key VARCHAR(255) NOT NULL,
    username VARCHAR(100) NOT NULL,
    password VARCHAR(255) NOT NULL,
    acc_type VARCHAR(10) NOT NULL DEFAULT 'LIVE',
    acc_number VARCHAR(50) DEFAULT '',
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ig_accounts_active ON ig_accounts (is_active);
