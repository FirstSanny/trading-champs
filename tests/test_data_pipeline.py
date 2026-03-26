"""Tests for the data pipeline."""

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import redis

from trading_champs.data.connectors.alpaca_connector import AlpacaPaperConnector
from trading_champs.data.connectors.base import PriceBar
from trading_champs.data.connectors.ccxt_connector import CCXTConnector
from trading_champs.data.service import DataService
from trading_champs.data.storage import MarketDataStorage


class TestPriceBar:
    """Tests for PriceBar dataclass."""

    def test_price_bar_creation(self):
        bar = PriceBar(
            symbol="BTC/USDT",
            timestamp=datetime(2024, 1, 1, 12, 0),
            open=50000.0,
            high=51000.0,
            low=49000.0,
            close=50500.0,
            volume=100.0,
        )
        assert bar.symbol == "BTC/USDT"
        assert bar.open == 50000.0
        assert bar.high == 51000.0
        assert bar.close == 50500.0


class TestCCXTConnector:
    """Tests for CCXT connector."""

    def test_connector_initialization(self):
        config = {"exchange": "binance", "api_key": "test", "api_secret": "secret"}
        connector = CCXTConnector(config)
        assert connector.exchange_id == "binance"
        assert connector.name == "ccxt-binance"

    def test_connector_invalid_exchange(self):
        config = {"exchange": "nonexistent"}
        connector = CCXTConnector(config)
        with pytest.raises(ValueError, match="Unknown exchange"):
            connector.connect()

    @patch("ccxt.binance")
    def test_fetch_ohlcv(self, mock_binance):
        mock_instance = MagicMock()
        mock_binance.return_value = mock_instance
        mock_instance.fetch_ohlcv.return_value = [
            [1704067200000, 50000.0, 51000.0, 49000.0, 50500.0, 100.0]
        ]

        connector = CCXTConnector({"exchange": "binance"})
        connector.connect()
        bars = connector.fetch_ohlcv("BTC/USDT")

        assert len(bars) == 1
        assert bars[0].symbol == "BTC/USDT"
        assert bars[0].close == 50500.0


class TestMarketDataStorage:
    """Tests for market data storage."""

    def test_redis_key_generation(self):
        config = {"redis_url": "redis://localhost:6379/0"}
        storage = MarketDataStorage(config)
        key = storage._redis_key("BTC/USDT", "1m", 1704067200)
        assert key == "market:BTC/USDT:1m:1704067200"

    def test_storage_without_redis(self):
        with patch("redis.from_url") as mock_redis:
            mock_redis.side_effect = redis.ConnectionError("Connection refused")
            config = {"redis_url": "redis://localhost:6379/0"}
            storage = MarketDataStorage(config)
            storage.connect_redis()
            assert storage._redis is None

    def test_save_and_get_bars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            config = {"db_path": db_path}
            storage = MarketDataStorage(config)
            storage.init_db()

            bars = [
                PriceBar(
                    symbol="BTC/USDT",
                    timestamp=datetime(2024, 1, 1, 12, 0),
                    open=50000.0,
                    high=51000.0,
                    low=49000.0,
                    close=50500.0,
                    volume=100.0,
                ),
                PriceBar(
                    symbol="BTC/USDT",
                    timestamp=datetime(2024, 1, 1, 12, 1),
                    open=50500.0,
                    high=51500.0,
                    low=50000.0,
                    close=51000.0,
                    volume=150.0,
                ),
            ]

            count = storage.save_bars(bars)
            assert count == 2

            retrieved = storage.get_bars("BTC/USDT", limit=10)
            assert len(retrieved) == 2
            assert retrieved[0].close == 50500.0
            assert retrieved[1].close == 51000.0

    def test_get_bars_in_range(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            config = {"db_path": db_path}
            storage = MarketDataStorage(config)
            storage.init_db()

            base_time = datetime(2024, 1, 1, 12, 0)
            bars = [
                PriceBar(
                    symbol="ETH/USDT",
                    timestamp=base_time + timedelta(minutes=i),
                    open=3000.0 + i * 10,
                    high=3100.0 + i * 10,
                    low=2900.0 + i * 10,
                    close=3050.0 + i * 10,
                    volume=50.0 + i,
                )
                for i in range(10)
            ]

            storage.save_bars(bars)

            start = base_time + timedelta(minutes=2)
            end = base_time + timedelta(minutes=5)
            filtered = storage.get_bars("ETH/USDT", start, end)
            assert len(filtered) == 4


class TestDataService:
    """Tests for DataService."""

    def test_service_initialization(self):
        config = {
            "exchange": {"exchange": "binance"},
            "storage": {"db_path": ":memory:"},
        }
        service = DataService(config)
        assert service.connector is None

    def test_service_not_connected_error(self):
        config = {
            "exchange": {"exchange": "binance"},
            "storage": {"db_path": ":memory:"},
        }
        service = DataService(config)
        with pytest.raises(ConnectionError, match="DataService not connected"):
            service.fetch_and_store("BTC/USDT")

    def test_unknown_connector_type(self):
        config = {
            "exchange": {"exchange": "invalid"},
            "storage": {"db_path": ":memory:"},
        }
        service = DataService(config)
        with pytest.raises(ValueError, match="Unknown connector type"):
            service.connect("unknown")


class TestAlpacaPaperConnector:
    """Tests for Alpaca Paper Trading connector."""

    def test_connector_initialization(self):
        connector = AlpacaPaperConnector()
        assert connector.name == "alpaca-paper"
        assert connector.base_url == "https://paper-api.alpaca.markets/v2"

    def test_connector_not_connected_error(self):
        connector = AlpacaPaperConnector()
        with pytest.raises(ConnectionError, match="Not connected"):
            connector.get_account()

    @patch("trading_champs.data.connectors.alpaca_connector.requests.get")
    def test_connect_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"account_number": "PAPER-123", "cash": "10000"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        connector = AlpacaPaperConnector()
        connector.connect()
        assert connector.is_connected()
        assert connector._account["account_number"] == "PAPER-123"

    @patch("trading_champs.data.connectors.alpaca_connector.requests.get")
    def test_get_account(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"account_number": "PAPER-123", "cash": "10000"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        connector = AlpacaPaperConnector()
        connector.connect()
        account = connector.get_account()
        assert account["account_number"] == "PAPER-123"

    @patch("trading_champs.data.connectors.alpaca_connector.requests.get")
    def test_get_positions(self, mock_get):
        # First call is connect(), second call is get_positions()
        mock_account_response = MagicMock()
        mock_account_response.json.return_value = {"account_number": "PAPER-123", "cash": "10000"}
        mock_account_response.raise_for_status = MagicMock()

        mock_positions_response = MagicMock()
        mock_positions_response.json.return_value = [
            {"symbol": "AAPL", "qty": "10", "market_value": "1500"},
            {"symbol": "GOOGL", "qty": "5", "market_value": "7500"},
        ]
        mock_positions_response.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_account_response, mock_positions_response]

        connector = AlpacaPaperConnector()
        connector.connect()
        positions = connector.get_positions()
        assert len(positions) == 2
        assert positions[0]["symbol"] == "AAPL"

    @patch("trading_champs.data.connectors.alpaca_connector.requests.get")
    @patch("trading_champs.data.connectors.alpaca_connector.requests.post")
    def test_submit_market_order(self, mock_post, mock_get):
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"account_number": "PAPER-123", "cash": "10000"}
        mock_get_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_get_response

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "order-123",
            "symbol": "AAPL",
            "qty": "10",
            "side": "buy",
            "type": "market",
            "status": "accepted",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        connector = AlpacaPaperConnector()
        connector.connect()
        order = connector.submit_order(symbol="AAPL", qty=10, side="buy", order_type="market")

        assert order["id"] == "order-123"
        assert order["symbol"] == "AAPL"
        mock_post.assert_called_once()

    @patch("trading_champs.data.connectors.alpaca_connector.requests.get")
    @patch("trading_champs.data.connectors.alpaca_connector.requests.post")
    def test_submit_limit_order(self, mock_post, mock_get):
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"account_number": "PAPER-123", "cash": "10000"}
        mock_get_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_get_response

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "order-456",
            "symbol": "AAPL",
            "qty": "10",
            "side": "buy",
            "type": "limit",
            "limit_price": "150.00",
            "status": "accepted",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        connector = AlpacaPaperConnector()
        connector.connect()
        order = connector.submit_order(
            symbol="AAPL", qty=10, side="buy", order_type="limit", limit_price=150.00
        )

        assert order["limit_price"] == "150.00"
        call_args = mock_post.call_args
        assert float(call_args[1]["json"]["limit_price"]) == 150.00

    @patch("trading_champs.data.connectors.alpaca_connector.requests.get")
    @patch("trading_champs.data.connectors.alpaca_connector.requests.delete")
    def test_cancel_order(self, mock_delete, mock_get):
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"account_number": "PAPER-123", "cash": "10000"}
        mock_get_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_get_response

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_delete.return_value = mock_response

        connector = AlpacaPaperConnector()
        connector.connect()
        connector.cancel_order("order-123")
        mock_delete.assert_called_once()

    @patch("trading_champs.data.connectors.alpaca_connector.requests.get")
    def test_fetch_ohlcv_not_implemented(self, mock_get):
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"account_number": "PAPER-123", "cash": "10000"}
        mock_get_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_get_response

        connector = AlpacaPaperConnector()
        connector.connect()
        with pytest.raises(NotImplementedError, match="Alpaca trading API does not provide"):
            connector.fetch_ohlcv("AAPL")

    @patch("trading_champs.data.connectors.alpaca_connector.requests.get")
    def test_fetch_ticker_not_implemented(self, mock_get):
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"account_number": "PAPER-123", "cash": "10000"}
        mock_get_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_get_response

        connector = AlpacaPaperConnector()
        connector.connect()
        with pytest.raises(NotImplementedError, match="Alpaca trading API does not provide"):
            connector.fetch_ticker("AAPL")

    @patch("trading_champs.data.connectors.alpaca_connector.requests.get")
    def test_fetch_order_book_not_implemented(self, mock_get):
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"account_number": "PAPER-123", "cash": "10000"}
        mock_get_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_get_response

        connector = AlpacaPaperConnector()
        connector.connect()
        with pytest.raises(NotImplementedError, match="Polygon.io"):
            connector.fetch_order_book("AAPL")
