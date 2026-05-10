"""Trading loop state persistence."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from trading_champs.data.supabase_client import SupabaseClient


@dataclass
class LoopConfig:
    """Configuration for the trading loop."""

    symbols: list[str] = field(default_factory=lambda: ["BTC/USDT"])
    strategy: str = "ma_crossover"  # 'ma_crossover', 'rsi', 'macd'
    interval_seconds: int = 60
    position_size_fraction: float = 0.1  # 10% of account per trade
    max_positions: int = 1
    stop_loss_percent: float = 2.0
    take_profit_percent: float = 4.0
    data_connector: str = "ccxt"  # 'ccxt' or 'alpaca'
    exec_connector: str = "alpaca"  # 'alpaca'
    exchange: str = "binance"
    timeframe: str = "1m"
    lookback_bars: int = 100
    fast_ma_period: int = 20
    slow_ma_period: int = 50
    mode: str = "paper"  # 'paper', 'live', or 'dry_run'


@dataclass
class LoopState:
    """Mutable state for the trading loop.

    Persisted to SQLite so state survives across serverless invocations.
    """

    running: bool = False
    last_run: Optional[datetime] = None
    last_symbol: Optional[str] = None
    last_signal: Optional[str] = None  # 'buy', 'sell', 'neutral'
    last_action: Optional[str] = None  # What the loop did
    consecutive_buy_signals: int = 0
    consecutive_sell_signals: int = 0
    last_error: Optional[str] = None
    iterations: int = 0
    # Persisted dry-run positions: {symbol: {"qty": float, "entry_price": float}}
    dry_run_positions: dict[str, dict] = field(default_factory=dict)

    def record_iteration(self, symbol: str, signal: str, action: str) -> None:
        """Record a loop iteration."""
        self.last_run = datetime.now()
        self.last_symbol = symbol
        self.last_signal = signal
        self.last_action = action
        self.iterations += 1

        if signal == "buy":
            self.consecutive_buy_signals += 1
            self.consecutive_sell_signals = 0
        elif signal == "sell":
            self.consecutive_sell_signals += 1
            self.consecutive_buy_signals = 0
        else:
            self.consecutive_buy_signals = 0
            self.consecutive_sell_signals = 0

        self.last_error = None

    def record_error(self, error: str) -> None:
        """Record an error."""
        self.last_error = error

    def to_dict(self) -> dict:
        """Serialize to dict for JSON responses."""
        return {
            "running": self.running,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_symbol": self.last_symbol,
            "last_signal": self.last_signal,
            "last_action": self.last_action,
            "consecutive_buy_signals": self.consecutive_buy_signals,
            "consecutive_sell_signals": self.consecutive_sell_signals,
            "last_error": self.last_error,
            "iterations": self.iterations,
            "dry_run_positions": self.dry_run_positions,
        }


class RedisDistributedLock:
    """Redis-based distributed lock for serverless environments.

    Prevents concurrent iterate() calls across multiple Vercel instances
    from opening duplicate positions.
    """

    LOCK_KEY = "trading_champs:iterate_lock"
    IDEMPOTENCY_KEY_PREFIX = "trading_champs:idempotency:"

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        lock_ttl_seconds: int = 60,
        idempotency_ttl_seconds: int = 120,
    ):
        self.redis_url = redis_url
        self.lock_ttl_seconds = lock_ttl_seconds
        self.idempotency_ttl_seconds = idempotency_ttl_seconds
        self._redis: Any = None

    def _get_redis(self) -> Any:
        """Lazily connect to Redis."""
        if self._redis is None:
            import redis as _redis_module

            try:
                self._redis = _redis_module.from_url(self.redis_url, decode_responses=True)
                self._redis.ping()
                logger.info("Redis distributed lock connected")
            except Exception as e:
                logger.warning(
                    "Redis unavailable — distributed lock disabled, "
                    f"proceeding with in-process lock only: {e}"
                )
                self._redis = None
        return self._redis

    def acquire(self, idempotency_key: str | None = None) -> bool:
        """Acquire the iterate lock.

        Returns True if lock acquired. If idempotency_key is provided and
        a result exists for that key, returns False (duplicate request).

        Args:
            idempotency_key: Optional idempotency key to prevent duplicate
                             executions within the TTL window.

        Returns:
            True if this instance should proceed with iterate().
            False if lock is held by another instance or a matching
            idempotency key was already processed.
        """
        redis = self._get_redis()
        if redis is None:
            # Redis unavailable — proceed without lock (old behavior, with warning)
            logger.warning("Proceeding without distributed lock — Redis unavailable")
            return True

        import time

        lock_acquired = False
        try:
            # Try to set the lock with NX (only if not exists)
            lock_acquired = redis.set(
                self.LOCK_KEY,
                str(time.time()),
                nx=True,
                ex=self.lock_ttl_seconds,
            )
        except Exception as e:
            logger.error(f"Failed to acquire Redis lock: {e}")
            logger.warning("Redis unavailable — skipping distributed lock (fail-open)")
            return True  # Fail open — don't block the loop

        if not lock_acquired:
            logger.warning("Could not acquire iterate lock — another instance is running")
            return False

        # Check idempotency key
        if idempotency_key:
            idempotency_redis_key = f"{self.IDEMPOTENCY_KEY_PREFIX}{idempotency_key}"
            try:
                existing = redis.get(idempotency_redis_key)
                if existing:
                    logger.info(f"Idempotency key '{idempotency_key}' already processed")
                    redis.delete(self.LOCK_KEY)  # Release lock since we didn't actually iterate
                    return False
                # Store idempotency marker
                redis.setex(idempotency_redis_key, self.idempotency_ttl_seconds, "processing")
            except Exception as e:
                logger.warning(f"Idempotency check failed: {e}")

        return True

    def release(self, idempotency_key: str | None = None) -> None:
        """Release the iterate lock."""
        redis = self._get_redis()
        if redis is None:
            return

        try:
            redis.delete(self.LOCK_KEY)
            if idempotency_key:
                redis.delete(f"{self.IDEMPOTENCY_KEY_PREFIX}{idempotency_key}")
        except Exception as e:
            logger.error(f"Failed to release Redis lock: {e}")

    def mark_done(self, idempotency_key: str, result: str) -> None:
        """Mark an idempotency key as completed with a result."""
        redis = self._get_redis()
        if redis is None:
            return

        try:
            key = f"{self.IDEMPOTENCY_KEY_PREFIX}{idempotency_key}"
            redis.setex(key, self.idempotency_ttl_seconds, result)
        except Exception as e:
            logger.error(f"Failed to store idempotency result: {e}")

    def get_cached_result(self, idempotency_key: str) -> str | None:
        """Get cached result for an idempotency key if it exists."""
        redis = self._get_redis()
        if redis is None:
            return None

        try:
            result = redis.get(f"{self.IDEMPOTENCY_KEY_PREFIX}{idempotency_key}")
            return result.decode("utf-8") if result else None
        except Exception:
            return None


def distributed_lock(
    redis_url: str = "redis://localhost:6379/0",
    idempotency_param: str | None = "idempotency_key",
    lock_ttl: int = 60,
    idempotency_ttl: int = 120,
) -> Callable:
    """Decorator that acquires a Redis distributed lock before invoking a function.

    Usage:
        @distributed_lock(redis_url="redis://...")
        def iterate(self, idempotency_key: str | None = None) -> dict:
            ...

    The decorated function receives the idempotency key from request headers
    and the lock is held for the duration of the function call.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            # Extract idempotency key from kwargs or first positional arg
            idempotency_key: str | None = (
                kwargs.get(idempotency_param) if idempotency_param else None
            )

            lock = RedisDistributedLock(
                redis_url=redis_url,
                lock_ttl_seconds=lock_ttl,
                idempotency_ttl_seconds=idempotency_ttl,
            )

            if not lock.acquire(idempotency_key):
                # Return a "skipped" response — another instance is handling this
                from starlette.responses import JSONResponse

                return JSONResponse(
                    content={
                        "status": "skipped",
                        "reason": "another_instance_running",
                        "idempotency_key": idempotency_key,
                    },
                    status_code=409,
                )

            try:
                return func(self, *args, **kwargs)
            finally:
                lock.release(idempotency_key)

        return wrapper

    return decorator


class LoopStateStore:
    """Persists LoopState to Supabase with SQLite/in-memory fallback.

    Priority: Supabase (primary) -> SQLite (fallback) -> in-memory (last resort).
    This ensures state survives serverless cold starts where SQLite is ephemeral.
    """

    def __init__(
        self,
        db_path: str = "data/trading_loop.db",
        supabase: Optional["SupabaseClient"] = None,
    ):
        self.db_path = db_path
        self._supabase = supabase
        self._db_initialized = False
        self._in_memory: Optional[LoopState] = None
        try:
            self._init_db()
            self._db_initialized = True
        except Exception as e:
            logger.warning(f"LoopStateStore: SQLite unavailable ({e}) — using fallback")
            self._db_initialized = False

    def _init_db(self) -> None:
        """Create the loop state table if it doesn't exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS loop_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                running INTEGER DEFAULT 0,
                last_run TEXT,
                last_symbol TEXT,
                last_signal TEXT,
                last_action TEXT,
                consecutive_buy_signals INTEGER DEFAULT 0,
                consecutive_sell_signals INTEGER DEFAULT 0,
                last_error TEXT,
                iterations INTEGER DEFAULT 0,
                dry_run_positions TEXT DEFAULT '{}'
            )
        """)
        # Ensure exactly one row exists
        cursor.execute("INSERT OR IGNORE INTO loop_state (id) VALUES (1)")
        conn.commit()
        conn.close()

    def load(self) -> LoopState:
        """Load state — tries Supabase first, then SQLite, then in-memory."""
        # 1. Try Supabase
        if self._supabase is not None and self._supabase.is_connected():
            try:
                row = self._supabase.get_loop_state(None)
                if row:
                    return LoopState(
                        running=bool(row.get("running", False)),
                        last_run=(
                            datetime.fromisoformat(row["last_run"]) if row.get("last_run") else None
                        ),
                        last_symbol=row.get("last_symbol"),
                        last_signal=row.get("last_signal"),
                        last_action=row.get("last_action"),
                        consecutive_buy_signals=int(row.get("consecutive_buy_signals", 0)),
                        consecutive_sell_signals=int(row.get("consecutive_sell_signals", 0)),
                        last_error=row.get("last_error"),
                        iterations=int(row.get("iterations", 0)),
                    )
            except Exception as e:
                logger.warning(f"LoopStateStore: Supabase load failed ({e}), trying SQLite")

        # 2. Fall back to SQLite
        if self._db_initialized:
            import json

            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT running, last_run, last_symbol, last_signal, last_action,
                           consecutive_buy_signals, consecutive_sell_signals,
                           last_error, iterations, dry_run_positions
                    FROM loop_state WHERE id = 1
                """)
                row = cursor.fetchone()
                conn.close()

                if row is not None:
                    dry_run_positions = {}
                    if row[9]:
                        try:
                            dry_run_positions = json.loads(row[9])
                        except Exception:
                            pass
                    return LoopState(
                        running=bool(row[0]),
                        last_run=datetime.fromisoformat(row[1]) if row[1] else None,
                        last_symbol=row[2],
                        last_signal=row[3],
                        last_action=row[4],
                        consecutive_buy_signals=row[5],
                        consecutive_sell_signals=row[6],
                        last_error=row[7],
                        iterations=row[8],
                        dry_run_positions=dry_run_positions,
                    )
            except Exception as e:
                logger.warning(f"LoopStateStore: SQLite load failed ({e}), using in-memory")
                fallback_state = self._in_memory if self._in_memory is not None else LoopState()
                fallback_state.last_error = f"DB load failed: {e}"
                return fallback_state

        # 3. Fall back to in-memory
        if self._in_memory is None:
            self._in_memory = LoopState()
        return self._in_memory

    def save(self, state: LoopState) -> None:
        """Persist state — tries Supabase first, then SQLite, then in-memory."""
        last_run_str = state.last_run.isoformat() if state.last_run else None

        # 1. Try Supabase
        if self._supabase is not None and self._supabase.is_connected():
            try:
                ok = self._supabase.save_loop_state(
                    strategy_id=None,
                    running=state.running,
                    last_run=last_run_str,
                    last_symbol=state.last_symbol,
                    last_signal=state.last_signal,
                    last_action=state.last_action,
                    consecutive_buy_signals=state.consecutive_buy_signals,
                    consecutive_sell_signals=state.consecutive_sell_signals,
                    last_error=state.last_error,
                    iterations=state.iterations,
                )
                if ok:
                    return
            except Exception as e:
                logger.warning(f"LoopStateStore: Supabase save failed ({e}), trying SQLite")

        # 2. Fall back to SQLite
        if self._db_initialized:
            import json

            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE loop_state SET
                        running = ?,
                        last_run = ?,
                        last_symbol = ?,
                        last_signal = ?,
                        last_action = ?,
                        consecutive_buy_signals = ?,
                        consecutive_sell_signals = ?,
                        last_error = ?,
                        iterations = ?,
                        dry_run_positions = ?
                    WHERE id = 1
                """,
                    (
                        int(state.running),
                        last_run_str,
                        state.last_symbol,
                        state.last_signal,
                        state.last_action,
                        state.consecutive_buy_signals,
                        state.consecutive_sell_signals,
                        state.last_error,
                        state.iterations,
                        json.dumps(state.dry_run_positions),
                    ),
                )
                conn.commit()
                conn.close()
                return
            except Exception as e:
                logger.warning(f"LoopStateStore: SQLite save failed ({e}), using in-memory")

        # 3. Fall back to in-memory
        self._in_memory = state
