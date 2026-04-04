"""Storage layer for market data using Redis and SQLite."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import redis

from trading_champs.data.connectors.base import PriceBar

if TYPE_CHECKING:
    from trading_champs.signals.backtester import BacktestResult

logger = logging.getLogger(__name__)


class MarketDataStorage:
    """Storage for market data using Redis (cache) + SQLite (persistence)."""

    def __init__(self, config: dict):
        self.redis_url = config.get("redis_url", "redis://localhost:6379/0")
        self.db_path = config.get("db_path", "data/market_data.db")
        self.ttl_seconds = config.get("ttl_seconds", 3600)

        self._redis: Optional[redis.Redis] = None
        self._db_path = Path(self.db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect_redis(self) -> None:
        """Connect to Redis."""
        try:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            self._redis.ping()
            logger.info("Connected to Redis")
        except redis.ConnectionError as e:
            logger.warning(f"Redis not available: {e}. Operating without cache.")
            self._redis = None

    def disconnect_redis(self) -> None:
        """Disconnect from Redis."""
        if self._redis:
            self._redis.close()
            self._redis = None

    def init_db(self) -> None:
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                quote_volume REAL,
                timeframe TEXT DEFAULT '1m',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, timestamp, timeframe)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_bars_symbol_time
            ON price_bars(symbol, timestamp DESC)
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                run_at TEXT NOT NULL,
                initial_capital REAL NOT NULL,
                final_capital REAL NOT NULL,
                total_pnl REAL NOT NULL,
                total_pnl_pct REAL NOT NULL,
                win_rate REAL NOT NULL,
                num_trades INTEGER NOT NULL,
                num_wins INTEGER NOT NULL,
                num_losses INTEGER NOT NULL,
                params_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, strategy_name, run_at)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtest_results_symbol_strategy
            ON backtest_results(symbol, strategy_name DESC)
        """)
        conn.commit()
        conn.close()
        logger.info("Database initialized")

    def _redis_key(self, symbol: str, timeframe: str, timestamp: int) -> str:
        return f"market:{symbol}:{timeframe}:{timestamp}"

    def cache_bar(self, bar: PriceBar, timeframe: str = "1m") -> None:
        """Cache a price bar in Redis."""
        if not self._redis:
            return

        key = self._redis_key(bar.symbol, timeframe, int(bar.timestamp.timestamp()))
        data = {
            "symbol": bar.symbol,
            "timestamp": bar.timestamp.isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "quote_volume": bar.quote_volume,
        }
        self._redis.setex(key, self.ttl_seconds, json.dumps(data))

    def get_cached_bar(self, symbol: str, timeframe: str, timestamp: int) -> Optional[PriceBar]:
        """Get a cached price bar from Redis."""
        if not self._redis:
            return None

        key = self._redis_key(symbol, timeframe, timestamp)
        data = self._redis.get(key)
        if not data:
            return None

        parsed = json.loads(data)  # type: ignore[arg-type]
        return PriceBar(
            symbol=parsed["symbol"],
            timestamp=datetime.fromisoformat(parsed["timestamp"]),
            open=parsed["open"],
            high=parsed["high"],
            low=parsed["low"],
            close=parsed["close"],
            volume=parsed["volume"],
            quote_volume=parsed.get("quote_volume"),
        )

    def save_bars(self, bars: List[PriceBar], timeframe: str = "1m") -> int:
        """Save price bars to SQLite."""
        if not bars:
            return 0

        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        count = 0
        for bar in bars:
            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO price_bars
                    (symbol, timestamp, open, high, low, close, volume, quote_volume, timeframe)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bar.symbol,
                        bar.timestamp.isoformat(),
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.volume,
                        bar.quote_volume,
                        timeframe,
                    ),
                )
                count += 1
            except Exception as e:
                logger.debug(f"Skipping bar: {e}")
        conn.commit()
        conn.close()
        logger.info(f"Saved {count} bars to database")
        return count

    def get_bars(
        self,
        symbol: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        timeframe: str = "1m",
        limit: int = 1000,
    ) -> List[PriceBar]:
        """Query price bars from SQLite."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        query = (
            "SELECT symbol, timestamp, open, high, low, close, volume, quote_volume "
            "FROM price_bars WHERE symbol = ? AND timeframe = ?"
        )
        params: List = [symbol, timeframe]

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [
            PriceBar(
                symbol=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                open=row[2],
                high=row[3],
                low=row[4],
                close=row[5],
                volume=row[6],
                quote_volume=row[7],
            )
            for row in reversed(rows)
        ]

    def save_backtest_result(
        self,
        symbol: str,
        strategy_name: str,
        initial_capital: float,
        result: "BacktestResult",
        params: dict,
    ) -> int:
        """Save a backtest result to SQLite.

        Args:
            symbol: Trading symbol (e.g., 'BTC/USD').
            strategy_name: Name of the strategy (e.g., 'ma_crossover_5_15').
            initial_capital: Starting capital for the backtest.
            result: BacktestResult object with trade history.
            params: Strategy parameters as a dictionary.

        Returns:
            Number of rows inserted/updated.
        """
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        final_capital = initial_capital + result.total_pnl
        run_at = datetime.utcnow().isoformat()
        params_json = json.dumps(params)

        try:
            cursor.execute(
                """
                INSERT INTO backtest_results
                (symbol, strategy_name, run_at, initial_capital, final_capital,
                 total_pnl, total_pnl_pct, win_rate, num_trades, num_wins, num_losses, params_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    strategy_name,
                    run_at,
                    initial_capital,
                    final_capital,
                    result.total_pnl,
                    result.total_pnl_pct,
                    result.win_rate,
                    result.num_trades,
                    result.num_wins,
                    result.num_losses,
                    params_json,
                ),
            )
            count = cursor.rowcount
        except Exception as e:
            logger.warning(f"Failed to save backtest result: {e}")
            count = 0

        conn.commit()
        conn.close()
        logger.info(f"Saved backtest result: {strategy_name} for {symbol}")
        return count

    def get_backtest_results(
        self,
        symbol: str,
        strategy_name: str | None = None,
        limit: int = 100,
    ) -> List[dict]:
        """Query backtest results from SQLite.

        Args:
            symbol: Trading symbol.
            strategy_name: Optional strategy name filter.
            limit: Maximum number of results.

        Returns:
            List of backtest result dictionaries.
        """
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        query = """
            SELECT id, symbol, strategy_name, run_at, initial_capital, final_capital,
                   total_pnl, total_pnl_pct, win_rate, num_trades, num_wins, num_losses,
                   params_json, created_at
            FROM backtest_results WHERE symbol = ?
        """
        params: List = [symbol]

        if strategy_name:
            query += " AND strategy_name = ?"
            params.append(strategy_name)

        query += " ORDER BY run_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id": row[0],
                "symbol": row[1],
                "strategy_name": row[2],
                "run_at": row[3],
                "initial_capital": row[4],
                "final_capital": row[5],
                "total_pnl": row[6],
                "total_pnl_pct": row[7],
                "win_rate": row[8],
                "num_trades": row[9],
                "num_wins": row[10],
                "num_losses": row[11],
                "params": json.loads(row[12]),
                "created_at": row[13],
            }
            for row in rows
        ]
