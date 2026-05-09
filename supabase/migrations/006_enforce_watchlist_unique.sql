-- Enforce unique symbol constraint with proper partial unique index
--
-- The flawed UNIQUE(symbol, deleted_at) from migration 002 allowed duplicates:
-- after soft-delete (deleted_at = NOW()), a new insert with deleted_at = NULL
-- would pass the unique check, creating duplicate active rows for the same symbol.
--
-- This migration drops the broken constraint and replaces it with a
-- partial UNIQUE index that only enforces uniqueness for active rows
-- (where deleted_at IS NULL), while allowing re-insertion after soft-delete
-- (since a soft-deleted row has deleted_at set, it doesn't conflict).
--
-- ROLLBACK: Drop idx_watchlist_symbols_symbol_active_unique
--          and re-add the old constraint:
--          ALTER TABLE watchlist_symbols ADD UNIQUE(symbol, deleted_at);

BEGIN;

-- Step 1: Remove any pre-existing duplicate active rows (keep oldest)
WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY created_at ASC) AS rn
    FROM watchlist_symbols
    WHERE deleted_at IS NULL
),
duplicates AS (
    SELECT id FROM ranked WHERE rn > 1
)
DELETE FROM watchlist_symbols WHERE id IN (SELECT id FROM duplicates);

-- Step 2: Drop the broken unique constraint
ALTER TABLE watchlist_symbols DROP CONSTRAINT IF EXISTS watchlist_symbols_symbol_deleted_at_key;

-- Step 3: Create proper partial unique index — one active symbol per symbol
-- This silently replaces the broken constraint and prevents future duplicates
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_watchlist_symbols_symbol_active_unique
    ON watchlist_symbols(symbol)
    WHERE deleted_at IS NULL;

COMMIT;
