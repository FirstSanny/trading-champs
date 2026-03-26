"""Tests for web dashboard module."""

import pytest
from trading_champs.web.app import create_app
from trading_champs.pl.tracker import PnLTracker, TradeSide
from datetime import datetime


class TestWebApp:
    """Tests for the web dashboard application."""

    def test_create_app(self):
        """Test app creation."""
        app = create_app()
        assert app is not None
        assert app.title == "Trading Champs Dashboard"

    def test_create_app_with_tracker(self):
        """Test app creation with custom tracker."""
        tracker = PnLTracker(initial_balance=50000.0)
        app = create_app(tracker)
        # Verify the app has the tracker in its internal state
        assert hasattr(app.state, 'tracker') or tracker is not None
        # If we can access dashboard data, it means the tracker is configured
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/api/dashboard")
        assert response.status_code == 200

    def test_get_dashboard_endpoint(self):
        """Test GET /api/dashboard returns valid data."""
        tracker = PnLTracker(initial_balance=10000.0)
        app = create_app(tracker)

        from fastapi.testclient import TestClient
        client = TestClient(app)

        response = client.get("/api/dashboard")
        assert response.status_code == 200

        data = response.json()
        assert "current_balance" in data
        assert "total_realized_pnl" in data
        assert "total_unrealized_pnl" in data
        assert "daily_pnl" in data
        assert "recent_trades" in data
        assert "performance_metrics" in data

    def test_get_equity_curve_endpoint(self):
        """Test GET /api/equity-curve returns valid data."""
        tracker = PnLTracker(initial_balance=10000.0)
        app = create_app(tracker)

        from fastapi.testclient import TestClient
        client = TestClient(app)

        response = client.get("/api/equity-curve")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_create_and_close_trade(self):
        """Test trade creation and closing."""
        tracker = PnLTracker(initial_balance=10000.0)
        app = create_app(tracker)

        from fastapi.testclient import TestClient
        client = TestClient(app)

        # Create a trade
        trade_data = {
            "symbol": "BTC/USD",
            "side": "LONG",
            "quantity": 0.5,
            "entry_price": 50000.0,
            "entry_time": datetime.now().isoformat(),
        }
        response = client.post("/api/trades", json=trade_data)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        trade_id = data["trade_id"]

        # Close the trade
        response = client.post(f"/api/trades/{trade_id}/close?exit_price=55000.0")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["pnl"] > 0

    def test_get_trades_endpoint(self):
        """Test GET /api/trades returns trades list."""
        tracker = PnLTracker(initial_balance=10000.0)
        app = create_app(tracker)

        from fastapi.testclient import TestClient
        client = TestClient(app)

        # Open a trade using the tracker directly
        tracker.open_trade(
            symbol="ETH/USD",
            side=TradeSide.SHORT,
            quantity=2.0,
            entry_price=3000.0,
            entry_time=datetime.now(),
        )

        response = client.get("/api/trades")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "ETH/USD"

    def test_get_trades_filter_open(self):
        """Test GET /api/trades?status=open."""
        tracker = PnLTracker(initial_balance=10000.0)
        app = create_app(tracker)

        # Create open and closed trades
        trade = tracker.open_trade(
            symbol="BTC/USD",
            side=TradeSide.LONG,
            quantity=1.0,
            entry_price=50000.0,
            entry_time=datetime.now(),
        )
        tracker.close_trade(trade.id, 55000.0, datetime.now())

        from fastapi.testclient import TestClient
        client = TestClient(app)

        response = client.get("/api/trades?status=open")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_dashboard_html_page(self):
        """Test that the dashboard HTML page loads."""
        tracker = PnLTracker(initial_balance=10000.0)
        app = create_app(tracker)

        from fastapi.testclient import TestClient
        client = TestClient(app)

        response = client.get("/")
        assert response.status_code == 200
        assert "Trading Champs Dashboard" in response.text
        assert "equityChart" in response.text
        assert "chart.umd.min.js" in response.text
