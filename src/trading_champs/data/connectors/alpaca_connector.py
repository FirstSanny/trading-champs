"""Alpaca Trading API connector for trading and account operations."""

import logging
import os
from decimal import Decimal
from typing import Any, List, Optional

import requests

from trading_champs.data.connectors.base import BaseConnector, PriceBar

logger = logging.getLogger(__name__)

# Alpaca API base URLs (v2 API)
ALPACA_PAPER_API = os.getenv("ALPACA_PAPER_API", "https://paper-api.alpaca.markets/v2")
ALPACA_LIVE_API = os.getenv("ALPACA_LIVE_API", "https://api.alpaca.markets/v2")


def get_alpaca_headers(api_key: str, api_secret: str) -> dict:
    """Get headers for Alpaca API."""
    return {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }


class AlpacaConnector(BaseConnector):
    """Connector for Alpaca trading API v2 - supports both live and paper trading."""

    def __init__(self, config: Optional[dict] = None, mode: str = "paper"):
        """Initialize Alpaca connector.

        Args:
            config: Optional configuration dict.
            mode: 'paper' or 'live'. Defaults to 'paper'.
        """
        super().__init__(config or {})
        self.mode = mode
        self.base_url = ALPACA_PAPER_API if mode == "paper" else ALPACA_LIVE_API

        # Get credentials based on mode
        if mode == "paper":
            self.api_key = os.getenv("ALPACA_PAPER_API_KEY")
            self.api_secret = os.getenv("ALPACA_PAPER_API_SECRET")
        else:
            self.api_key = os.getenv("ALPACA_LIVE_API_KEY")
            self.api_secret = os.getenv("ALPACA_LIVE_API_SECRET")

        self._headers = get_alpaca_headers(self.api_key or "", self.api_secret or "")
        self._account: Optional[Any] = None

    @property
    def name(self) -> str:
        return f"alpaca-{self.mode}"

    def connect(self) -> None:
        """Verify API credentials and fetch account info."""
        if not self.api_key or not self.api_secret:
            raise ConnectionError(f"Alpaca {self.mode} API credentials not configured")

        try:
            response = requests.get(
                f"{self.base_url}/account",
                headers=self._headers,
                timeout=10,
            )
            response.raise_for_status()
            self._account = response.json()
            self._connected = True
            logger.info(
                f"Connected to Alpaca {self.mode.title()} Trading: "
                f"{self._account.get('account_number')}"
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to Alpaca {self.mode}: {e}")
            raise ConnectionError(f"Alpaca connection failed: {e}")

    def disconnect(self) -> None:
        """Close connection."""
        self._account = None
        self._connected = False
        logger.info(f"Disconnected from Alpaca {self.mode.title()} Trading")

    def is_connected(self) -> bool:
        return self._connected and self._account is not None

    def get_account(self) -> dict:
        """Fetch account information."""
        if not self.is_connected():
            raise ConnectionError("Not connected to Alpaca")

        try:
            response = requests.get(
                f"{self.base_url}/account",
                headers=self._headers,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch account: {e}")
            raise

    def get_positions(self) -> List[dict]:
        """Fetch all open positions."""
        if not self.is_connected():
            raise ConnectionError("Not connected to Alpaca")

        try:
            response = requests.get(
                f"{self.base_url}/positions",
                headers=self._headers,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch positions: {e}")
            raise

    def get_position(self, symbol: str) -> Optional[dict]:
        """Fetch position for a specific symbol."""
        if not self.is_connected():
            raise ConnectionError("Not connected to Alpaca")

        try:
            response = requests.get(
                f"{self.base_url}/positions/{symbol}",
                headers=self._headers,
                timeout=10,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch position for {symbol}: {e}")
            raise

    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,  # 'buy' or 'sell'
        order_type: str = "market",  # 'market' or 'limit'
        limit_price: Optional[float] = None,
        time_in_force: str = "day",  # 'day', 'gtc', 'opg', 'cls', 'ioc', 'fok'
    ) -> dict:
        """Submit a trading order.

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            qty: Number of shares
            side: 'buy' or 'sell'
            order_type: 'market' or 'limit'
            limit_price: Required for limit orders
            time_in_force: Order expiration

        Returns:
            Order response from Alpaca
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to Alpaca")

        order_payload = {
            "symbol": symbol,
            "qty": str(Decimal(str(qty))),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }

        if order_type == "limit" and limit_price is not None:
            order_payload["limit_price"] = str(Decimal(str(limit_price)))

        try:
            response = requests.post(
                f"{self.base_url}/orders",
                json=order_payload,
                headers=self._headers,
                timeout=10,
            )
            response.raise_for_status()
            logger.info(f"Order submitted: {side} {qty} {symbol} @ {order_type}")
            return response.json()  # type: ignore[no-any-return]
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to submit order: {e}")
            raise

    def get_orders(self, status: str = "all", limit: int = 50) -> List[dict]:
        """Fetch orders.

        Args:
            status: 'open', 'closed', or 'all'
            limit: Max number of orders to return

        Returns:
            List of orders
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to Alpaca")

        try:
            response = requests.get(
                f"{self.base_url}/orders",
                params={"status": status, "limit": limit},  # type: ignore[arg-type]
                headers=self._headers,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch orders: {e}")
            raise

    def cancel_order(self, order_id: str) -> None:
        """Cancel an open order."""
        if not self.is_connected():
            raise ConnectionError("Not connected to Alpaca")

        try:
            response = requests.delete(
                f"{self.base_url}/orders/{order_id}",
                headers=self._headers,
                timeout=10,
            )
            response.raise_for_status()
            logger.info(f"Order cancelled: {order_id}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            raise

    # Market data methods - using polygon.io free tier (Alpaca Data)
    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1m", since: Optional[int] = None, limit: int = 100
    ) -> List[PriceBar]:
        """Fetch OHLCV bars for a symbol from Alpaca Data API.

        Note: Alpaca Data API (polygon.io) has separate free tier.
        This method requires ALPACA_DATA_API_KEY if different from trading key.
        """
        raise NotImplementedError(
            "Use Polygon.io or another data provider for market data. "
            "Alpaca trading API does not provide historical OHLCV."
        )

    def fetch_ticker(self, symbol: str) -> dict:
        """Fetch current ticker - requires Alpaca Data API."""
        raise NotImplementedError(
            "Use Polygon.io or another data provider for real-time quotes. "
            "Alpaca trading API does not provide streaming quotes."
        )

    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict:
        """Fetch order book - requires Alpaca Data API."""
        raise NotImplementedError("Use Polygon.io or another data provider for order book data.")


# Backwards compatibility alias
AlpacaPaperConnector = AlpacaConnector
