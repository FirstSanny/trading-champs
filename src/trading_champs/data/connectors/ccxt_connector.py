"""CCXT-based exchange connector for market data ingestion."""

import logging
from datetime import datetime
from typing import Any, List, Optional

import ccxt

from trading_champs.data.connectors.base import BaseConnector, PriceBar

logger = logging.getLogger(__name__)


class CCXTConnector(BaseConnector):
    """Connector using CCXT library for multi-exchange support."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.exchange_id = config.get("exchange", "binance")
        self.api_key = config.get("api_key")
        self.api_secret = config.get("api_secret")
        self._exchange: Optional[Any] = None

    @property
    def name(self) -> str:
        return f"ccxt-{self.exchange_id}"

    def connect(self) -> None:
        """Initialize CCXT exchange."""
        try:
            exchange_class = getattr(ccxt, self.exchange_id)
            self._exchange = exchange_class(
                {
                    "apiKey": self.api_key,
                    "secret": self.api_secret,
                    "enableRateLimit": True,
                }
            )
            self._connected = True
            logger.info(f"Connected to {self.exchange_id} via CCXT")
        except AttributeError:
            raise ValueError(f"Unknown exchange: {self.exchange_id}")
        except Exception as e:
            logger.error(f"Failed to connect to {self.exchange_id}: {e}")
            raise

    def disconnect(self) -> None:
        """Close exchange connection."""
        self._exchange = None
        self._connected = False
        logger.info(f"Disconnected from {self.exchange_id}")

    def is_connected(self) -> bool:
        return self._connected and self._exchange is not None

    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1m", since: Optional[int] = None, limit: int = 100
    ) -> List[PriceBar]:
        """Fetch OHLCV bars from exchange."""
        if not self.is_connected():
            raise ConnectionError(f"Not connected to {self.exchange_id}")

        try:
            # type: ignore[union-attr]
            raw_bars = self._exchange.fetch_ohlcv(symbol, timeframe, since, limit)
            return [
                PriceBar(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(bar[0] / 1000),
                    open=float(bar[1]),
                    high=float(bar[2]),
                    low=float(bar[3]),
                    close=float(bar[4]),
                    volume=float(bar[5]),
                    quote_volume=float(bar[5]) * float(bar[4]) if len(bar) > 5 else None,
                )
                for bar in raw_bars
            ]
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            raise

    def fetch_ticker(self, symbol: str) -> dict:
        """Fetch current ticker from exchange."""
        if not self.is_connected():
            raise ConnectionError(f"Not connected to {self.exchange_id}")

        try:
            ticker = self._exchange.fetch_ticker(symbol)  # type: ignore[union-attr]
            return {
                "symbol": symbol,
                "last": float(ticker.get("last", 0)),
                "bid": float(ticker.get("bid", 0)),
                "ask": float(ticker.get("ask", 0)),
                "volume": float(ticker.get("volume", 0)),
                "timestamp": datetime.fromtimestamp(ticker.get("timestamp", 0) / 1000),
            }
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            raise

    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict:
        """Fetch order book from exchange."""
        if not self.is_connected():
            raise ConnectionError(f"Not connected to {self.exchange_id}")

        try:
            book = self._exchange.fetch_order_book(symbol, limit)  # type: ignore[union-attr]
            return {
                "symbol": symbol,
                "bids": [[float(p), float(q)] for p, q in book.get("bids", [])],
                "asks": [[float(p), float(q)] for p, q in book.get("asks", [])],
                "timestamp": datetime.fromtimestamp(book.get("timestamp", 0) / 1000),
            }
        except Exception as e:
            logger.error(f"Failed to fetch order book for {symbol}: {e}")
            raise
