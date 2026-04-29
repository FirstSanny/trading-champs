"""Tests for DryRunConnector."""

import os
from unittest.mock import patch

import pytest

from trading_champs.data.connectors.dry_run_connector import DEFAULT_SLIPPAGE, DryRunConnector


class TestDryRunConnectorSlippage:
    """Tests for slippage application."""

    def test_buy_order_fills_above_price(self):
        """Buy fills at price * (1 + slippage), which is above price."""
        connector = DryRunConnector(slippage_pct=0.001)
        result = connector.submit_order(
            symbol="BTCUSDT",
            qty=1.0,
            side="buy",
            order_type="market",
            limit_price=50000.0,
        )
        assert result["status"] == "filled"
        filled = float(result["filled_avg_price"])
        assert filled > 50000.0
        assert filled == pytest.approx(50000.0 * 1.001, rel=1e-9)

    def test_sell_order_fills_below_price(self):
        """Sell fills at price * (1 - slippage), which is below price."""
        connector = DryRunConnector(slippage_pct=0.001)
        result = connector.submit_order(
            symbol="BTCUSDT",
            qty=1.0,
            side="sell",
            order_type="market",
            limit_price=50000.0,
        )
        assert result["status"] == "filled"
        filled = float(result["filled_avg_price"])
        assert filled < 50000.0
        assert filled == pytest.approx(50000.0 * 0.999, rel=1e-9)

    def test_zero_limit_price_returns_rejected(self):
        """Market order with no limit_price is rejected."""
        connector = DryRunConnector()
        result = connector.submit_order(
            symbol="BTCUSDT",
            qty=1.0,
            side="buy",
            order_type="market",
            limit_price=None,
        )
        assert result["status"] == "rejected"
        assert result["filled_avg_price"] is None

    def test_negative_limit_price_returns_rejected(self):
        """Negative limit_price is rejected."""
        connector = DryRunConnector()
        result = connector.submit_order(
            symbol="BTCUSDT",
            qty=1.0,
            side="buy",
            order_type="market",
            limit_price=-100.0,
        )
        assert result["status"] == "rejected"


class TestDryRunConnectorPositionTracking:
    """Tests for in-memory position tracking."""

    def test_buy_creates_position(self):
        """After buying, get_position returns the position."""
        connector = DryRunConnector()
        connector.submit_order(
            symbol="BTCUSDT",
            qty=2.0,
            side="buy",
            limit_price=50000.0,
        )
        pos = connector.get_position("BTCUSDT")
        assert pos is not None
        assert float(pos["qty"]) == 2.0
        assert float(pos["avg_entry_price"]) == pytest.approx(50000.0 * 1.001, rel=1e-9)

    def test_sell_reduces_position(self):
        """After buying then selling, position qty decreases."""
        connector = DryRunConnector()
        connector.submit_order(symbol="BTCUSDT", qty=2.0, side="buy", limit_price=50000.0)
        connector.submit_order(symbol="BTCUSDT", qty=1.0, side="sell", limit_price=51000.0)
        pos = connector.get_position("BTCUSDT")
        assert pos is not None
        assert float(pos["qty"]) == 1.0

    def test_no_position_returns_none(self):
        """get_position returns None when no position exists."""
        connector = DryRunConnector()
        assert connector.get_position("BTCUSDT") is None

    def test_get_positions_returns_all_open(self):
        """get_positions returns all non-zero positions."""
        connector = DryRunConnector()
        connector.submit_order(symbol="BTCUSDT", qty=1.0, side="buy", limit_price=50000.0)
        connector.submit_order(symbol="ETHUSDT", qty=3.0, side="buy", limit_price=3000.0)
        positions = connector.get_positions()
        assert len(positions) == 2
        symbols = {p["symbol"] for p in positions}
        assert symbols == {"BTCUSDT", "ETHUSDT"}


class TestDryRunConnectorEnvVar:
    """Tests for environment variable configuration."""

    def test_env_var_overrides_slippage(self):
        """DRY_RUN_SLIPPAGE_PCT env var overrides the default slippage."""
        with patch.dict(os.environ, {"DRY_RUN_SLIPPAGE_PCT": "0.005"}):
            connector = DryRunConnector()
            assert connector.slippage_pct == 0.005

    def test_default_slippage_when_no_env_var(self):
        """When DRY_RUN_SLIPPAGE_PCT is not set, uses DEFAULT_SLIPPAGE."""
        connector = DryRunConnector()
        assert connector.slippage_pct == DEFAULT_SLIPPAGE


class TestDryRunConnectorMode:
    """Tests for connector mode."""

    def test_mode_is_dry_run(self):
        """Connector mode is 'dry_run'."""
        connector = DryRunConnector()
        assert connector.mode == "dry_run"

    def test_name_is_dry_run(self):
        """Connector name is 'dry-run'."""
        connector = DryRunConnector()
        assert connector.name == "dry-run"

    def test_is_connected(self):
        """DryRunConnector is always connected."""
        connector = DryRunConnector()
        assert connector.is_connected() is True
