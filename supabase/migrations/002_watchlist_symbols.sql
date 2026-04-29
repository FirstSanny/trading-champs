-- Watchlist symbols table for AI agent-driven symbol management
-- Enables dynamic addition/removal of symbols without env var changes

-- ROLLBACK: DROP TABLE IF EXISTS watchlist_symbols;

CREATE TABLE IF NOT EXISTS watchlist_symbols (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('crypto', 'stock', 'etf')),
    enabled BOOLEAN NOT NULL DEFAULT true,
    added_by TEXT NOT NULL DEFAULT 'manual',
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    UNIQUE(symbol, deleted_at)
);

-- Index for fetching enabled (non-deleted) symbols
CREATE INDEX IF NOT EXISTS idx_watchlist_symbols_enabled
    ON watchlist_symbols(symbol)
    WHERE deleted_at IS NULL;

-- Index for listing (includes soft-deleted for audit)
CREATE INDEX IF NOT EXISTS idx_watchlist_symbols_deleted
    ON watchlist_symbols(deleted_at);

-- Updated_at trigger helper
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER watchlist_symbols_updated_at
    BEFORE UPDATE ON watchlist_symbols
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- RLS
ALTER TABLE watchlist_symbols ENABLE ROW LEVEL SECURITY;

-- Public can read enabled symbols
CREATE POLICY "Public can read enabled watchlist" ON watchlist_symbols
    FOR SELECT USING (deleted_at IS NULL AND enabled = true);

-- Service key can do everything
CREATE POLICY "Service can insert watchlist_symbols" ON watchlist_symbols
    FOR INSERT WITH CHECK (true);
CREATE POLICY "Service can update watchlist_symbols" ON watchlist_symbols
    FOR UPDATE USING (true);
CREATE POLICY "Service can delete watchlist_symbols" ON watchlist_symbols
    FOR DELETE USING (true);
