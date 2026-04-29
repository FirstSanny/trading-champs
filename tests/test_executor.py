"""Tests for TradeExecutor."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import requests

from trading_champs.core.executor import ExecResult, ExecStatus, TradeExecutor
from trading_champs.pl.tracker import PnLTracker, TradeSide


class MockAlpacaConnector:
    """Mock Alpaca connector for testing."""

    def __init__(self):
        self.orders = []
        self._position = None

    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        limit_price: float | None = None,
    ):
        return self.orders[-1] if self.orders else {"id": None, "status": "unknown"}

    def get_position(self, symbol: str):
        return self._position


class TestExecResult:
    """Tests for ExecResult dataclass."""

    def test_exec_result_defaults(self):
        result = ExecResult(status=ExecStatus.FILLED)
        assert result.status == ExecStatus.FILLED
        assert result.order_id is None
        assert result.symbol is None
        assert result.filled_price is None
        assert result.trade is None


class TestTradeExecutorOpenLong:
    """Tests for TradeExecutor.open_long()."""

    def _make_connector(self, order_response: dict) -> MockAlpacaConnector:
        conn = MockAlpacaConnector()
        conn.orders.append(order_response)
        return conn

    def _make_tracker(self) -> PnLTracker:
        return PnLTracker(initial_balance=10000.0)

    def test_open_long_filled_order_returns_filled(self):
        """When Alpaca returns filled status, open_long returns FILLED."""
        connector = self._make_connector(
            {
                "id": "order-123",
                "status": "filled",
                "filled_avg_price": "150.00",
            }
        )
        executor = TradeExecutor(connector)
        tracker = self._make_tracker()

        result = executor.open_long(
            symbol="AAPL",
            qty=10.0,
            tracker=tracker,
            strategy="test",
        )

        assert result.status == ExecStatus.FILLED
        assert result.order_id == "order-123"
        assert result.filled_price == 150.00
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.qty == 10.0

    def test_open_long_unfilled_order_returns_rejected(self):
        """When Alpaca returns unfilled order, open_long returns REJECTED."""
        connector = self._make_connector(
            {
                "id": "order-456",
                "status": "pending",
                "filled_avg_price": None,
            }
        )
        executor = TradeExecutor(connector)
        tracker = self._make_tracker()

        result = executor.open_long(
            symbol="AAPL",
            qty=10.0,
            tracker=tracker,
            strategy="test",
        )

        assert result.status == ExecStatus.REJECTED
        assert result.order_id == "order-456"
        assert result.symbol == "AAPL"
        assert result.qty == 10.0
        assert "not filled" in result.message.lower()
        # Trade should NOT be recorded in tracker
        assert len(tracker.trade_log.get_open_trades()) == 0

    def test_open_long_zero_filled_price_returns_rejected(self):
        """When filled_avg_price is 0, open_long returns REJECTED."""
        connector = self._make_connector(
            {
                "id": "order-789",
                "status": "filled",
                "filled_avg_price": "0",
            }
        )
        executor = TradeExecutor(connector)
        tracker = self._make_tracker()

        result = executor.open_long(
            symbol="AAPL",
            qty=10.0,
            tracker=tracker,
            strategy="test",
        )

        assert result.status == ExecStatus.REJECTED

    def test_open_long_rate_limited_returns_retryable(self):
        """When Alpaca returns 429, open_long returns RETRYABLE."""
        connector = self._make_connector({})
        executor = TradeExecutor(connector)
        tracker = self._make_tracker()

        with patch.object(connector, "submit_order") as mock_submit:
            mock_submit.side_effect = requests.exceptions.HTTPError(
                response=MagicMock(status_code=429)
            )

            result = executor.open_long(
                symbol="AAPL",
                qty=10.0,
                tracker=tracker,
                strategy="test",
            )

        assert result.status == ExecStatus.RETRYABLE
        assert result.symbol == "AAPL"
        assert result.side == "buy"

    def test_open_long_other_http_error_returns_error(self):
        """When Alpaca returns 500, open_long returns ERROR."""
        connector = self._make_connector({})
        executor = TradeExecutor(connector)
        tracker = self._make_tracker()

        with patch.object(connector, "submit_order") as mock_submit:
            mock_submit.side_effect = requests.exceptions.HTTPError(
                response=MagicMock(status_code=500)
            )

            result = executor.open_long(
                symbol="AAPL",
                qty=10.0,
                tracker=tracker,
                strategy="test",
            )

        assert result.status == ExecStatus.ERROR


class TestTradeExecutorCloseLong:
    """Tests for TradeExecutor.close_long()."""

    def _make_connector(self, order_response: dict, position: dict | None) -> MockAlpacaConnector:
        conn = MockAlpacaConnector()
        conn.orders.append(order_response)
        conn._position = position
        return conn

    def _make_tracker(self) -> PnLTracker:
        tracker = PnLTracker(initial_balance=10000.0)
        tracker.open_trade(
            symbol="AAPL",
            side=TradeSide.LONG,
            entry_price=150.0,
            quantity=10.0,
            entry_time=datetime.now(),
        )
        return tracker

    def test_close_long_filled_order_returns_filled(self):
        """When Alpaca returns filled close, close_long returns FILLED."""
        connector = self._make_connector(
            {"id": "close-123", "status": "filled", "filled_avg_price": "155.00"},
            position={"qty": "10"},
        )
        executor = TradeExecutor(connector)
        tracker = self._make_tracker()
        open_trade = tracker.trade_log.get_open_trades()[0]

        result = executor.close_long(
            symbol="AAPL",
            tracker=tracker,
            tracker_trade_id=open_trade.id,
        )

        assert result.status == ExecStatus.FILLED
        assert result.order_id == "close-123"
        assert result.filled_price == 155.00
        assert result.symbol == "AAPL"
        assert result.side == "sell"

    def test_close_long_unfilled_order_returns_rejected(self):
        """When Alpaca returns unfilled close, close_long returns REJECTED."""
        connector = self._make_connector(
            {"id": "close-456", "status": "pending", "filled_avg_price": None},
            position={"qty": "10"},
        )
        executor = TradeExecutor(connector)
        tracker = self._make_tracker()
        open_trade = tracker.trade_log.get_open_trades()[0]

        result = executor.close_long(
            symbol="AAPL",
            tracker=tracker,
            tracker_trade_id=open_trade.id,
        )

        assert result.status == ExecStatus.REJECTED
        # Trade should NOT be closed in tracker
        assert len(tracker.trade_log.get_open_trades()) == 1

    def test_close_long_rate_limited_returns_retryable(self):
        """When Alpaca returns 429 on close, close_long returns RETRYABLE."""
        connector = self._make_connector({}, position={"qty": "10"})
        executor = TradeExecutor(connector)
        tracker = self._make_tracker()
        open_trade = tracker.trade_log.get_open_trades()[0]

        with patch.object(connector, "submit_order") as mock_submit:
            mock_submit.side_effect = requests.exceptions.HTTPError(
                response=MagicMock(status_code=429)
            )

            result = executor.close_long(
                symbol="AAPL",
                tracker=tracker,
                tracker_trade_id=open_trade.id,
            )

        assert result.status == ExecStatus.RETRYABLE

    def test_close_long_no_position_returns_no_action(self):
        """When no open position exists, close_long returns NO_ACTION."""
        connector = self._make_connector({}, position=None)
        executor = TradeExecutor(connector)
        tracker = self._make_tracker()

        result = executor.close_long(symbol="AAPL", tracker=tracker)

        assert result.status == ExecStatus.NO_ACTION

    def test_close_long_zero_qty_returns_no_action(self):
        """When position qty is 0, close_long returns NO_ACTION."""
        connector = self._make_connector({}, position={"qty": "0"})
        executor = TradeExecutor(connector)
        tracker = self._make_tracker()

        result = executor.close_long(symbol="AAPL", tracker=tracker)

        assert result.status == ExecStatus.NO_ACTION


class TestTradeExecutorPosition:
    """Tests for position query methods."""

    def test_get_position_qty_returns_qty(self):
        conn = MockAlpacaConnector()
        conn._position = {"qty": "25.5"}
        executor = TradeExecutor(conn)

        assert executor.get_position_qty("AAPL") == 25.5

    def test_get_position_qty_no_position_returns_zero(self):
        conn = MockAlpacaConnector()
        conn._position = None
        executor = TradeExecutor(conn)

        assert executor.get_position_qty("AAPL") == 0.0

    def test_has_position_true(self):
        conn = MockAlpacaConnector()
        conn._position = {"qty": "10"}
        executor = TradeExecutor(conn)

        assert executor.has_position("AAPL") is True

    def test_has_position_false(self):
        conn = MockAlpacaConnector()
        conn._position = None
        executor = TradeExecutor(conn)

        assert executor.has_position("AAPL") is False
