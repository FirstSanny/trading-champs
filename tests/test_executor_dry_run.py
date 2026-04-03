"""Tests for TradeExecutor with DryRunConnector (dry-run mode)."""

from trading_champs.core.executor import TradeExecutor
from trading_champs.data.connectors.dry_run_connector import DryRunConnector
from trading_champs.pl.tracker import PnLTracker


class TestTradeExecutorDryRun:
    """Tests for TradeExecutor with DryRunConnector."""

    def _make_connector(self) -> DryRunConnector:
        return DryRunConnector(slippage_pct=0.001)

    def _make_tracker(self) -> PnLTracker:
        return PnLTracker(initial_balance=10000.0)

    def test_open_long_in_dry_run_tags_trade(self):
        """Dry-run open_long injects 'dry_run' tag into the trade."""
        connector = self._make_connector()
        executor = TradeExecutor(connector)
        tracker = self._make_tracker()

        result = executor.open_long(
            symbol="BTCUSDT",
            qty=1.0,
            tracker=tracker,
            strategy="ma_crossover",
            limit_price=50000.0,
        )

        assert result.status.value == "filled"
        assert result.trade is not None
        assert "dry_run" in result.trade.tags
        assert "auto" in result.trade.tags
        assert "loop" in result.trade.tags

    def test_close_long_in_dry_run_tags_trade(self):
        """Dry-run close_long injects 'dry_run' tag into the closed trade."""
        connector = self._make_connector()
        executor = TradeExecutor(connector)
        tracker = self._make_tracker()

        open_result = executor.open_long(
            symbol="BTCUSDT",
            qty=1.0,
            tracker=tracker,
            strategy="ma_crossover",
            limit_price=50000.0,
        )
        trade_id = open_result.trade.id

        close_result = executor.close_long(
            symbol="BTCUSDT",
            tracker=tracker,
            tracker_trade_id=trade_id,
            limit_price=51000.0,
        )

        assert close_result.status.value == "filled"
        assert close_result.trade is not None
        assert "dry_run" in close_result.trade.tags

    def test_dry_run_connector_no_credentials_required(self):
        """DryRunConnector initializes without any API credentials."""
        connector = DryRunConnector()
        assert connector.mode == "dry_run"
        assert connector.is_connected() is True
        # No env vars needed for dry_run
        result = connector.submit_order(symbol="BTCUSDT", qty=1.0, side="buy", limit_price=50000.0)
        assert result["status"] == "filled"

    def test_has_position_works_with_dry_run(self):
        """executor.has_position() works with DryRunConnector."""
        connector = self._make_connector()
        executor = TradeExecutor(connector)

        assert executor.has_position("BTCUSDT") is False

        executor.open_long(
            symbol="BTCUSDT",
            qty=1.0,
            tracker=self._make_tracker(),
            limit_price=50000.0,
        )

        assert executor.has_position("BTCUSDT") is True
