"""FastAPI application for P&L Dashboard."""

import pathlib
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from trading_champs.pl.dashboard import DashboardProvider
from trading_champs.pl.tracker import PnLTracker, TradeSide

_DASHBOARD_HTML = (pathlib.Path(__file__).parent / "dashboard.html").read_text()


def create_app(tracker: PnLTracker | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        tracker: Optional PnLTracker instance. Creates new one if not provided.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="Trading Champs Dashboard",
        description="P&L Tracking and Performance Dashboard",
        version="1.0.0",
    )

    if tracker is None:
        tracker = PnLTracker(initial_balance=10000.0)

    provider = DashboardProvider(tracker)

    @app.get("/", response_class=HTMLResponse)
    async def root() -> str:
        """Serve the main dashboard page."""
        return _DASHBOARD_HTML

    @app.get("/api/dashboard")
    async def get_dashboard(days: int = 30) -> Any:
        """Get dashboard data."""
        return provider.get_dashboard_data(days)

    @app.get("/api/equity-curve")
    async def get_equity_curve(days: int = 30) -> Any:
        """Get equity curve data."""
        return provider.get_equity_curve(days)

    @app.post("/api/trades")
    async def create_trade(trade_data: dict) -> dict:
        """Log a new trade."""
        side = TradeSide.LONG if trade_data.get("side", "").upper() == "LONG" else TradeSide.SHORT
        entry_time = (
            datetime.fromisoformat(trade_data["entry_time"])
            if "entry_time" in trade_data
            else datetime.now()
        )

        trade = tracker.open_trade(
            symbol=trade_data["symbol"],
            side=side,
            quantity=float(trade_data["quantity"]),
            entry_price=float(trade_data["entry_price"]),
            entry_time=entry_time,
        )
        return {"status": "success", "trade_id": trade.id}

    @app.post("/api/trades/{trade_id}/close")
    async def close_trade(trade_id: str, exit_price: float, exit_time: datetime | None = None) -> dict:
        """Close a trade."""
        if exit_time is None:
            exit_time = datetime.now()

        trade = tracker.close_trade(trade_id, exit_price, exit_time)
        if trade is None:
            raise HTTPException(status_code=404, detail="Trade not found")
        return {"status": "success", "trade_id": trade.id, "pnl": trade.pnl}

    @app.get("/api/trades")
    async def get_trades(status: str | None = None) -> Any:
        """Get trades with optional status filter."""
        if status == "open":
            return tracker.trade_log.get_open_trades()
        elif status == "closed":
            return tracker.trade_log.get_closed_trades()
        return tracker.trade_log.trades

    return app
