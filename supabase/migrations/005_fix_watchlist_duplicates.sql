-- Fix watchlist_symbols duplicate entries and constraint
-- Problem: UNIQUE(symbol, deleted_at) allows re-insertion after soft-delete,
--          creating duplicate active rows for the same symbol.
-- Solution: Drop old constraint, create proper partial unique index on (symbol)
--           WHERE deleted_at IS NULL, and clean up any stray duplicates.

BEGIN;

-- Step 1: Remove duplicate rows (keep the oldest, delete newer duplicates)
-- Identify duplicate symbols (same symbol, multiple non-deleted rows)
WITH ranked AS (
    SELECT id, symbol,
           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY created_at ASC) AS rn
    FROM watchlist_symbols
    WHERE deleted_at IS NULL
),
duplicates AS (
    SELECT id FROM ranked WHERE rn > 1
)
DELETE FROM watchlist_symbols WHERE id IN (SELECT id FROM duplicates);

-- Step 2: Drop the flawed unique constraint
ALTER TABLE watchlist_symbols DROP CONSTRAINT IF EXISTS watchlist_symbols_symbol_deleted_at_key;

-- Step 3: Create a proper partial unique index — one active symbol per symbol
-- This replaces the flawed UNIQUE(symbol, deleted_at) constraint
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_watchlist_symbols_symbol_active_unique
    ON watchlist_symbols(symbol)
    WHERE deleted_at IS NULL;

COMMIT;
