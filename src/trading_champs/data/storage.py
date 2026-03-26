"""Storage layer for market data using Redis and SQLite."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import redis

from trading_champs.data.connectors.base import PriceBar

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

        parsed = json.loads(data)
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
