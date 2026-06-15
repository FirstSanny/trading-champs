#!/usr/bin/env python3
"""Run the trading performance checker once and print the result.

Designed for the Paperclip daily routine: invoked as
``python scripts/run_performance_check.py``.

Exit codes:
  0 — checker ran successfully
  1 — checker raised
  2 — at least one strategy classified as 'poor' (informational; wiring
        the follow-up is the routine's job)

Outputs the JSON report on stdout so the caller can post the body
straight to a Paperclip issue comment or webhook.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _resolve_tracker():
    """Reuse the API's module-level PnLTracker when available.

    The API singleton is the canonical source of truth (loads Supabase /
    Alpaca trades on first request). When this script runs out-of-band
    (cron, Paperclip heartbeats) no API has booted yet, so we fall back
    to a fresh empty tracker.
    """
    try:
        import api.index as api_index  # type: ignore[import-not-found]

        return getattr(api_index, "tracker", None)
    except Exception:
        return None


def _resolve_known_strategies():
    try:
        from trading_champs.signals.strategies import (
            DATA_STRATEGY_REGISTRY,
            STRATEGY_REGISTRY,
        )

        return list(STRATEGY_REGISTRY.keys()) + list(DATA_STRATEGY_REGISTRY.keys())
    except Exception:
        return []


def _resolve_strategy_stages():
    try:
        import api.index as api_index  # type: ignore[import-not-found]

        fn = getattr(api_index, "_collect_strategy_stages", None)
        if fn is None:
            return {}
        try:
            return fn()
        except Exception:
            return {}
    except Exception:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-append",
        action="store_true",
        help="Run the checker but do not append the report to the JSONL ledger.",
    )
    parser.add_argument(
        "--ledger",
        default=None,
        help="Override the ledger path (default: PERF_LOG_PATH env or data/performance_log.jsonl).",
    )
    args = parser.parse_args()

    try:
        from trading_champs.performance.checker import PerformanceChecker
        from trading_champs.performance.classifier import Classification
        from trading_champs.performance.ledger import PerformanceLedger
        from trading_champs.pl.tracker import PnLTracker
    except Exception as exc:  # pragma: no cover - import failure is environmental
        print(json.dumps({"error": f"import failed: {exc}"}), file=sys.stderr)
        return 1

    tracker = _resolve_tracker() or PnLTracker()
    try:
        checker = PerformanceChecker(
            tracker=tracker,
            strategy_stages=_resolve_strategy_stages(),
            known_strategies=_resolve_known_strategies(),
        )
        report = checker.run()
    except Exception as exc:
        print(
            json.dumps({"error": str(exc), "type": type(exc).__name__}),
            file=sys.stderr,
        )
        return 1

    if not args.no_append:
        path = Path(args.ledger) if args.ledger else None
        PerformanceLedger(path).append(report)

    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))

    return 2 if report.summary.get(Classification.POOR, 0) > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
