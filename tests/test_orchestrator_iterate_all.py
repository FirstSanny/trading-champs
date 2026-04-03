"""Critical path tests for StrategyOrchestrator.iterate_all() — parallel execution."""

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from trading_champs.core.orchestrator import (
    OrchestratorConfig,
    StrategyLoopConfig,
    StrategyOrchestrator,
)


class TestOrchestratorIterateAll:
    """Critical path tests for StrategyOrchestrator._iterate_all_impl()."""

    def _make_config(self) -> OrchestratorConfig:
        # Use a temp file so SQLite in-memory behavior works across connections
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        return OrchestratorConfig(db_path=self._tmp.name)

    def _make_loop_config(self, strategy_id: str) -> StrategyLoopConfig:
        return StrategyLoopConfig(
            strategy_id=strategy_id,
            strategy_name=strategy_id.upper(),
            symbols=["AAPL"],
            strategy="rsi",
            mode="dry_run",
            data_connector="ccxt",
            exec_connector="alpaca",
            timeframe="4h",
        )

    def test_all_strategies_run_in_parallel(self):
        """All 4 strategies run and return results (parallel execution)."""
        config = self._make_config()
        strategy_ids = ["rsi", "macd", "bollinger", "ma_crossover"]
        configs = [self._make_loop_config(sid) for sid in strategy_ids]

        orchestrator = StrategyOrchestrator(configs, config=config)

        # Mock each strategy loop's iterate to return a mock result
        for strategy_id in strategy_ids:
            slo = orchestrator._strategy_loops[strategy_id]
            slo.iterate = MagicMock(return_value={"status": "ok", "trades": 3})

        results = orchestrator._iterate_all_impl()

        assert "strategies" in results
        assert set(results["strategies"].keys()) == set(strategy_ids)
        for sid in strategy_ids:
            assert results["strategies"][sid]["status"] == "ok"

    def test_exception_in_one_strategy_others_continue(self):
        """If one strategy raises, others still complete (exception isolation)."""
        config = self._make_config()
        strategy_ids = ["rsi", "macd", "bollinger"]
        configs = [self._make_loop_config(sid) for sid in strategy_ids]

        orchestrator = StrategyOrchestrator(configs, config=config)

        # Mock rsi to raise
        orchestrator._strategy_loops["rsi"].iterate = MagicMock(
            side_effect=Exception("rsi error")
        )
        # Mock others to succeed
        for sid in ["macd", "bollinger"]:
            orchestrator._strategy_loops[sid].iterate = MagicMock(
                return_value={"status": "ok"}
            )

        results = orchestrator._iterate_all_impl()

        # RSI should have error status, others should be ok
        assert results["strategies"]["rsi"]["status"] == "error"
        assert "rsi error" in results["strategies"]["rsi"]["error"]
        assert results["strategies"]["macd"]["status"] == "ok"
        assert results["strategies"]["bollinger"]["status"] == "ok"

    def test_evaluate_all_called_after_iterate(self):
        """_evaluate_all() is called after all strategy iterations complete."""
        config = self._make_config()
        strategy_ids = ["rsi"]
        configs = [self._make_loop_config(sid) for sid in strategy_ids]

        orchestrator = StrategyOrchestrator(configs, config=config)

        slo = orchestrator._strategy_loops["rsi"]
        slo.iterate = MagicMock(return_value={"status": "ok"})

        with patch.object(orchestrator, "_evaluate_all") as mock_eval:
            orchestrator._iterate_all_impl()
            mock_eval.assert_called_once()

    def test_drift_detector_passed_to_loop_iterate(self):
        """StrategyLoop.iterate() passes drift_detector to loop.iterate()."""
        config = self._make_config()
        strategy_ids = ["rsi"]
        configs = [self._make_loop_config(sid) for sid in strategy_ids]

        orchestrator = StrategyOrchestrator(configs, config=config)

        slo = orchestrator._strategy_loops["rsi"]
        mock_result = {
            "status": "ok",
            "signals": [{"symbol": "AAPL", "bar_timestamp": "2026-04-03T10:00:00+00:00"}],
            "actions": [],
        }
        slo.loop.iterate = MagicMock(return_value=mock_result)

        slo.iterate()

        # Verify drift_detector was passed
        slo.loop.iterate.assert_called_once()
        call_kwargs = slo.loop.iterate.call_args
        assert call_kwargs[1].get("drift_detector") is not None
        assert call_kwargs[1]["drift_detector"] is slo.drift_detector

    def test_dry_run_fills_recorded_for_enter_action(self):
        """In dry_run mode, enter actions cause record_dry_run_fill to be called."""
        config = self._make_config()
        strategy_ids = ["rsi"]
        configs = [self._make_loop_config(sid) for sid in strategy_ids]

        orchestrator = StrategyOrchestrator(configs, config=config)
        slo = orchestrator._strategy_loops["rsi"]

        mock_result = {
            "status": "ok",
            "signals": [
                {"symbol": "AAPL", "price": 150.0, "bar_timestamp": "2026-04-03T10:00:00+00:00"}
            ],
            "actions": [
                {"type": "enter", "symbol": "AAPL", "status": "filled", "price": 150.0}
            ],
        }
        slo.loop.iterate = MagicMock(return_value=mock_result)

        # Replace drift_detector with a mock
        slo._drift_detector = MagicMock()

        slo.iterate()

        # record_dry_run_fill should have been called
        assert slo.drift_detector.record_dry_run_fill.called
