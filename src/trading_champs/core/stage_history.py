"""Append-only stage transition history for per-strategy pipelines."""

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StageTransition:
    """A single stage transition event."""

    strategy_id: str
    from_stage: str
    to_stage: str
    trigger: str  # "auto_promotion", "auto_demotion", "manual_override"
    metrics_snapshot: dict[str, Any]
    timestamp: str  # ISO format
    actor: str  # "system" or human user identifier
    override_reason: Optional[str] = None


class StageHistory:
    """Append-only log of stage transitions for all strategies.

    Stored in SQLite alongside existing loop state.
    """

    _local = threading.local()

    def __init__(self, db_path: Optional[str] = None):
        """Initialize StageHistory.

        Args:
            db_path: Path to SQLite database. Defaults to .loop_state.db in project root.
        """
        if db_path is None:
            db_path = str(Path(__file__).parent.parent.parent / ".loop_state.db")
        self._db_path = db_path
        self._db_initialized = False
        try:
            self._init_db()
            self._db_initialized = True
        except Exception as e:
            logger.warning(f"StageHistory[{db_path}]: SQLite unavailable ({e}) — running without persistence")
            self._db_initialized = False

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        conn: sqlite3.Connection
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        else:
            conn = self._local.conn
        return conn

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                from_stage TEXT NOT NULL,
                to_stage TEXT NOT NULL,
                trigger TEXT NOT NULL,
                metrics_snapshot TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                actor TEXT NOT NULL,
                override_reason TEXT,
                UNIQUE(strategy_id, timestamp)
            )
            """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_stage_history_strategy_id
            ON stage_history(strategy_id)
            """)
        conn.commit()

    def append(self, transition: StageTransition) -> None:
        """Append a stage transition to the log."""
        if not self._db_initialized:
            return
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO stage_history
            (strategy_id, from_stage, to_stage, trigger, metrics_snapshot,
             timestamp, actor, override_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transition.strategy_id,
                transition.from_stage,
                transition.to_stage,
                transition.trigger,
                json.dumps(transition.metrics_snapshot),
                transition.timestamp,
                transition.actor,
                transition.override_reason,
            ),
        )
        conn.commit()

    def get_history(self, strategy_id: str, limit: int = 50) -> list[StageTransition]:
        """Get stage transition history for a strategy."""
        if not self._db_initialized:
            return []
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT * FROM stage_history
            WHERE strategy_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (strategy_id, limit),
        ).fetchall()

        return [
            StageTransition(
                strategy_id=row["strategy_id"],
                from_stage=row["from_stage"],
                to_stage=row["to_stage"],
                trigger=row["trigger"],
                metrics_snapshot=json.loads(row["metrics_snapshot"]),
                timestamp=row["timestamp"],
                actor=row["actor"],
                override_reason=row["override_reason"],
            )
            for row in rows
        ]

    def get_latest_stage(self, strategy_id: str) -> Optional[str]:
        """Get the most recent stage for a strategy.

        Args:
            strategy_id: The strategy identifier.

        Returns:
            The current stage name, or None if no history.
        """
        if not self._db_initialized:
            return None
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT to_stage FROM stage_history
            WHERE strategy_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (strategy_id,),
        ).fetchone()
        return row["to_stage"] if row else None

    def log_transition(
        self,
        strategy_id: str,
        from_stage: str,
        to_stage: str,
        trigger: str,
        metrics: dict[str, Any],
        actor: str = "system",
        override_reason: Optional[str] = None,
    ) -> StageTransition:
        """Convenience method to create and append a transition.

        Args:
            strategy_id: Strategy identifier.
            from_stage: Stage before transition.
            to_stage: Stage after transition.
            trigger: What triggered the transition.
            metrics: Metrics snapshot at transition time.
            actor: Who initiated ("system" or user identifier).
            override_reason: Reason for manual override (required if actor is not "system").

        Returns:
            The created StageTransition.
        """
        transition = StageTransition(
            strategy_id=strategy_id,
            from_stage=from_stage,
            to_stage=to_stage,
            trigger=trigger,
            metrics_snapshot=metrics,
            timestamp=datetime.utcnow().isoformat(),
            actor=actor,
            override_reason=override_reason,
        )
        self.append(transition)
        return transition
