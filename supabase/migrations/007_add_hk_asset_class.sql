-- Add 'hk' to the asset_class CHECK constraint
-- The watchlist supports HK stocks (e.g. 0100.HK) but the original CHECK
-- only allowed 'crypto', 'stock', 'etf'.

BEGIN;

ALTER TABLE watchlist_symbols DROP CONSTRAINT IF EXISTS watchlist_symbols_asset_class_check;
ALTER TABLE watchlist_symbols ADD CONSTRAINT watchlist_symbols_asset_class_check
    CHECK (asset_class IN ('crypto', 'stock', 'etf', 'hk'));

COMMIT;
