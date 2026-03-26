"""Vercel serverless function for Trading Champs Dashboard."""

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Add src to path for imports
# In Vercel, the project root is the parent of the api directory
_project_root = Path(__file__).parent.parent
_src_path = _project_root / "src"
if _src_path.exists():
    sys.path.insert(0, str(_src_path))
else:
    # Fallback for local development
    sys.path.insert(0, str(_project_root / "src"))

# Late imports to ensure path is set
from trading_champs.pl.dashboard import DashboardProvider, DashboardData
from trading_champs.pl.tracker import PnLTracker, TradeSide, Trade, DailyPnL
from trading_champs.pl.metrics import PerformanceMetrics
from datetime import datetime


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

_DASHBOARD_HTML = (Path(__file__).parent.parent / "src" / "trading_champs" / "web" / "dashboard.html").read_text()

# Create tracker and provider
tracker = PnLTracker(initial_balance=10000.0)
provider = DashboardProvider(tracker)


def parse_post_body(body: str, content_type: str = "") -> dict:
    """Parse POST body as JSON or form data."""
    if not body:
        return {}
    if "application/json" in content_type:
        return json.loads(body)
    # Form data
    result = {}
    for pair in body.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[key] = value
    return result


def get_query_params(query_string: str) -> dict:
    """Parse query string parameters."""
    if not query_string:
        return {}
    return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(query_string).items()}


async def handle_request(method: str, path: str, headers: dict, body: str) -> tuple:
    """Handle incoming request and return (status, response_headers, body)."""
    # Parse path and query
    parsed = urlparse(path)
    route_path = parsed.path
    query_params = get_query_params(parsed.query)

    # CORS headers
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

    # Handle CORS preflight
    if method == "OPTIONS":
        return 200, {**cors_headers, "Content-Type": "text/plain"}, ""

    # Route matching
    if route_path == "/" or route_path == "":
        if method == "GET":
            return 200, {**cors_headers, "Content-Type": "text/html"}, _DASHBOARD_HTML
        return 405, cors_headers, json.dumps({"error": "Method not allowed"})

    elif route_path == "/api/dashboard":
        if method == "GET":
            days = int(query_params.get("days", [30])[0])
            data = serialize_dashboard_data(provider.get_dashboard_data(days))
            return 200, {**cors_headers, "Content-Type": "application/json"}, json.dumps(data)
        return 405, cors_headers, json.dumps({"error": "Method not allowed"})

    elif route_path == "/api/equity-curve":
        if method == "GET":
            days = int(query_params.get("days", [30])[0])
            data = provider.get_equity_curve(days)
            return 200, {**cors_headers, "Content-Type": "application/json"}, json.dumps(data)
        return 405, cors_headers, json.dumps({"error": "Method not allowed"})

    elif route_path == "/api/trades":
        if method == "POST":
            trade_data = parse_post_body(body, headers.get("content-type", ""))
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
            return 200, {**cors_headers, "Content-Type": "application/json"}, json.dumps({"status": "success", "trade_id": trade.id})
        elif method == "GET":
            status_filter = query_params.get("status", [None])[0]
            if status_filter == "open":
                trades = tracker.trade_log.get_open_trades()
            elif status_filter == "closed":
                trades = tracker.trade_log.get_closed_trades()
            else:
                trades = tracker.trade_log.trades
            return 200, {**cors_headers, "Content-Type": "application/json"}, json.dumps(trades)
        return 405, cors_headers, json.dumps({"error": "Method not allowed"})

    elif route_path.startswith("/api/trades/") and route_path.endswith("/close"):
        if method == "POST":
            # Extract trade_id from path
            parts = route_path.split("/")
            trade_id = parts[3] if len(parts) >= 4 else None
            if not trade_id:
                return 404, {**cors_headers, "Content-Type": "application/json"}, json.dumps({"error": "Trade not found"})

            trade_data = parse_post_body(body, headers.get("content-type", ""))
            exit_price = float(trade_data.get("exit_price", 0))
            exit_time = (
                datetime.fromisoformat(trade_data["exit_time"])
                if "exit_time" in trade_data
                else datetime.now()
            )

            trade = tracker.close_trade(trade_id, exit_price, exit_time)
            if trade is None:
                return 404, {**cors_headers, "Content-Type": "application/json"}, json.dumps({"error": "Trade not found"})
            return 200, {**cors_headers, "Content-Type": "application/json"}, json.dumps({"status": "success", "trade_id": trade.id, "pnl": trade.pnl})
        return 405, cors_headers, json.dumps({"error": "Method not allowed"})

    # 404 Not Found
    return 404, {**cors_headers, "Content-Type": "application/json"}, json.dumps({"error": "Not found"})


async def handler(request):
    """Vercel handler function."""
    method = request.get("method", "GET")
    path = request.get("path", "/")
    headers = request.get("headers", {})
    body = request.get("body", "")

    # Run the async handler
    status, response_headers, response_body = await handle_request(method, path, headers, body)

    return {
        "statusCode": status,
        "headers": response_headers,
        "body": response_body,
    }
