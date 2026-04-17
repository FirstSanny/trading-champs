"""StageEvaluator computes quantitative gates and triggers promotion/demotion."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from trading_champs.core.stage_config import STAGE_CONFIGS, get_stage_config, next_stage
from trading_champs.core.stage_history import StageHistory, StageTransition

logger = logging.getLogger(__name__)


@dataclass
class StrategyMetrics:
    """Metrics computed from a strategy's PnLTracker for a given stage."""

    total_trades: int
    win_rate: float
    current_drawdown_pct: float
    sharpe_ratio: Optional[float]
    days_in_stage: int
    total_pnl_pct: float


@dataclass
class DataStrategyMetrics:
    """Signal-quality metrics for data-driven strategy stage gates."""

    total_signals: int  # non-neutral signals only
    buy_rate: float  # BUY / total_non_neutral
    neutral_rate: float  # neutral / total_signals
    consecutive_neutral: int  # capped at 15
    days_in_stage: int

    @property
    def buy_count(self) -> int:
        return int(self.buy_rate * self.total_signals) if self.total_signals > 0 else 0

    @property
    def sell_count(self) -> int:
        return self.total_signals - self.buy_count


class StageEvaluator:
    """Evaluates quantitative gates and triggers stage transitions.

    After each Orchestrator.iterate_all(), StageEvaluator.evaluate_all() is called
    for each strategy. Promotion requires all gates to be met. Demotion occurs
    when drawdown exceeds the stage's max_drawdown_pct.
    """

    def __init__(
        self,
        stage_history: StageHistory,
        evaluate_mode: bool = False,
    ):
        """Initialize StageEvaluator.

        Args:
            stage_history: StageHistory instance for logging transitions.
            evaluate_mode: If True, evaluate gates but do NOT trigger transitions.
        """
        self._history = stage_history
        self._evaluate_mode = evaluate_mode

    def evaluate(
        self,
        strategy_id: str,
        current_stage: str,
        stage_entered_at: datetime,
        metrics: StrategyMetrics,
        consecutive_demotions: int = 0,
    ) -> Optional[StageTransition]:
        """Evaluate a single strategy's stage gates.

        Args:
            strategy_id: Strategy identifier.
            current_stage: Current stage name.
            stage_entered_at: When the strategy entered the current stage.
            metrics: Computed strategy metrics.

        Returns:
            StageTransition if a promotion or demotion occurred, None otherwise.
        """
        config = get_stage_config(current_stage)
        days_in_stage = max(0, (datetime.utcnow() - stage_entered_at).days)

        # Archived strategies are never re-evaluated automatically
        if current_stage == "archived":
            return None

        # --- Archival triggers ---

        # Trigger 1: Consecutive demotions exceeded limit
        if (
            config.consecutive_demote_limit > 0
            and consecutive_demotions >= config.consecutive_demote_limit
        ):
            logger.warning(
                f"Strategy {strategy_id} archived: {consecutive_demotions} consecutive demotions "
                f"(limit={config.consecutive_demote_limit})"
            )
            return self._transition(
                strategy_id,
                current_stage,
                "archived",
                "auto_archive_consecutive_demotions",
                metrics,
            )

        # Trigger 2: Stalled in dry_run — too many days, too few trades
        if (
            current_stage == "dry_run"
            and config.dry_run_archive_after_days > 0
            and config.dry_run_archive_min_trades > 0
            and days_in_stage > config.dry_run_archive_after_days
            and metrics.total_trades < config.dry_run_archive_min_trades
        ):
            logger.warning(
                f"Strategy {strategy_id} archived: in dry_run {days_in_stage} days "
                f"with only {metrics.total_trades} trades "
                f"(min_trades={config.dry_run_archive_min_trades}, "
                f"max_days={config.dry_run_archive_after_days})"
            )
            return self._transition(
                strategy_id,
                current_stage,
                "archived",
                "auto_archive_stalled_dry_run",
                metrics,
            )

        # --- Normal gate evaluation ---

        # Check if current drawdown exceeds max for immediate demotion
        if metrics.current_drawdown_pct > config.max_drawdown_pct:
            demote_stage = config.demotes_to
            # If demote_stage == current_stage, already at minimum — no-op
            if demote_stage == current_stage:
                logger.info(f"Strategy {strategy_id} at {current_stage}, cannot demote further")
                return None
            logger.warning(
                f"Strategy {strategy_id} demoted from {current_stage} to {demote_stage}: "
                f"drawdown {metrics.current_drawdown_pct:.2f}% exceeds "
                f"max {config.max_drawdown_pct}%"
            )
            return self._transition(
                strategy_id,
                current_stage,
                demote_stage,
                "auto_demotion",
                metrics,
            )

        # Check if all promotion gates are met
        gates_met = config.gates_met(
            total_trades=metrics.total_trades,
            win_rate=metrics.win_rate,
            current_drawdown_pct=metrics.current_drawdown_pct,
            days_in_stage=days_in_stage,
            sharpe_ratio=metrics.sharpe_ratio,
        )

        if not gates_met:
            return None

        # Try to promote to next stage
        next_stage_name = next_stage(current_stage)
        if next_stage_name is None:
            logger.info(
                f"Strategy {strategy_id} is at final stage ({current_stage}) with gates met"
            )
            return None

        logger.info(
            f"Strategy {strategy_id} promoted from {current_stage} to {next_stage_name}: "
            f"trades={metrics.total_trades}, win_rate={metrics.win_rate:.2f}, "
            f"drawdown={metrics.current_drawdown_pct:.2f}%, days={days_in_stage}"
        )
        return self._transition(
            strategy_id,
            current_stage,
            next_stage_name,
            "auto_promotion",
            metrics,
        )

    def evaluate_signal_metrics(
        self,
        strategy_id: str,
        current_stage: str,
        stage_entered_at: datetime,
        metrics: DataStrategyMetrics,
        consecutive_neutral: int = 0,
    ) -> Optional[StageTransition]:
        """Evaluate signal-quality gates for data-driven strategies.

        Data strategies use BUY rate and neutral rate instead of trade P&L metrics.
        Gates:
          - dry_run: entry state
          - paper: >=10 signals, BUY rate >30%
          - live_stage_1: >=20 signals, BUY rate >40%, neutral rate <50%
          - live_stage_2: >=50 signals, BUY rate >50%, neutral rate <40%
          - archived: BUY rate <=20% over last 30 signals OR consecutive_neutral >=15

        Args:
            strategy_id: Strategy identifier.
            current_stage: Current stage name.
            stage_entered_at: When the strategy entered the current stage.
            metrics: Signal-quality metrics for this data strategy.
            consecutive_neutral: Current consecutive neutral signal count.

        Returns:
            StageTransition if a promotion or demotion occurred, None otherwise.
        """
        _ = get_stage_config(current_stage)
        max(0, (datetime.utcnow() - stage_entered_at).days)

        # Archived strategies are never re-evaluated automatically
        if current_stage == "archived":
            return None

        # --- Archival triggers ---

        # Auto-archive if consecutive neutral >= 15
        if consecutive_neutral >= 15:
            logger.warning(
                f"Strategy {strategy_id} archived: {consecutive_neutral} consecutive neutral "
                f"signals (limit=15)"
            )
            return self._transition_signal(
                strategy_id,
                current_stage,
                "archived",
                "auto_archive_consecutive_neutral",
                metrics,
            )

        # Auto-archive if BUY rate <= 20% over last 30 signals
        if metrics.total_signals >= 30 and metrics.buy_rate <= 0.20:
            logger.warning(
                f"Strategy {strategy_id} archived: BUY rate {metrics.buy_rate:.1%} <= 20% "
                f"over {metrics.total_signals} signals"
            )
            return self._transition_signal(
                strategy_id,
                current_stage,
                "archived",
                "auto_archive_low_buy_rate",
                metrics,
            )

        # --- Stage-specific gate evaluation ---

        if current_stage == "dry_run":
            # Promotion: >=10 signals, BUY rate > 30%
            if metrics.total_signals >= 10 and metrics.buy_rate > 0.30:
                return self._transition_signal(
                    strategy_id,
                    current_stage,
                    "paper",
                    "auto_promotion",
                    metrics,
                )

        elif current_stage == "paper":
            # Promotion: >=20 signals, BUY rate >40%, neutral rate <50%
            if (
                metrics.total_signals >= 20
                and metrics.buy_rate > 0.40
                and metrics.neutral_rate < 0.50
            ):
                return self._transition_signal(
                    strategy_id,
                    current_stage,
                    "live_stage_1",
                    "auto_promotion",
                    metrics,
                )

        elif current_stage == "live_stage_1":
            # Promotion: >=50 signals, BUY rate >50%, neutral rate <40%
            if (
                metrics.total_signals >= 50
                and metrics.buy_rate > 0.50
                and metrics.neutral_rate < 0.40
            ):
                return self._transition_signal(
                    strategy_id,
                    current_stage,
                    "live_stage_2",
                    "auto_promotion",
                    metrics,
                )

        # live_stage_2 and others: no automatic promotion (final stage for data strategies)
        return None

    def _transition_signal(
        self,
        strategy_id: str,
        from_stage: str,
        to_stage: str,
        trigger: str,
        metrics: DataStrategyMetrics,
    ) -> Optional[StageTransition]:
        """Create and log a stage transition for data strategies.

        Args:
            strategy_id: Strategy identifier.
            from_stage: Stage before transition.
            to_stage: Stage after transition.
            trigger: What triggered the transition.
            metrics: DataStrategyMetrics snapshot.

        Returns:
            The created StageTransition, or None if in evaluate_mode.
        """
        if self._evaluate_mode:
            logger.info(
                f"[evaluate_mode] Would transition {strategy_id}: {from_stage} -> {to_stage} "
                f"trigger={trigger}"
            )
            return None

        metrics_snapshot = {
            "total_signals": metrics.total_signals,
            "buy_rate": metrics.buy_rate,
            "neutral_rate": metrics.neutral_rate,
            "consecutive_neutral": metrics.consecutive_neutral,
            "days_in_stage": metrics.days_in_stage,
        }

        return self._history.log_transition(
            strategy_id=strategy_id,
            from_stage=from_stage,
            to_stage=to_stage,
            trigger=trigger,
            metrics=metrics_snapshot,
            actor="system",
        )

    def _transition(
        self,
        strategy_id: str,
        from_stage: str,
        to_stage: str,
        trigger: str,
        metrics: StrategyMetrics,
    ) -> Optional[StageTransition]:
        """Create and log a stage transition.

        Args:
            strategy_id: Strategy identifier.
            from_stage: Stage before transition.
            to_stage: Stage after transition.
            trigger: What triggered the transition.
            metrics: Metrics snapshot at transition time.

        Returns:
            The created StageTransition, or None if in evaluate_mode.
        """
        if self._evaluate_mode:
            logger.info(
                f"[evaluate_mode] Would transition {strategy_id}: {from_stage} -> {to_stage} "
                f"trigger={trigger}"
            )
            return None

        metrics_snapshot = {
            "total_trades": metrics.total_trades,
            "win_rate": metrics.win_rate,
            "current_drawdown_pct": metrics.current_drawdown_pct,
            "sharpe_ratio": metrics.sharpe_ratio,
            "days_in_stage": metrics.days_in_stage,
            "total_pnl_pct": metrics.total_pnl_pct,
        }

        return self._history.log_transition(
            strategy_id=strategy_id,
            from_stage=from_stage,
            to_stage=to_stage,
            trigger=trigger,
            metrics=metrics_snapshot,
            actor="system",
        )

    def force_stage(
        self,
        strategy_id: str,
        current_stage: str,
        target_stage: str,
        reason: str,
        actor: str = "system",
    ) -> StageTransition:
        """Force a strategy to a specific stage (manual override).

        Args:
            strategy_id: Strategy identifier.
            current_stage: Current stage (for logging).
            target_stage: Target stage to set.
            reason: Reason for the override.
            actor: Who initiated ("system" or user identifier).

        Returns:
            The created StageTransition.

        Raises:
            ValueError: If target_stage is not a valid stage name.
        """
        if target_stage not in STAGE_CONFIGS:
            raise ValueError(f"Invalid stage: {target_stage}")

        return self._history.log_transition(
            strategy_id=strategy_id,
            from_stage=current_stage,
            to_stage=target_stage,
            trigger="manual_override",
            metrics={},
            actor=actor,
            override_reason=reason,
        )
