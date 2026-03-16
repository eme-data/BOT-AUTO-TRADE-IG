-- Role-based permissions migration
-- Run: docker exec -i bot-auto-trade-ig-timescaledb-1 psql -U trader -d trading_db < scripts/migrate-roles.sql

-- Add role column to admin_users (existing users get 'admin' role)
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'admin';
