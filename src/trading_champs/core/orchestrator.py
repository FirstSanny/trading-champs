"""StrategyOrchestrator manages multiple per-strategy trading loop instances."""

import json
import logging
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from trading_champs.core.drift_detector import DriftDetector
from trading_champs.core.drift_store import DriftStore
from trading_champs.core.loop import TradingLoop
from trading_champs.core.loop_state import LoopConfig, LoopStateStore, RedisDistributedLock
from trading_champs.core.stage_config import STAGE_CONFIGS, StageConfig, get_stage_config
from trading_champs.core.stage_evaluator import StageEvaluator, StrategyMetrics
from trading_champs.core.stage_history import StageHistory
from trading_champs.pl.tracker import PnLTracker

logger = logging.getLogger(__name__)


@dataclass
class StrategyLoopConfig:
    """Per-strategy loop configuration.

    Extends LoopConfig with strategy identity and stage management fields.
    """

    strategy_id: str
    strategy_name: str
    stage: str = "dry_run"
    stage_config: StageConfig = field(default_factory=lambda: get_stage_config("dry_run"))
    # Inherits all LoopConfig fields
    symbols: list[str] = field(default_factory=lambda: ["BTC/USDT"])
    strategy: str = "ma_crossover"
    interval_seconds: int = 60
    position_size_fraction: float = 0.1
    max_positions: int = 1
    stop_loss_percent: float = 2.0
    take_profit_percent: float = 4.0
    data_connector: str = "ccxt"
    exec_connector: str = "alpaca"
    exchange: str = "binance"
    timeframe: str = "1m"
    lookback_bars: int = 100
    fast_ma_period: int = 20
    slow_ma_period: int = 50
    mode: str = "dry_run"

    def to_loop_config(self) -> LoopConfig:
        """Convert to LoopConfig for use by TradingLoop.

        position_size_fraction is derived from stage_config.capital_fraction.
        """
        effective_fraction = self.stage_config.capital_fraction if self.stage_config else 0.0
        return LoopConfig(
            symbols=self.symbols,
            strategy=self.strategy,
            interval_seconds=self.interval_seconds,
            position_size_fraction=effective_fraction,
            max_positions=self.max_positions,
            stop_loss_percent=self.stop_loss_percent,
            take_profit_percent=self.take_profit_percent,
            data_connector=self.data_connector,
            exec_connector=self.exec_connector,
            exchange=self.exchange,
            timeframe=self.timeframe,
            lookback_bars=self.lookback_bars,
            fast_ma_period=self.fast_ma_period,
            slow_ma_period=self.slow_ma_period,
            mode=self.stage,  # Use stage as the loop mode
        )


@dataclass
class StrategyState:
    """Per-strategy runtime state persisted to SQLite."""

    strategy_id: str
    stage: str
    stage_entered_at: datetime
    current_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "stage": self.stage,
            "stage_entered_at": self.stage_entered_at.isoformat(),
            "current_metrics": self.current_metrics,
        }


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator itself."""

    db_path: str = ".loop_state.db"
    redis_url: str = "redis://localhost:6379/0"
    lock_ttl_seconds: int = 120


class StrategyLoop:
    """A single strategy's trading loop wrapper.

    Owns its own TradingLoop, PnLTracker, and per-strategy state.
    """

    def __init__(
        self,
        config: StrategyLoopConfig,
        state_store: Optional[LoopStateStore] = None,
        db_path: str = ".loop_state.db",
    ):
        self.config = config
        self._state_store = state_store or LoopStateStore(
            db_path=db_path.replace(".db", f"_{config.strategy_id}.db")
        )
        self._tracker: Optional[PnLTracker] = None
        self._loop: Optional[TradingLoop] = None
        self._drift_store: Optional[DriftStore] = None
        self._drift_detector: Optional[DriftDetector] = None

    @property
    def tracker(self) -> PnLTracker:
        if self._tracker is None:
            self._tracker = PnLTracker()
        return self._tracker

    @property
    def loop(self) -> TradingLoop:
        if self._loop is None:
            loop_config = self.config.to_loop_config()
            self._loop = TradingLoop(
                config=loop_config,
                tracker=self.tracker,
                state_store=self._state_store,
            )
        return self._loop

    @property
    def drift_store(self) -> DriftStore:
        if self._drift_store is None:
            self._drift_store = DriftStore()
        return self._drift_store

    @property
    def drift_detector(self) -> DriftDetector:
        if self._drift_detector is None:
            self._drift_detector = DriftDetector(self.drift_store)
        return self._drift_detector

    def iterate(self) -> dict[str, Any]:
        """Run one iteration of this strategy's loop."""
        try:
            result = self.loop.iterate(
                idempotency_key=f"orchestrator_{self.config.strategy_id}",
                drift_detector=self.drift_detector,
            )

            # Record dry_run fills for drift detection
            if self.config.stage == "dry_run":
                self._record_dry_run_fills(result)

            return result
        except Exception as e:
            logger.error(f"Strategy {self.config.strategy_id} iterate error: {e}")
            return {"status": "error", "strategy_id": self.config.strategy_id, "error": str(e)}

    def _record_dry_run_fills(self, result: dict[str, Any]) -> None:
        """Record dry_run fills from iterate result into DriftStore.

        Called after a successful dry_run iterate to populate DriftStore
        so DriftDetector can compare against paper fills.
        """
        from trading_champs.core.drift_store import DryRunFill

        signals = result.get("signals", [])
        actions = result.get("actions", [])

        # Build symbol -> bar_timestamp map from signals
        symbol_ts: dict[str, float] = {}
        for sig in signals:
            sym = sig.get("symbol")
            ts_str = sig.get("bar_timestamp")
            if sym and ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    symbol_ts[sym] = ts.timestamp()
                except (ValueError, TypeError):
                    pass

        for action in actions:
            sym = action.get("symbol")
            if sym not in symbol_ts:
                continue

            bar_ts = int(symbol_ts[sym])
            action_type = action.get("type")
            status = action.get("status")
            filled_price = action.get("price")  # filled_avg_price equivalent

            if status != "filled" or not filled_price:
                continue

            if action_type == "enter":
                fill = DryRunFill(
                    symbol=sym,
                    bar_timestamp=bar_ts,
                    entry_price=filled_price,
                    exit_price=None,
                    side="long",
                    fill_time=time.time(),
                )
                self.drift_detector.record_dry_run_fill(fill)
            elif action_type == "exit":
                fill = DryRunFill(
                    symbol=sym,
                    bar_timestamp=bar_ts,
                    entry_price=None,
                    exit_price=filled_price,
                    side="long",
                    fill_time=time.time(),
                )
                self.drift_detector.record_dry_run_fill(fill)

    def get_metrics(self, stage_entered_at: datetime) -> StrategyMetrics:
        """Compute metrics from the tracker for stage evaluation."""
        closed_trades = self.tracker.trade_log.get_closed_trades()

        total_trades = len(closed_trades)
        if total_trades == 0:
            return StrategyMetrics(
                total_trades=0,
                win_rate=0.0,
                current_drawdown_pct=0.0,
                sharpe_ratio=None,
                days_in_stage=(datetime.utcnow() - stage_entered_at).days,
                total_pnl_pct=0.0,
            )

        winning_trades = sum(1 for t in closed_trades if t.pnl is not None and t.pnl > 0)
        win_rate = winning_trades / total_trades

        # Calculate current drawdown from trade log equity progression
        running_equity = self.tracker.initial_balance
        equity_points = [running_equity]
        for t in sorted(closed_trades, key=lambda x: x.exit_time or x.entry_time):
            if t.pnl is not None:
                running_equity += t.pnl
            equity_points.append(running_equity)

        if len(equity_points) > 1:
            peak = max(equity_points)
            current = equity_points[-1]
            drawdown_pct = ((peak - current) / peak * 100) if peak > 0 else 0.0
        else:
            drawdown_pct = 0.0

        # Calculate Sharpe ratio (simplified: annualized return / annualized std)
        if len(equity_points) > 10:
            returns = [
                equity_points[i] - equity_points[i - 1] for i in range(1, len(equity_points))
            ]
            if returns:
                import statistics

                mean_return = statistics.mean(returns)
                std_return = statistics.stdev(returns) if len(returns) > 1 else 0.0
                sharpe = (mean_return / std_return * (252**0.5)) if std_return > 0 else None
            else:
                sharpe = None
        else:
            sharpe = None

        total_pnl = sum(t.pnl for t in closed_trades if t.pnl is not None)
        total_pnl_pct = (
            (total_pnl / self.tracker.current_balance * 100)
            if self.tracker.current_balance > 0
            else 0.0
        )

        return StrategyMetrics(
            total_trades=total_trades,
            win_rate=win_rate,
            current_drawdown_pct=drawdown_pct,
            sharpe_ratio=sharpe,
            days_in_stage=(datetime.utcnow() - stage_entered_at).days,
            total_pnl_pct=total_pnl_pct,
        )


class StrategyStateStore:
    """Persists per-strategy StrategyState to SQLite.

    Uses the same database file as OrchestratorConfig.db_path.
    """

    def __init__(self, db_path: str = ".loop_state.db"):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._db_initialized = False
        try:
            self._init_db()
            self._db_initialized = True
        except Exception as e:
            logger.warning(f"StrategyStateStore[{db_path}]: SQLite unavailable ({e}) — running without persistence")
            self._db_initialized = False

    def _init_db(self) -> None:
        with self._lock:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_state (
                    strategy_id TEXT PRIMARY KEY,
                    stage TEXT NOT NULL,
                    stage_entered_at TEXT NOT NULL,
                    current_metrics TEXT NOT NULL DEFAULT '{}'
                )
                """)
            conn.commit()
            conn.close()

    def load(self, strategy_id: str) -> StrategyState:
        """Load state for a strategy, returning defaults if not found."""
        if not self._db_initialized:
            return StrategyState(
                strategy_id=strategy_id,
                stage="dry_run",
                stage_entered_at=datetime.utcnow(),
                current_metrics={},
            )
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM strategy_state WHERE strategy_id = ?",
                (strategy_id,),
            )
            row = cursor.fetchone()
            conn.close()

            if row is None:
                return StrategyState(
                    strategy_id=strategy_id,
                    stage="dry_run",
                    stage_entered_at=datetime.utcnow(),
                    current_metrics={},
                )

            return StrategyState(
                strategy_id=row["strategy_id"],
                stage=row["stage"],
                stage_entered_at=datetime.fromisoformat(row["stage_entered_at"]),
                current_metrics=json.loads(row["current_metrics"]),
            )

    def save(self, state: StrategyState) -> None:
        """Persist strategy state to SQLite."""
        if not self._db_initialized:
            return
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_state
                (strategy_id, stage, stage_entered_at, current_metrics)
                VALUES (?, ?, ?, ?)
                """,
                (
                    state.strategy_id,
                    state.stage,
                    state.stage_entered_at.isoformat(),
                    json.dumps(state.current_metrics),
                ),
            )
            conn.commit()
            conn.close()


class StrategyOrchestrator:
    """Orchestrates multiple per-strategy trading loop instances.

    Owns N StrategyLoop instances, each with its own connector, PnLTracker,
    and stage state. After each iterate_all(), runs StageEvaluator on each
    strategy and logs transitions to StageHistory.
    """

    def __init__(
        self,
        strategies: list[StrategyLoopConfig],
        config: Optional[OrchestratorConfig] = None,
        evaluate_mode: bool = False,
    ):
        """Initialize the orchestrator.

        Args:
            strategies: List of per-strategy loop configurations.
            config: Orchestrator-level configuration.
            evaluate_mode: If True, evaluate gates but do NOT trigger transitions.
        """
        self._config = config or OrchestratorConfig()
        self._evaluate_mode = evaluate_mode

        # State store for per-strategy state
        self._state_store = StrategyStateStore(db_path=self._config.db_path)

        # Stage history
        self._stage_history = StageHistory(db_path=self._config.db_path)

        # Stage evaluator
        self._evaluator = StageEvaluator(
            stage_history=self._stage_history,
            evaluate_mode=evaluate_mode,
        )

        # Drift detectors per strategy (for paper/live strategies)
        self._strategy_loops: dict[str, StrategyLoop] = {}
        for strategy_config in strategies:
            strategy_state = self._state_store.load(strategy_config.strategy_id)
            # Override stage from config with persisted state
            strategy_config.stage = strategy_state.stage
            strategy_config.stage_config = get_stage_config(strategy_state.stage)

            self._strategy_loops[strategy_config.strategy_id] = StrategyLoop(
                config=strategy_config,
                db_path=self._config.db_path,
            )

    def iterate_all(self, idempotency_key: Optional[str] = None) -> dict[str, Any]:
        """Run one iteration across all strategy loops.

        Uses RedisDistributedLock to prevent concurrent invocations.
        If lock is held, returns early with skipped status.

        Args:
            idempotency_key: Optional idempotency key.

        Returns:
            Dict with results for each strategy.
        """
        import os

        redis_url = os.environ.get("REDIS_URL", self._config.redis_url)
        lock = RedisDistributedLock(
            redis_url=redis_url,
            lock_ttl_seconds=self._config.lock_ttl_seconds,
        )

        if not lock.acquire(idempotency_key):
            return {
                "status": "skipped",
                "reason": "another_instance_running",
                "idempotency_key": idempotency_key,
                "timestamp": datetime.utcnow().isoformat(),
            }

        try:
            return self._iterate_all_impl()
        finally:
            lock.release(idempotency_key)

    def _iterate_all_impl(self) -> dict[str, Any]:
        """Internal iterate_all implementation (called after lock acquired)."""
        results: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "strategies": {},
        }

        # Run all strategy iterations in parallel via ThreadPoolExecutor
        def run_strategy(
            strategy_id: str, strategy_loop: StrategyLoop
        ) -> tuple[str, dict[str, Any]]:
            try:
                # Update position_size_fraction from current stage_config before iterate
                current_fraction = strategy_loop.config.stage_config.capital_fraction
                strategy_loop.loop.config.position_size_fraction = current_fraction

                result = strategy_loop.iterate()
                return strategy_id, result
            except Exception as e:
                logger.error(f"Strategy {strategy_id} error in iterate_all: {e}")
                return strategy_id, {
                    "status": "error",
                    "strategy_id": strategy_id,
                    "error": str(e),
                }

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(run_strategy, sid, slo): sid
                for sid, slo in self._strategy_loops.items()
            }
            for future in futures:
                strategy_id, result = future.result()
                results["strategies"][strategy_id] = result

        # Update stages from state store (sequential — DB writes)
        for strategy_id, strategy_loop in self._strategy_loops.items():
            try:
                strategy_state = self._state_store.load(strategy_id)
                strategy_loop.config.stage = strategy_state.stage
                strategy_loop.config.stage_config = get_stage_config(strategy_state.stage)
            except Exception as e:
                logger.error(f"Strategy {strategy_id} stage update error: {e}")

        # After all strategies iterate, evaluate stage transitions
        self._evaluate_all()

        return results

    def _evaluate_all(self) -> None:
        """Evaluate stage gates for all strategies and log transitions."""
        for strategy_id, strategy_loop in self._strategy_loops.items():
            try:
                strategy_state = self._state_store.load(strategy_id)
                metrics = strategy_loop.get_metrics(strategy_state.stage_entered_at)

                transition = self._evaluator.evaluate(
                    strategy_id=strategy_id,
                    current_stage=strategy_loop.config.stage,
                    stage_entered_at=strategy_state.stage_entered_at,
                    metrics=metrics,
                )

                if transition is not None:
                    # Update local config and state store
                    strategy_loop.config.stage = transition.to_stage
                    new_state = StrategyState(
                        strategy_id=strategy_id,
                        stage=transition.to_stage,
                        stage_entered_at=datetime.utcnow(),
                        current_metrics=metrics.__dict__,
                    )
                    self._state_store.save(new_state)

                    # Update position_size_fraction from new stage
                    new_stage_config = get_stage_config(transition.to_stage)
                    strategy_loop.config.stage_config = new_stage_config
                    logger.info(f"Strategy {strategy_id} transitioned to {transition.to_stage}")

            except Exception as e:
                logger.error(f"Strategy {strategy_id} evaluation error: {e}")

    def get_strategy_state(self, strategy_id: str) -> Optional[StrategyState]:
        """Get current state for a strategy."""
        if strategy_id not in self._strategy_loops:
            return None
        return self._state_store.load(strategy_id)

    def get_all_strategy_states(self) -> dict[str, StrategyState]:
        """Get current state for all strategies."""
        return {
            strategy_id: self._state_store.load(strategy_id) for strategy_id in self._strategy_loops
        }

    def get_stage_history(self, strategy_id: str, limit: int = 50) -> list:
        """Get stage history for a strategy."""
        return self._stage_history.get_history(strategy_id, limit=limit)

    def force_stage(
        self,
        strategy_id: str,
        target_stage: str,
        reason: str,
        actor: str = "system",
    ) -> StrategyState:
        """Force a strategy to a specific stage (manual override).

        Args:
            strategy_id: Strategy to update.
            target_stage: Stage to set.
            reason: Reason for the override.
            actor: Who initiated.

        Returns:
            Updated StrategyState.

        Raises:
            ValueError: If strategy_id or target_stage is invalid.
        """
        if strategy_id not in self._strategy_loops:
            raise ValueError(f"Unknown strategy: {strategy_id}")

        if target_stage not in STAGE_CONFIGS:
            raise ValueError(f"Invalid stage: {target_stage}")

        current_state = self._state_store.load(strategy_id)

        self._evaluator.force_stage(
            strategy_id=strategy_id,
            current_stage=current_state.stage,
            target_stage=target_stage,
            reason=reason,
            actor=actor,
        )

        new_state = StrategyState(
            strategy_id=strategy_id,
            stage=target_stage,
            stage_entered_at=datetime.utcnow(),
            current_metrics={},
        )
        self._state_store.save(new_state)

        # Update strategy loop config
        strategy_loop = self._strategy_loops[strategy_id]
        strategy_loop.config.stage = target_stage
        strategy_loop.config.stage_config = get_stage_config(target_stage)

        return new_state
