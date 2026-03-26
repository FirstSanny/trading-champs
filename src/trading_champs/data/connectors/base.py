"""Base connector interface for market data providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class PriceBar:
    """OHLCV price bar."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: Optional[float] = None


@dataclass
class Tick:
    """Single price tick."""

    symbol: str
    timestamp: datetime
    price: float
    volume: float
    side: str  # 'buy' or 'sell'


class BaseConnector(ABC):
    """Abstract base class for exchange connectors."""

    def __init__(self, config: dict):
        self.config = config
        self._connected = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Connector name."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the exchange."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the exchange."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected."""

    @abstractmethod
    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1m", since: Optional[int] = None, limit: int = 100
    ) -> List[PriceBar]:
        """Fetch OHLCV bars for a symbol."""

    @abstractmethod
    def fetch_ticker(self, symbol: str) -> dict:
        """Fetch current ticker for a symbol."""

    @abstractmethod
    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict:
        """Fetch order book for a symbol."""

    def parse_symbol(self, symbol: str) -> str:
        """Parse and normalize symbol (e.g. BTC/USDT -> BTC/USDT)."""
        return symbol.upper()

    def format_symbol(self, symbol: str, exchange: str) -> str:
        """Format symbol for specific exchange."""
        return symbol
