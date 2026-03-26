"""Alpaca Paper Trading API connector for trading and account operations."""

import logging
import os
from decimal import Decimal
from typing import Any, List, Optional

import requests

from trading_champs.data.connectors.base import BaseConnector, PriceBar

logger = logging.getLogger(__name__)

# Alpaca paper trading base URL (v2 API)
ALPACA_PAPER_API = os.getenv("ALPACA_PAPER_API", "https://paper-api.alpaca.markets/v2")
ALPACA_API_KEY = os.getenv("ALPACA_PAPER_API_KEY")
ALPACA_API_SECRET = os.getenv("ALPACA_PAPER_API_SECRET")

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
}


class AlpacaPaperConnector(BaseConnector):
    """Connector for Alpaca paper trading API v2."""

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config or {})
        self.base_url = ALPACA_PAPER_API
        self.api_key = ALPACA_API_KEY
        self.api_secret = ALPACA_API_SECRET
        self._account: Optional[Any] = None

    @property
    def name(self) -> str:
        return "alpaca-paper"

    def connect(self) -> None:
        """Verify API credentials and fetch account info."""
        try:
            response = requests.get(
                f"{self.base_url}/v2/account",
                headers=HEADERS,
                timeout=10,
            )
            response.raise_for_status()
            self._account = response.json()
            self._connected = True
            logger.info(f"Connected to Alpaca Paper Trading: {self._account.get('account_number')}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to Alpaca: {e}")
            raise ConnectionError(f"Alpaca connection failed: {e}")

    def disconnect(self) -> None:
        """Close connection."""
        self._account = None
        self._connected = False
        logger.info("Disconnected from Alpaca Paper Trading")

    def is_connected(self) -> bool:
        return self._connected and self._account is not None

    def get_account(self) -> dict:
        """Fetch account information."""
        if not self.is_connected():
            raise ConnectionError("Not connected to Alpaca")

        try:
            response = requests.get(
                f"{self.base_url}/v2/account",
                headers=HEADERS,
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
                f"{self.base_url}/v2/positions",
                headers=HEADERS,
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
                f"{self.base_url}/v2/positions/{symbol}",
                headers=HEADERS,
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
                f"{self.base_url}/v2/orders",
                json=order_payload,
                headers=HEADERS,
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
                f"{self.base_url}/v2/orders",
                params={"status": status, "limit": limit},  # type: ignore[arg-type]
                headers=HEADERS,
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
                f"{self.base_url}/v2/orders/{order_id}",
                headers=HEADERS,
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
