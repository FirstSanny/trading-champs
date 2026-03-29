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
from trading_champs.core.loop import TradingLoop
from trading_champs.core.loop_state import LoopConfig, LoopStateStore
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
        "alpaca_connected": data.alpaca_connected,
        "alpaca_account": data.alpaca_account,
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

# Try to set up Alpaca connector for live data (credentials may not be available locally)
def _setup_alpaca() -> None:
    try:
        from trading_champs.data.connectors.alpaca_connector import AlpacaPaperConnector
        connector = AlpacaPaperConnector()
        connector.connect()
        provider.set_alpaca_connector(connector)
    except Exception:
        pass  # Alpaca not available (e.g., missing credentials in dev)

_setup_alpaca()

# Trading loop singleton (lazily initialized)
_loop_instance: TradingLoop | None = None


def get_loop() -> TradingLoop:
    """Get or create the trading loop singleton."""
    global _loop_instance
    if _loop_instance is None:
        import os

        symbols_raw = os.environ.get("LOOP_SYMBOLS", "BTC/USDT")
        symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()]
        config = LoopConfig(
            symbols=symbols,
            strategy=os.environ.get("LOOP_STRATEGY", "ma_crossover"),
            interval_seconds=int(os.environ.get("LOOP_INTERVAL_SECONDS", "60")),
            position_size_fraction=float(os.environ.get("LOOP_POSITION_SIZE", "0.1")),
            max_positions=int(os.environ.get("LOOP_MAX_POSITIONS", "1")),
            stop_loss_percent=float(os.environ.get("LOOP_STOP_LOSS_PCT", "2.0")),
            take_profit_percent=float(os.environ.get("LOOP_TAKE_PROFIT_PCT", "4.0")),
            exchange=os.environ.get("LOOP_EXCHANGE", "binance"),
            timeframe=os.environ.get("LOOP_TIMEFRAME", "1m"),
        )
        _loop_instance = TradingLoop(
            config=config,
            tracker=tracker,
        )
    return _loop_instance


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


async def loop_start(request: Request) -> JSONResponse:
    """Start the trading loop."""
    loop = get_loop()
    loop.start()
    return JSONResponse(content={"status": "started", "loop": loop.get_status()})


async def loop_stop(request: Request) -> JSONResponse:
    """Stop the trading loop."""
    loop = get_loop()
    loop.stop()
    return JSONResponse(content={"status": "stopped", "loop": loop.get_status()})


async def loop_status(request: Request) -> JSONResponse:
    """Get trading loop status."""
    loop = get_loop()
    return JSONResponse(content=loop.get_status())


async def loop_iterate(request: Request) -> JSONResponse:
    """Run one iteration of the trading loop.

    This is the main endpoint called by Vercel Cron or an external scheduler.
    Each call runs one complete fetch → signal → execute cycle.
    """
    loop = get_loop()
    try:
        result = loop.iterate()
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(
            content={"error": str(e), "timestamp": datetime.now().isoformat()},
            status_code=500,
        )


def _get_alpaca_connector() -> "AlpacaPaperConnector":  # type: ignore[name-defined]
    """Get or create an Alpaca connector for dashboard queries."""
    from trading_champs.data.connectors.alpaca_connector import AlpacaPaperConnector
    connector = AlpacaPaperConnector()
    connector.connect()
    return connector


async def account_api(request: Request) -> JSONResponse:
    """Return live Alpaca account data."""
    try:
        connector = _get_alpaca_connector()
        account = connector.get_account()
        return JSONResponse(content={
            "status": "connected",
            "account": {
                "account_number": account.get("account_number"),
                "cash": account.get("cash"),
                "portfolio_value": account.get("portfolio_value"),
                "equity": account.get("equity"),
                "buying_power": account.get("buying_power"),
                "daytrade_count": account.get("daytrade_count"),
                "pattern_day_trader": account.get("pattern_day_trader"),
                "status": account.get("status"),
                "currency": account.get("currency"),
            },
        })
    except Exception as e:
        return JSONResponse(
            content={"status": "error", "error": str(e)},
            status_code=500,
        )


async def positions_api(request: Request) -> JSONResponse:
    """Return live Alpaca positions merged with tracker trades."""
    try:
        connector = _get_alpaca_connector()
        positions = connector.get_positions()

        # Format Alpaca positions
        alpaca_positions = []
        for pos in positions:
            alpaca_positions.append({
                "symbol": pos.get("symbol"),
                "qty": pos.get("qty"),
                "avg_entry_price": pos.get("avg_entry_price"),
                "current_price": pos.get("current_price"),
                "market_value": pos.get("market_value"),
                "unrealized_pl": pos.get("unrealized_pl"),
                "unrealized_plpc": pos.get("unrealized_plpc"),
                "side": pos.get("side"),
                "asset_class": pos.get("asset_class"),
            })

        # Also get open tracker trades for comparison
        open_trades = tracker.trade_log.get_open_trades()

        return JSONResponse(content={
            "alpaca_positions": alpaca_positions,
            "tracker_open_trades": [_serialize_trade(t) for t in open_trades],
            "count": len(alpaca_positions),
        })
    except Exception as e:
        return JSONResponse(
            content={"status": "error", "error": str(e)},
            status_code=500,
        )


# Starlette routes
routes = [
    Route("/", dashboard),
    Route("/api/dashboard", dashboard_api),
    Route("/api/equity-curve", equity_curve_api),
    Route("/api/trades", trades_api),
    Route("/api/trades/{trade_id}/close", close_trade_api),
    Route("/api/account", account_api),
    Route("/api/positions", positions_api),
    Route("/api/loop/start", loop_start, methods=["POST"]),
    Route("/api/loop/stop", loop_stop, methods=["POST"]),
    Route("/api/loop/status", loop_status),
    Route("/api/loop/iterate", loop_iterate, methods=["POST"]),
]

# Create the ASGI app
starlette_app = Starlette(routes=routes)

# Export app - VercelASGI wrapper applied at runtime if available
app = starlette_app