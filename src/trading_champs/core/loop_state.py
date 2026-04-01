"""Trading loop state persistence."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


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
    mode: str = "paper"  # 'paper' or 'live'


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
        }


class LoopStateStore:
    """Persists LoopState to SQLite so state survives serverless cold starts."""

    def __init__(self, db_path: str = "data/trading_loop.db"):
        self.db_path = db_path
        self._db_initialized = False
        try:
            self._init_db()
            self._db_initialized = True
        except Exception:
            # In serverless environments, SQLite may fail - use in-memory fallback
            self._db_initialized = False

    def _init_db(self) -> None:
        """Create the loop state table if it doesn't exist."""
        import sqlite3
        from pathlib import Path

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
                iterations INTEGER DEFAULT 0
            )
        """)
        # Ensure exactly one row exists
        cursor.execute("INSERT OR IGNORE INTO loop_state (id) VALUES (1)")
        conn.commit()
        conn.close()

    def load(self) -> LoopState:
        """Load state from SQLite."""
        if not self._db_initialized:
            return LoopState()

        import sqlite3

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT running, last_run, last_symbol, last_signal, last_action,
                       consecutive_buy_signals, consecutive_sell_signals,
                       last_error, iterations
                FROM loop_state WHERE id = 1
            """)
            row = cursor.fetchone()
            conn.close()

            if row is None:
                return LoopState()

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
            )
        except Exception:
            return LoopState()

    def save(self, state: LoopState) -> None:
        """Persist state to SQLite."""
        if not self._db_initialized:
            return

        import sqlite3

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
                    iterations = ?
                WHERE id = 1
            """,
                (
                    int(state.running),
                    state.last_run.isoformat() if state.last_run else None,
                    state.last_symbol,
                    state.last_signal,
                    state.last_action,
                    state.consecutive_buy_signals,
                    state.consecutive_sell_signals,
                    state.last_error,
                    state.iterations,
                ),
            )
            conn.commit()
            conn.close()
        except Exception:
            # Silently fail on serverless - state won't persist but loop will work
            pass
