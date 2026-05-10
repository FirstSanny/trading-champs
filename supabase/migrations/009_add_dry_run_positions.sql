-- Migration 009: Add dry_run_positions JSONB column to loop_state
-- This column persists in-memory dry-run positions across serverless cold starts
ALTER TABLE loop_state
ADD COLUMN IF NOT EXISTS dry_run_positions JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN loop_state.dry_run_positions IS
'Dry-run mode open positions: {symbol: {"qty": float, "avg_price": float}}';