"""Pure-function strategy classifier.

Maps a set of metrics to one of four classifications:
  - "poor":     crossed a documented poor-performance threshold
  - "watch":    on the way to "poor" (warning band) or insufficient sample
  - "inactive": no closed trades yet
  - "ok":       healthy

The classifier is intentionally pure (no I/O) so it is trivially testable
and can be reused in batch jobs or notebooks.
"""

from __future__ import annotations

from dataclasses import dataclass


class Classification:
    """Enum-like constants for strategy classification."""

    OK = "ok"
    POOR = "poor"
    WATCH = "watch"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class Thresholds:
    """Tunable poor-performance thresholds.

    Defaults match the values documented in
    tasks/tra163-performance-check-workflow-plan.md §3.
    """

    max_drawdown_pct: float = 25.0
    drawdown_watch_pct: float = 15.0
    win_rate_floor: float = 0.40
    profit_factor_floor: float = 1.0
    min_trades_for_stats: int = 10
    staleness_days: int = 14


@dataclass(frozen=True)
class StrategyMetrics:
    """Subset of metrics consumed by the classifier.

    Held in its own dataclass so the classifier is decoupled from the
    checker's internal representation and can be tested in isolation.
    """

    total_pnl: float
    num_trades: int
    num_wins: int
    num_losses: int
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    days_since_last_trade: float | None  # None when num_trades == 0
    open_position_count: int


def classify_strategy(
    metrics: StrategyMetrics,
    thresholds: Thresholds | None = None,
) -> str:
    """Classify a strategy from its metrics.

    Returns one of Classification.OK/POOR/WATCH/INACTIVE.
    """
    t = thresholds or Thresholds()

    # Inactive: nothing to evaluate.
    if metrics.num_trades == 0:
        return Classification.INACTIVE

    poor_reasons: list[str] = []
    watch_reasons: list[str] = []

    # 1) Drawdown breach.
    if metrics.max_drawdown_pct > t.max_drawdown_pct:
        poor_reasons.append(
            f"drawdown {metrics.max_drawdown_pct:.1f}% > {t.max_drawdown_pct:.1f}%"
        )
    elif metrics.max_drawdown_pct > t.drawdown_watch_pct:
        watch_reasons.append(
            f"drawdown {metrics.max_drawdown_pct:.1f}% in watch band"
        )

    # 2) Win rate floor (only meaningful with a real sample).
    if metrics.num_trades >= t.min_trades_for_stats:
        if metrics.win_rate < t.win_rate_floor:
            poor_reasons.append(
                f"win rate {metrics.win_rate:.1%} < {t.win_rate_floor:.0%}"
            )

        # 3) Profit factor floor.
        if metrics.profit_factor < t.profit_factor_floor:
            poor_reasons.append(
                f"profit factor {metrics.profit_factor:.2f} < {t.profit_factor_floor:.2f}"
            )

    # 4) Staleness.
    if (
        metrics.days_since_last_trade is not None
        and metrics.days_since_last_trade > t.staleness_days
    ):
        poor_reasons.append(
            f"no trades in {metrics.days_since_last_trade:.0f} days"
        )

    # 5) Insufficient sample (1-9 trades): watch, not poor.
    if 0 < metrics.num_trades < t.min_trades_for_stats and not poor_reasons:
        watch_reasons.append(
            f"insufficient sample ({metrics.num_trades}/{t.min_trades_for_stats} trades)"
        )

    if poor_reasons:
        return Classification.POOR
    if watch_reasons:
        return Classification.WATCH
    return Classification.OK
