"""PerformanceChecker — runs a single performance check and returns a report.

The checker is the only place that knows about the PnLTracker shape.
It produces immutable dataclasses that the classifier, ledger, and
HTTP layer consume without coupling to tracker internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable

from trading_champs.performance.classifier import (
    Classification,
    StrategyMetrics,
    Thresholds,
    classify_strategy,
)

if TYPE_CHECKING:
    from trading_champs.pl.tracker import PnLTracker, Trade


@dataclass(frozen=True)
class StrategySnapshot:
    """One strategy's metrics + classification for a single run."""

    name: str
    stage: str  # dry_run / paper / live / unknown
    metrics: StrategyMetrics
    classification: str
    policy_action: str  # human-readable next step
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "stage": self.stage,
            "metrics": {
                "total_pnl": self.metrics.total_pnl,
                "num_trades": self.metrics.num_trades,
                "num_wins": self.metrics.num_wins,
                "num_losses": self.metrics.num_losses,
                "win_rate": self.metrics.win_rate,
                "profit_factor": _sanitize_float(self.metrics.profit_factor),
                "max_drawdown_pct": self.metrics.max_drawdown_pct,
                "sharpe_ratio": self.metrics.sharpe_ratio,
                "days_since_last_trade": self.metrics.days_since_last_trade,
                "open_position_count": self.metrics.open_position_count,
            },
            "classification": self.classification,
            "policy_action": self.policy_action,
            "reasons": self.reasons,
        }
        return d


@dataclass(frozen=True)
class PerformanceReport:
    """A complete checker run."""

    run_at: str
    strategies: dict[str, StrategySnapshot]
    summary: dict[str, int]
    thresholds: Thresholds
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_at": self.run_at,
            "strategies": {k: v.to_dict() for k, v in self.strategies.items()},
            "summary": self.summary,
            "thresholds": {
                "max_drawdown_pct": self.thresholds.max_drawdown_pct,
                "drawdown_watch_pct": self.thresholds.drawdown_watch_pct,
                "win_rate_floor": self.thresholds.win_rate_floor,
                "profit_factor_floor": self.thresholds.profit_factor_floor,
                "min_trades_for_stats": self.thresholds.min_trades_for_stats,
                "staleness_days": self.thresholds.staleness_days,
            },
            "notes": self.notes,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize_float(value: float) -> float:
    """Clamp non-JSON-compliant floats (inf/-inf/NaN) to safe sentinels.

    profit_factor = +inf when a strategy has wins but no losses. JSON has
    no representation for that; we cap to 1e9 so downstream consumers
    see a very-large-but-finite number.
    """
    if value != value:  # NaN
        return 0.0
    if value == float("inf"):
        return 1e9
    if value == float("-inf"):
        return -1e9
    return value


def _filter_closed(trades: Iterable["Trade"]) -> list["Trade"]:
    return [t for t in trades if t.exit_price is not None and t.pnl is not None]


def _compute_metrics_for_strategy(
    closed: list["Trade"],
    open_for_strategy: list["Trade"],
    now: datetime,
) -> StrategyMetrics:
    num_trades = len(closed)
    wins = [t for t in closed if (t.pnl or 0) > 0]
    losses = [t for t in closed if (t.pnl or 0) <= 0]
    total_pnl = sum(t.pnl for t in closed if t.pnl is not None)
    num_wins = len(wins)
    num_losses = len(losses)
    win_rate = num_wins / num_trades if num_trades > 0 else 0.0

    total_wins = sum(t.pnl for t in wins if t.pnl is not None)
    total_losses = abs(sum(t.pnl for t in losses if t.pnl is not None))
    if total_losses > 0:
        profit_factor = total_wins / total_losses
        profit_factor = _sanitize_float(profit_factor)
    elif total_wins > 0:
        # No losses but realized wins — perfect record. JSON cannot
        # represent +inf, so we cap to a large but finite sentinel here.
        profit_factor = 1e9
    else:
        profit_factor = 0.0

    # Drawdown: replay equity curve from initial $10k (matches existing
    # MetricsCalculator default; threshold is relative so absolute scale
    # only matters via the percent metric).
    initial_balance = 10000.0
    running = initial_balance
    peak = initial_balance
    max_dd_pct = 0.0
    sorted_trades = sorted(
        closed, key=lambda t: t.exit_time or t.entry_time
    )
    for trade in sorted_trades:
        if trade.pnl is None:
            continue
        running += trade.pnl
        if running > peak:
            peak = running
        if peak > 0:
            dd_pct = (peak - running) / peak * 100.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

    # Sharpe: per-trade return %, annualize via sqrt(N) over a 252-day year.
    sharpe_ratio = 0.0
    returns = [
        t.pnl_percent / 100.0
        for t in closed
        if t.pnl_percent is not None
    ]
    if len(returns) >= 2:
        avg = sum(returns) / len(returns)
        var = sum((r - avg) ** 2 for r in returns) / len(returns)
        std = var**0.5
        if std > 0:
            sharpe_ratio = (avg / std) * (len(returns) ** 0.5)

    days_since_last: float | None = None
    if closed:
        last_exit = max(
            (t.exit_time for t in closed if t.exit_time is not None),
            default=None,
        )
        if last_exit is not None:
            days_since_last = max((now - last_exit).total_seconds() / 86400.0, 0.0)

    return StrategyMetrics(
        total_pnl=total_pnl,
        num_trades=num_trades,
        num_wins=num_wins,
        num_losses=num_losses,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown_pct=_sanitize_float(max_dd_pct),
        sharpe_ratio=sharpe_ratio,
        days_since_last_trade=days_since_last,
        open_position_count=len(open_for_strategy),
    )


def _policy_action(classification: str, stage: str) -> str:
    """Map (classification, stage) → human-readable next step.

    No live-trading side effects: this string is what the Paperclip
    daily routine consumes.
    """
    if classification == Classification.POOR:
        if stage in ("dry_run", "paper"):
            return (
                "create follow-up Paperclip issue 'Pause/Review strategy "
                "<name> — poor performance' (no auto-pause)"
            )
        if stage == "live":
            return "comment on parent project; live side effects out of scope"
        return "log + report"
    if classification == Classification.WATCH:
        return "log only; do not escalate"
    if classification == Classification.INACTIVE:
        return "log only; no signal yet"
    return "no action"


def _stage_for_strategy(name: str, stages: dict[str, str]) -> str:
    return stages.get(name, "unknown")


class PerformanceChecker:
    """Computes a PerformanceReport from the current PnLTracker state."""

    def __init__(
        self,
        tracker: "PnLTracker",
        strategy_stages: dict[str, str] | None = None,
        thresholds: Thresholds | None = None,
        known_strategies: Iterable[str] | None = None,
        now: datetime | None = None,
    ):
        self.tracker = tracker
        self.strategy_stages = strategy_stages or {}
        self.thresholds = thresholds or Thresholds()
        self.known_strategies = set(known_strategies or [])
        self._now = now

    def _now_dt(self) -> datetime:
        if self._now is not None:
            return self._now
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def run(self) -> PerformanceReport:
        now = self._now_dt()
        all_trades = self.tracker.trade_log.trades

        # Group by strategy. Any trade whose `strategy` is not in the
        # known set is reported under its own name (legacy support) but
        # also flagged as unknown in the report notes.
        strategies: dict[str, list] = {}
        unknown: set[str] = set()
        for t in all_trades:
            if not t.strategy:
                continue
            strategies.setdefault(t.strategy, []).append(t)
            if self.known_strategies and t.strategy not in self.known_strategies:
                unknown.add(t.strategy)

        snapshots: dict[str, StrategySnapshot] = {}
        summary = {Classification.OK: 0, Classification.POOR: 0,
                   Classification.WATCH: 0, Classification.INACTIVE: 0}

        for name, trades in strategies.items():
            closed = _filter_closed(trades)
            open_trades = [t for t in trades if t.exit_price is None]
            metrics = _compute_metrics_for_strategy(closed, open_trades, now)
            classification = classify_strategy(metrics, self.thresholds)
            stage = _stage_for_strategy(name, self.strategy_stages)
            action = _policy_action(classification, stage)
            snapshots[name] = StrategySnapshot(
                name=name,
                stage=stage,
                metrics=metrics,
                classification=classification,
                policy_action=action,
                reasons=[],
            )
            summary[classification] = summary.get(classification, 0) + 1

        notes: list[str] = []
        if unknown:
            notes.append(
                "unknown_strategy_trades: " + ", ".join(sorted(unknown))
            )

        return PerformanceReport(
            run_at=_now_iso(),
            strategies=snapshots,
            summary=summary,
            thresholds=self.thresholds,
            notes=notes,
        )
