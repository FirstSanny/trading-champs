"""StageEvaluator computes quantitative gates and triggers promotion/demotion."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from trading_champs.core.stage_config import (
    STAGE_CONFIGS,
    StageConfig,
    get_stage_config,
    next_stage,
)
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
        days_in_stage = (datetime.utcnow() - stage_entered_at).days

        # Check if current drawdown exceeds max for immediate demotion
        if metrics.current_drawdown_pct > config.max_drawdown_pct:
            demote_stage = config.demotes_to
            logger.warning(
                f"Strategy {strategy_id} demoted from {current_stage} to {demote_stage}: "
                f"drawdown {metrics.current_drawdown_pct:.2f}% exceeds max {config.max_drawdown_pct}%"
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

        next_config = get_stage_config(next_stage_name)
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
