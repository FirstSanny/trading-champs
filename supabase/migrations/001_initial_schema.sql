-- Supabase schema for trading_champs P&L tracking
-- Run this in the Supabase SQL Editor to create required tables

-- Trades table
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('long', 'short')),
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    entry_time TIMESTAMPTZ NOT NULL,
    exit_time TIMESTAMPTZ,
    pnl REAL,
    pnl_percent REAL,
    strategy TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Daily P&L summary table
CREATE TABLE IF NOT EXISTS daily_pnl (
    date DATE PRIMARY KEY,
    realized_pnl REAL NOT NULL DEFAULT 0,
    unrealized_pnl REAL NOT NULL DEFAULT 0,
    total_pnl REAL NOT NULL DEFAULT 0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    win_count INTEGER NOT NULL DEFAULT 0,
    loss_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Account balances history
CREATE TABLE IF NOT EXISTS account_balances (
    id BIGSERIAL PRIMARY KEY,
    balance REAL NOT NULL,
    equity REAL NOT NULL,
    mode TEXT NOT NULL DEFAULT 'paper' CHECK (mode IN ('paper', 'live')),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_account_balances_mode_recorded ON account_balances(mode, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_daily_pnl_date ON daily_pnl(date DESC);

-- Enable RLS (Row Level Security) - adjust policies as needed
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_pnl ENABLE ROW LEVEL SECURITY;
ALTER TABLE account_balances ENABLE ROW LEVEL SECURITY;

-- Public read access (for dashboard)
CREATE POLICY "Public can read trades" ON trades FOR SELECT USING (true);
CREATE POLICY "Public can read daily_pnl" ON daily_pnl FOR SELECT USING (true);
CREATE POLICY "Public can read account_balances" ON account_balances FOR SELECT USING (true);

-- Service key can do everything (for backend writes)
CREATE POLICY "Service can insert trades" ON trades FOR INSERT WITH CHECK (true);
CREATE POLICY "Service can update trades" ON trades FOR UPDATE USING (true);
CREATE POLICY "Service can delete trades" ON trades FOR DELETE USING (true);
CREATE POLICY "Service can insert daily_pnl" ON daily_pnl FOR INSERT WITH CHECK (true);
CREATE POLICY "Service can update daily_pnl" ON daily_pnl FOR UPDATE USING (true);
CREATE POLICY "Service can insert account_balances" ON account_balances FOR INSERT WITH CHECK (true);
