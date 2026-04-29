"""Unified data service for market data ingestion and retrieval."""

import logging
from datetime import datetime
from typing import List, Optional

from trading_champs.data.connectors.base import BaseConnector, PriceBar
from trading_champs.data.connectors.ccxt_connector import CCXTConnector
from trading_champs.data.storage import MarketDataStorage

logger = logging.getLogger(__name__)


class DataService:
    """Unified service for market data operations."""

    def __init__(self, config: dict):
        self.config = config
        self.connector: Optional[BaseConnector] = None
        self.storage = MarketDataStorage(config.get("storage", {}))

    def connect(self, connector_type: str = "ccxt") -> None:
        """Connect to exchange and storage."""
        if connector_type == "ccxt":
            self.connector = CCXTConnector(self.config.get("exchange", {}))
        else:
            raise ValueError(f"Unknown connector type: {connector_type}")

        self.connector.connect()
        self.storage.connect_redis()
        self.storage.init_db()
        logger.info("DataService connected")

    def disconnect(self) -> None:
        """Disconnect from exchange and storage."""
        if self.connector:
            self.connector.disconnect()
        self.storage.disconnect_redis()
        logger.info("DataService disconnected")

    def is_connected(self) -> bool:
        """Check if service is connected."""
        return self.connector is not None and self.connector.is_connected()

    def fetch_and_store(
        self,
        symbol: str,
        timeframe: str = "1m",
        since: Optional[int] = None,
        limit: int = 100,
    ) -> List[PriceBar]:
        """Fetch OHLCV data from exchange and store in database."""
        if not self.connector:
            raise ConnectionError("DataService not connected")

        bars = self.connector.fetch_ohlcv(symbol, timeframe, since, limit)

        for bar in bars:
            self.storage.cache_bar(bar, timeframe)

        if bars:
            self.storage.save_bars(bars, timeframe)

        logger.info(f"Fetched and stored {len(bars)} bars for {symbol}")
        return bars

    def get_latest_bars(
        self, symbol: str, timeframe: str = "1m", limit: int = 100
    ) -> List[PriceBar]:
        """Get latest bars from database."""
        return self.storage.get_bars(symbol, timeframe=timeframe, limit=limit)

    def get_bars_in_range(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str = "1m",
    ) -> List[PriceBar]:
        """Get bars within a time range from database."""
        return self.storage.get_bars(symbol, start_time, end_time, timeframe)

    def get_ticker(self, symbol: str) -> dict:
        """Get current ticker from exchange."""
        if not self.connector:
            raise ConnectionError("DataService not connected")
        return self.connector.fetch_ticker(symbol)

    def get_order_book(self, symbol: str, limit: int = 20) -> dict:
        """Get order book from exchange."""
        if not self.connector:
            raise ConnectionError("DataService not connected")
        return self.connector.fetch_order_book(symbol, limit)
