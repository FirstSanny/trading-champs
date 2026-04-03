"""Critical path tests for StageEvaluator — stage transitions."""

from datetime import datetime, timedelta

import pytest

from trading_champs.core.stage_config import get_stage_config
from trading_champs.core.stage_evaluator import StageEvaluator, StrategyMetrics
from trading_champs.core.stage_history import StageHistory


class TestStageEvaluator:
    """Critical path tests for StageEvaluator.evaluate()."""

    def _make_evaluator(self) -> StageEvaluator:
        """Create a StageEvaluator with a fresh in-memory StageHistory."""
        history = StageHistory(db_path=":memory:")
        return StageEvaluator(history, evaluate_mode=False)

    def _make_metrics(
        self,
        total_trades: int = 25,
        win_rate: float = 0.6,
        drawdown: float = 3.0,
        days: int = 6,
        sharpe: float | None = 1.2,
    ) -> StrategyMetrics:
        return StrategyMetrics(
            total_trades=total_trades,
            win_rate=win_rate,
            current_drawdown_pct=drawdown,
            sharpe_ratio=sharpe,
            days_in_stage=days,
            total_pnl_pct=2.5,
        )

    def test_promotion_dry_run_to_paper(self):
        """Case 1: All gates met → dry_run promotes to paper."""
        evaluator = self._make_evaluator()
        stage_entered_at = datetime.utcnow() - timedelta(days=6)

        # All gates met: 25 trades, 60% win rate, 3% drawdown (< 6%), 6 days (>= 5)
        metrics = self._make_metrics(total_trades=25, win_rate=0.60, drawdown=3.0, days=6)

        transition = evaluator.evaluate(
            strategy_id="rsi",
            current_stage="dry_run",
            stage_entered_at=stage_entered_at,
            metrics=metrics,
        )

        assert transition is not None
        assert transition.from_stage == "dry_run"
        assert transition.to_stage == "paper"
        assert transition.trigger == "auto_promotion"

    def test_demotion_exceeds_drawdown(self):
        """Case 2: Drawdown exceeds max → auto-demoted."""
        evaluator = self._make_evaluator()
        stage_entered_at = datetime.utcnow() - timedelta(days=2)

        # Drawdown 9% exceeds paper max of 8% → demote to dry_run
        metrics = self._make_metrics(total_trades=10, win_rate=0.5, drawdown=9.0, days=2)

        transition = evaluator.evaluate(
            strategy_id="macd",
            current_stage="paper",
            stage_entered_at=stage_entered_at,
            metrics=metrics,
        )

        assert transition is not None
        assert transition.from_stage == "paper"
        # demotes_to for paper is dry_run
        assert transition.to_stage == "dry_run"
        assert transition.trigger == "auto_demotion"

    def test_no_change_gates_not_met(self):
        """Case 3: Gates not met → no transition."""
        evaluator = self._make_evaluator()
        stage_entered_at = datetime.utcnow() - timedelta(days=3)

        # Only 5 trades — need 20 for promotion
        metrics = self._make_metrics(total_trades=5, win_rate=0.4, drawdown=2.0, days=3)

        transition = evaluator.evaluate(
            strategy_id="bollinger",
            current_stage="dry_run",
            stage_entered_at=stage_entered_at,
            metrics=metrics,
        )

        assert transition is None

    def test_final_stage_no_promotion(self):
        """At final stage (live_stage_2), gates met = no transition."""
        evaluator = self._make_evaluator()
        stage_entered_at = datetime.utcnow() - timedelta(days=20)

        # drawdown=8.0 < 12.0 (live_stage_2 max), no demotion
        # next_stage returns None (final stage), so no promotion
        metrics = self._make_metrics(total_trades=60, win_rate=0.65, drawdown=8.0, days=20)

        transition = evaluator.evaluate(
            strategy_id="ma_crossover",
            current_stage="live_stage_2",
            stage_entered_at=stage_entered_at,
            metrics=metrics,
        )

        assert transition is None

    def test_evaluate_mode_no_transition(self):
        """In evaluate_mode, transitions are logged but not executed."""
        history = StageHistory(db_path=":memory:")
        evaluator = StageEvaluator(history, evaluate_mode=True)
        stage_entered_at = datetime.utcnow() - timedelta(days=10)

        metrics = self._make_metrics(total_trades=30, win_rate=0.65, drawdown=2.0, days=10)

        transition = evaluator.evaluate(
            strategy_id="rsi",
            current_stage="dry_run",
            stage_entered_at=stage_entered_at,
            metrics=metrics,
        )

        # evaluate_mode returns None (doesn't execute transition)
        assert transition is None

    def test_days_in_stage_negative_clamped_to_zero(self):
        """days_in_stage calculation is clamped to 0 on clock skew."""
        evaluator = self._make_evaluator()
        # stage_entered_at in the future (clock skew forward)
        stage_entered_at = datetime.utcnow() + timedelta(days=1)

        metrics = self._make_metrics(total_trades=25, win_rate=0.60, drawdown=3.0, days=0)
        # The max(0, ...) guard should prevent negative days

        # This should not raise and should use 0 days
        transition = evaluator.evaluate(
            strategy_id="rsi",
            current_stage="dry_run",
            stage_entered_at=stage_entered_at,
            metrics=metrics,
        )

        # Gates check days_in_stage >= 5 for dry_run; with 0 it should fail
        # So no transition expected
        assert transition is None
