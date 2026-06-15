"""Trading performance check workflow.

Provides a daily-cadence checker that computes per-strategy metrics
from the in-process PnLTracker, classifies each strategy against
documented thresholds, persists a JSONL ledger, and exposes read-only
HTTP endpoints for dashboard integration.

See tasks/tra163-performance-check-workflow-plan.md for the design.
"""

from trading_champs.performance.checker import (
    PerformanceChecker,
    PerformanceReport,
    StrategySnapshot,
)
from trading_champs.performance.classifier import (
    Classification,
    StrategyMetrics,
    Thresholds,
    classify_strategy,
)
from trading_champs.performance.ledger import PerformanceLedger, append_report

__all__ = [
    "Classification",
    "PerformanceChecker",
    "PerformanceLedger",
    "PerformanceReport",
    "StrategyMetrics",
    "StrategySnapshot",
    "Thresholds",
    "append_report",
    "classify_strategy",
]
