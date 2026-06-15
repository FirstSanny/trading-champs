# TRA-163 — Trading Performance Check Workflow

**Issue:** TRA-163 (Design trading performance check workflow)
**Author:** Steve (CTO)
**Date:** 2026-06-15
**Status:** Plan, pending board approval

---

## Goal

A sustainable, daily, low-touch workflow that monitors every active trading
strategy's health, persists a durable performance ledger, and surfaces
problems before they compound. The workflow must be runnable today against
the local trading-champs app (no Supabase required) and must NOT touch
live-trading execution side effects.

## Non-Goals

- No auto-execution of live trading actions.
- No Supabase dependency (TRA-104, TRA-124 cancelled).
- No new strategy implementations — this work only observes existing
  strategies and reports on them.

## Design

### 1. Inputs

The checker reads from the existing in-process `PnLTracker.trade_log`,
which already carries a `strategy` field on every `Trade`. No schema
change is needed.

Concretely:

- `tracker.trade_log.get_closed_trades()` — all closed trades (with
  attribution to the strategy that opened them).
- `tracker.trade_log.get_open_trades()` — open positions, used to
  surface staleness.
- `provider.get_strategies()` (already exposed at `GET /api/strategies`)
  — for the current stage of each strategy (`dry_run` vs `live`).
- `repo.get_all_entries()` from `WatchlistRepository` (already exposed
  at `GET /api/watchlist`) — for cross-checking trade activity vs the
  watchlist.

### 2. Canonical Metrics

Computed per strategy, per symbol, and aggregate:

| Metric | Definition | Source |
| --- | --- | --- |
| `total_pnl` | Sum of realized PnL. | `tracker.get_total_realized_pnl` filtered by strategy. |
| `num_trades` | Count of closed trades. | `len(trades)`. |
| `win_rate` | `num_wins / num_trades` (0.0 if no trades). | Filtered `trades` by `pnl > 0`. |
| `profit_factor` | `sum(wins) / abs(sum(losses))` (∞ if no losses, 0 if no wins). | Filtered `trades`. |
| `max_drawdown_pct` | Largest peak-to-trough equity drop, expressed as percent of peak equity. | Reuse `MetricsCalculator._calculate_max_drawdown`. |
| `sharpe_ratio` | Annualized mean / std of trade returns (0 if < 2 trades). | Reuse `MetricsCalculator._calculate_sharpe_ratio`. |
| `days_since_last_trade` | `(now - max(trade.exit_time))` in days. | `closed_trades`. |
| `open_position_count` | Count of currently open trades attributed to the strategy. | `open_trades`. |

### 3. Poor-Performance Thresholds

A strategy is flagged as `poor` if ANY of the following hold:

- `max_drawdown_pct > 25.0` (25% peak-to-trough drawdown).
- `win_rate < 0.40` AND `num_trades >= 10` (statistically meaningful sample).
- `days_since_last_trade > 14` (no activity in two weeks).
- `profit_factor < 1.0` AND `num_trades >= 10` (losing more than winning).

A strategy is flagged as `watch` if:

- `0 < num_trades < 10` (insufficient sample — don't act, but log).
- `max_drawdown_pct > 15.0` (warning before reaching the `poor` threshold).

Strategies with `num_trades == 0` are `inactive` and reported separately
(do not flag as poor — no signal yet).

### 4. Action Policy

`poor` strategies are subject to a `policy_action`:

- If the strategy is in `dry_run` stage: log + create a follow-up Paperclip
  issue titled "Pause/Review strategy <name> — poor performance" with a
  link to the run. **No auto-pause;** the next Paperclip heartbeat picks
  it up and a human or agent decides.
- If the strategy is in `live` stage: do nothing automatically. Emit a
  Paperclip comment on the parent project so a human sees it; live side
  effects are explicitly out of scope per the issue description.

`watch` strategies are logged but not escalated.

`inactive` strategies are logged.

### 5. Persistence

A JSONL ledger at `data/performance_log.jsonl`, one line per run:

```json
{
  "run_at": "2026-06-15T20:00:00Z",
  "strategies": {
    "bollinger": {
      "stage": "dry_run",
      "metrics": { "total_pnl": 0.0, "num_trades": 0, ... },
      "classification": "inactive"
    },
    "rsi": { ... }
  },
  "summary": { "poor": 0, "watch": 2, "inactive": 6, "ok": 0 }
}
```

Append-only, one JSON object per line. The file is gitignored; the
path is configurable via `PERF_LOG_PATH` env var, defaulting to
`data/performance_log.jsonl`.

### 6. Public Endpoints

Two new endpoints, both behind the same `API_SECRET` guard as existing
endpoints:

- `GET /api/debug/performance-summary` — returns the most recent run
  from the ledger, plus aggregate counts (poor/watch/inactive/ok
  across all known strategies). Used by dashboards or curl checks.
- `GET /api/debug/performance` — returns the last N runs (default 30,
  capped at 365). Used for trend eyeballing.

Both endpoints are read-only. The checker itself runs in two ways:

1. On-demand: `POST /api/debug/performance-run` — runs the checker
   synchronously, appends to the ledger, returns the result. Idempotent
   (safe to call twice in a row).
2. Scheduled: a small script `scripts/run_performance_check.py` that
   imports the checker and runs it. This is what the daily Paperclip
   routine (TRA-163 step 6) will invoke.

### 7. Tests

Per project standards, 80%+ coverage. New test file
`tests/test_performance_check.py`:

- `TestClassifyStrategy` — boundary cases for each threshold
  (e.g. exactly 25% drawdown = not poor, 25.01% = poor).
- `TestMetricsFromTrades` — known trade sequences produce expected
  metrics (golden values).
- `TestLedgerAppend` — append-only, no clobber, valid JSONL.
- `TestEndpointAuth` — `/api/debug/performance-summary` requires auth.
- `TestEndpointEmpty` — empty state returns 200 with zero counts.
- `TestEndToEnd` — populate trades → run checker → fetch summary → assert.

## File Layout

New files:

- `src/trading_champs/performance/__init__.py`
- `src/trading_champs/performance/checker.py` — `PerformanceChecker`
  class with `run() -> PerformanceReport`.
- `src/trading_champs/performance/ledger.py` — JSONL append/load
  helpers.
- `src/trading_champs/performance/classifier.py` — pure functions
  mapping metrics → classification + thresholds dataclass.
- `scripts/run_performance_check.py` — CLI entry.
- `tests/test_performance_check.py` — unit + integration tests.
- `tasks/tra163-performance-check-workflow-plan.md` — this file.

Touched files:

- `api/index.py` — add the three new endpoints.
- `.gitignore` — add `data/performance_log.jsonl`.

## Risks

- **Trade attribution drift.** If trades are opened by an old `strategy`
  name that has since been removed from `STRATEGY_REGISTRY`, the
  classifier will surface them under the legacy name. Mitigation: the
  classifier is permissive — any `strategy` value not in
  `STRATEGY_REGISTRY` is reported as `unknown_strategy` and listed
  separately, not classified.
- **Serverless cold start.** The local dev server (uvicorn) keeps the
  `PnLTracker` in memory; Vercel does not. The existing app already
  persists trades via `supabase_client` (when configured) and
  re-hydrates on cold start. The checker reads the in-memory tracker
  only — meaning on Vercel, a freshly cold-started container will
  report empty state. Mitigation: out of scope for this work. The
  paperclip-routine invocation is a separate concern.
- **Threshold flapping.** A strategy oscillating between `poor` and
  `watch` will create noise. Mitigation: classification is based on
  rolling 30-day window, not all-time, to reduce flapping.

## Verification

1. Run `pytest tests/test_performance_check.py -v` — all pass.
2. Run `pytest tests/ -q` — full suite still green.
3. Start the local server: `uvicorn api.index:app` (in background).
4. Open trades via the existing `/api/trades` and `/api/trades/{id}/close`
   endpoints to seed the tracker.
5. `curl -H "X-API-Key: $API_SECRET" -X POST http://localhost:8000/api/debug/performance-run` —
   expect 200 + a JSON report.
6. `curl -H "X-API-Key: $API_SECRET" http://localhost:8000/api/debug/performance-summary` —
   expect the same report back, plus appended ledger entry.
7. `cat data/performance_log.jsonl` — one valid JSON line per run.
8. Kill the server; restart; verify summary endpoint still returns the
   persisted line.

## Out of Scope (deferred)

- Auto-pausing live strategies on `poor` classification.
- The actual Paperclip daily routine (TRA-163 step 6) — once the
  checker and endpoints are merged, a separate issue can wire the
  routine.
- Supabase-backed ledger migration (in case Supabase is reintroduced
  later).

## Estimated Effort

- Implementation: ~250 lines of production code + ~250 lines of tests.
- One follow-up issue for routine wiring after merge.
