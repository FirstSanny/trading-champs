-- Migration: Add loop_state, strategy_state, stage_history tables
-- for replacing ephemeral SQLite state persistence with Supabase

-- 1. loop_state: single-row per strategy (null strategy_id = global loop)
CREATE TABLE IF NOT EXISTS loop_state (
    id integer PRIMARY KEY CHECK (id = 1),
    strategy_id text,
    running boolean NOT NULL DEFAULT false,
    last_run timestamptz,
    last_symbol text,
    last_signal text,
    last_action text,
    consecutive_buy_signals integer NOT NULL DEFAULT 0,
    consecutive_sell_signals integer NOT NULL DEFAULT 0,
    last_error text,
    iterations integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

-- 2. strategy_state: one row per strategy
CREATE TABLE IF NOT EXISTS strategy_state (
    strategy_id text PRIMARY KEY,
    stage text NOT NULL,
    stage_entered_at timestamptz NOT NULL,
    current_metrics jsonb NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

-- 3. stage_history: append-only log of stage transitions
CREATE TABLE IF NOT EXISTS stage_history (
    id bigserial PRIMARY KEY,
    strategy_id text NOT NULL,
    from_stage text NOT NULL,
    to_stage text NOT NULL,
    trigger text NOT NULL,
    metrics_snapshot jsonb NOT NULL DEFAULT '{}',
    timestamp timestamptz NOT NULL,
    actor text NOT NULL,
    override_reason text,
    UNIQUE(strategy_id, timestamp)
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_loop_state_strategy_id
    ON loop_state(strategy_id) WHERE strategy_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_stage_history_strategy_id
    ON stage_history(strategy_id);
CREATE INDEX IF NOT EXISTS idx_stage_history_timestamp
    ON stage_history(timestamp DESC);

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION update_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER loop_state_updated_at
    BEFORE UPDATE ON loop_state FOR EACH ROW
    EXECUTE FUNCTION update_state_updated_at();
CREATE TRIGGER strategy_state_updated_at
    BEFORE UPDATE ON strategy_state FOR EACH ROW
    EXECUTE FUNCTION update_state_updated_at();

-- RLS policies
ALTER TABLE loop_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE strategy_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE stage_history ENABLE ROW LEVEL SECURITY;

-- Public read (anyone can read state)
CREATE POLICY "Public can read loop_state" ON loop_state
    FOR SELECT USING (true);
CREATE POLICY "Public can read strategy_state" ON strategy_state
    FOR SELECT USING (true);
CREATE POLICY "Public can read stage_history" ON stage_history
    FOR SELECT USING (true);

-- Service key write (server-side code uses service key for writes)
CREATE POLICY "Service can upsert loop_state" ON loop_state
    FOR INSERT WITH CHECK (true);
CREATE POLICY "Service can update loop_state" ON loop_state
    FOR UPDATE USING (true);
CREATE POLICY "Service can upsert strategy_state" ON strategy_state
    FOR INSERT WITH CHECK (true);
CREATE POLICY "Service can update strategy_state" ON strategy_state
    FOR UPDATE USING (true);
CREATE POLICY "Service can insert stage_history" ON stage_history
    FOR INSERT WITH CHECK (true);
