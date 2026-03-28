"""Vercel serverless function for Trading Champs Dashboard using Starlette ASGI."""

import json
import sys
from dataclasses import asdict
from pathlib import Path
from datetime import datetime
from typing import Any, cast

# Add src to path for imports
_project_root = Path(__file__).parent.parent
_src_path = _project_root / "src"
if _src_path.exists():
    sys.path.insert(0, str(_src_path))
else:
    sys.path.insert(0, str(_project_root / "src"))

# Try to import vercel.asgi for Vercel deployment
try:
    from vercel.asgi import VercelASGI
    _HAS_VERCEL_ASGI = True
except ImportError:
    _HAS_VERCEL_ASGI = False

# Late imports to ensure path is set
from trading_champs.pl.dashboard import DashboardProvider, DashboardData
from trading_champs.pl.tracker import PnLTracker, TradeSide, Trade, DailyPnL
from trading_champs.pl.metrics import PerformanceMetrics
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route


def serialize_dashboard_data(data: DashboardData) -> dict:
    """Convert DashboardData to JSON-serializable dict."""
    def serialize_daily_pnl(d: DailyPnL) -> dict:
        """Serialize DailyPnL with datetime handling."""
        return {
            "date": d.date.isoformat() if isinstance(d.date, datetime) else d.date,
            "realized_pnl": d.realized_pnl,
            "unrealized_pnl": d.unrealized_pnl,
            "total_pnl": d.total_pnl,
            "trade_count": d.trade_count,
            "win_count": d.win_count,
            "loss_count": d.loss_count,
        }

    return {
        "current_balance": data.current_balance,
        "initial_balance": data.initial_balance,
        "total_realized_pnl": data.total_realized_pnl,
        "total_unrealized_pnl": data.total_unrealized_pnl,
        "total_pnl": data.total_pnl,
        "total_return_percent": data.total_return_percent,
        "daily_pnl": [serialize_daily_pnl(d) for d in data.daily_pnl] if data.daily_pnl else [],
        "recent_trades": [_serialize_trade(t) for t in data.recent_trades] if data.recent_trades else [],
        "performance_metrics": asdict(data.performance_metrics) if data.performance_metrics else None,
        "open_positions": data.open_positions,
    }


def _serialize_trade(trade: Trade) -> dict:
    """Convert Trade to JSON-serializable dict."""
    return {
        "id": trade.id,
        "symbol": trade.symbol,
        "side": trade.side.value if hasattr(trade.side, 'value') else str(trade.side),
        "quantity": trade.quantity,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "entry_time": trade.entry_time.isoformat() if isinstance(trade.entry_time, datetime) else trade.entry_time,
        "exit_time": trade.exit_time.isoformat() if isinstance(trade.exit_time, datetime) else trade.exit_time,
        "pnl": trade.pnl,
        "pnl_percent": trade.pnl_percent,
        "status": trade.status.value if hasattr(trade.status, 'value') else str(trade.status),
    }


# Lazy load the HTML
_dashboard_html = None


def get_dashboard_html() -> str:
    """Lazily load the dashboard HTML."""
    global _dashboard_html
    if _dashboard_html is None:
        html_path = _project_root / "src" / "trading_champs" / "web" / "dashboard.html"
        _dashboard_html = html_path.read_text()
    return _dashboard_html


# Create tracker and provider
tracker = PnLTracker(initial_balance=10000.0)
provider = DashboardProvider(tracker)


def parse_post_body(body: str, content_type: str = "") -> dict[str, str]:
    """Parse POST body as JSON or form data."""
    if not body:
        return {}
    if "application/json" in content_type:
        return cast(dict[str, str], json.loads(body))
    # Form data
    result: dict[str, str] = {}
    for pair in body.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[key] = value
    return result


async def dashboard(request: Request) -> HTMLResponse:
    """Serve the dashboard HTML."""
    return HTMLResponse(content=get_dashboard_html())


async def dashboard_api(request: Request) -> JSONResponse:
    """Return dashboard data as JSON."""
    query_params = request.query_params
    days = int(query_params.get("days", [30])[0])
    data = serialize_dashboard_data(provider.get_dashboard_data(days))
    return JSONResponse(content=data)


async def equity_curve_api(request: Request) -> JSONResponse:
    """Return equity curve data as JSON."""
    query_params = request.query_params
    days = int(query_params.get("days", [30])[0])
    data = provider.get_equity_curve(days)
    return JSONResponse(content=data)


async def trades_api(request: Request) -> JSONResponse:
    """Handle trades API endpoint."""
    if request.method == "POST":
        body = await request.body()
        body_str = body.decode() if body else ""
        content_type = request.headers.get("content-type", "")
        trade_data = parse_post_body(body_str, content_type)
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
        return JSONResponse(content={"status": "success", "trade_id": trade.id})
    elif request.method == "GET":
        query_params = request.query_params
        status_filter = query_params.get("status", [None])[0]
        if status_filter == "open":
            trades = tracker.trade_log.get_open_trades()
        elif status_filter == "closed":
            trades = tracker.trade_log.get_closed_trades()
        else:
            trades = tracker.trade_log.trades
        return JSONResponse(content=trades)
    return JSONResponse(content={"error": "Method not allowed"}, status_code=405)


async def close_trade_api(request: Request) -> JSONResponse:
    """Handle close trade API endpoint."""
    path_parts = request.url.path.split("/")
    trade_id = path_parts[3] if len(path_parts) >= 4 else None
    if not trade_id:
        return JSONResponse(content={"error": "Trade not found"}, status_code=404)

    if request.method == "POST":
        body = await request.body()
        body_str = body.decode() if body else ""
        content_type = request.headers.get("content-type", "")
        trade_data = parse_post_body(body_str, content_type)
        exit_price = float(trade_data.get("exit_price", 0))
        exit_time = (
            datetime.fromisoformat(trade_data["exit_time"])
            if "exit_time" in trade_data
            else datetime.now()
        )
        trade = tracker.close_trade(trade_id, exit_price, exit_time)
        if trade is None:
            return JSONResponse(content={"error": "Trade not found"}, status_code=404)
        return JSONResponse(content={"status": "success", "trade_id": trade.id, "pnl": trade.pnl})
    return JSONResponse(content={"error": "Method not allowed"}, status_code=405)


async def not_found(request: Request) -> JSONResponse:
    """Handle 404 Not Found."""
    return JSONResponse(content={"error": "Not found"}, status_code=404)


# Starlette routes
routes = [
    Route("/", dashboard),
    Route("/api/dashboard", dashboard_api),
    Route("/api/equity-curve", equity_curve_api),
    Route("/api/trades", trades_api),
    Route("/api/trades/{trade_id}/close", close_trade_api),
]

# Create the ASGI app
starlette_app = Starlette(routes=routes)

# Export app - VercelASGI wrapper applied at runtime if available
app = starlette_app