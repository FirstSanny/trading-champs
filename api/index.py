"""Vercel serverless function for Trading Champs Dashboard using Starlette ASGI."""

import json
import sys
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timedelta
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
from trading_champs.data.supabase_client import SupabaseClient, get_supabase_client
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
        "mode": data.mode,
    }


def _serialize_trade(trade: Trade) -> dict:
    """Convert Trade to JSON-serializable dict."""
    status = "open" if trade.exit_price is None else "closed"
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
        "status": status,
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

# Supabase client (lazily initialized)
_supabase_client: SupabaseClient | None = None


def get_supabase() -> SupabaseClient | None:
    """Get or initialize Supabase client."""
    global _supabase_client
    if _supabase_client is None:
        import os
        url = os.environ.get("SUPABASE_URL", "")
        anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
        if url and anon_key:
            _supabase_client = SupabaseClient({"url": url, "anon_key": anon_key})
            if not _supabase_client.connect():
                _supabase_client = None
        if _supabase_client:
            print("Supabase connected")
        else:
            print("Supabase not configured, running without backend persistence")
    return _supabase_client


def _load_supabase_trades() -> bool:
    """Load trades from Supabase into tracker if tracker is empty.

    Returns:
        True if trades were loaded from Supabase.
    """
    supabase = get_supabase()
    if not supabase:
        return False

    if tracker.trade_log.trades:
        return False  # Already have trades

    try:
        trades = supabase.get_trades(limit=500)
        if not trades:
            return False

        for t in trades:
            side = TradeSide.LONG if t.get("side", "").lower() == "long" else TradeSide.SHORT
            from dateutil import parser
            entry_time = parser.parse(t["entry_time"]) if t.get("entry_time") else datetime.now()
            exit_time = parser.parse(t["exit_time"]) if t.get("exit_time") else None

            trade = tracker.open_trade(
                symbol=t["symbol"],
                side=side,
                entry_price=float(t["entry_price"]),
                quantity=float(t["quantity"]),
                entry_time=entry_time,
            )
            if t.get("exit_price") and exit_time:
                tracker.close_trade(trade.id, float(t["exit_price"]), exit_time)
        print(f"Loaded {len(trades)} trades from Supabase")
        return True
    except Exception as e:
        print(f"Failed to load trades from Supabase: {e}")
        return False


def _check_alpaca_credentials(mode: str) -> tuple[bool, str | None]:
    """Check if Alpaca credentials are configured for the given mode.

    Returns (ok, error_message).
    For paper mode, credentials are optional - it can run without them.
    """
    import os
    key_env = f"ALPACA_{mode.upper()}_API_KEY"
    secret_env = f"ALPACA_{mode.upper()}_API_SECRET"
    if not os.environ.get(key_env):
        if mode.lower() == "paper":
            return True, None  # Paper mode doesn't require credentials
        return False, f"${key_env} environment variable is not set"
    if not os.environ.get(secret_env):
        if mode.lower() == "paper":
            return True, None  # Paper mode doesn't require credentials
        return False, f"${secret_env} environment variable is not set"
    return True, None


def _fetch_alpaca_trades(mode: str = "paper") -> tuple[bool, str | None]:
    """Fetch actual trades from Alpaca and populate the tracker.

    Returns (success, error_message).
    """
    import os
    # Only fetch from Alpaca if credentials are available
    key_env = f"ALPACA_{mode.upper()}_API_KEY"
    secret_env = f"ALPACA_{mode.upper()}_API_SECRET"
    if not os.environ.get(key_env) or not os.environ.get(secret_env):
        return False, f"Alpaca {mode} credentials not configured"

    try:
        from trading_champs.data.connectors.alpaca_connector import AlpacaConnector
        connector = AlpacaConnector(mode=mode)
        connector.connect()

        # Sync tracker balance with Alpaca account equity
        account = connector.get_account()
        alpaca_equity = float(account.get("equity", 0))
        if alpaca_equity > 0:
            tracker.initial_balance = alpaca_equity
            tracker.current_balance = alpaca_equity

        # Fetch closed orders from Alpaca if no trades yet
        if not tracker.trade_log.trades:
            orders = connector.get_orders(status="closed", limit=100)

            for order in orders:
                side = TradeSide.LONG if order.get("side") == "buy" else TradeSide.SHORT
                filled_qty = float(order.get("filled_qty", 0))
                if filled_qty <= 0:
                    continue

                entry_price = float(order.get("filled_avg_price", 0))
                if entry_price <= 0:
                    continue

                # Parse timestamps
                created_at = order.get("created_at", "")
                if created_at:
                    from dateutil import parser  # type: ignore[import-untyped]
                    entry_time = parser.parse(created_at)
                else:
                    entry_time = datetime.now()

                closed_at = order.get("filled_at", "") or order.get("closed_at", "")
                exit_price = entry_price
                exit_time = None
                if closed_at:
                    from dateutil import parser
                    exit_time = parser.parse(closed_at)

                trade = tracker.open_trade(
                    symbol=order.get("symbol"),
                    side=side,
                    entry_price=entry_price,
                    quantity=filled_qty,
                    entry_time=entry_time,
                )
                if exit_time:
                    tracker.close_trade(trade.id, exit_price, exit_time)

        provider.set_alpaca_connector(connector)
        return True, None
    except Exception:
        return False, f"Alpaca {mode} fetch failed"


# Current Alpaca mode (paper or live)
_current_alpaca_mode = "paper"


def _refresh_alpaca_trades(mode: str = "paper") -> tuple[bool, str | None]:
    """Refresh trades from Alpaca for the specified mode.

    Returns (success, error_message).
    """
    global _current_alpaca_mode

    # Validate credentials before wiping tracker state
    ok, err = _check_alpaca_credentials(mode)
    if not ok:
        return False, err

    _current_alpaca_mode = mode
    # Reset tracker and re-fetch
    tracker.trade_log.trades.clear()
    return _fetch_alpaca_trades(mode)


_fetch_alpaca_trades()

# Load from Supabase if tracker is empty (fallback when Alpaca not configured)
_load_supabase_trades()

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
            fast_ma_period=int(os.environ.get("LOOP_FAST_MA", "20")),
            slow_ma_period=int(os.environ.get("LOOP_SLOW_MA", "50")),
            mode=os.environ.get("LOOP_MODE", "paper"),
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


def require_api_auth(request: Request) -> bool:
    """Check API key from Authorization header.

    Expects: Authorization: Bearer <API_SECRET>

    Returns True if valid, raises JSONResponse 401 if invalid.
    """
    import os

    api_secret = os.environ.get("API_SECRET", "")
    # Skip auth if no secret configured (development mode)
    if not api_secret:
        return True

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return False

    token = auth_header[7:]  # Strip "Bearer " prefix
    import hmac

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(token, api_secret):
        return False
    return True


def auth_guard(request: Request) -> JSONResponse | None:
    """Returns 401 JSONResponse if auth fails, None if auth passes."""
    if require_api_auth(request):
        return None
    return JSONResponse(
        content={"error": "Unauthorized", "message": "Missing or invalid API_SECRET"},
        status_code=401,
    )


async def dashboard(request: Request) -> HTMLResponse:
    """Serve the dashboard HTML."""
    return HTMLResponse(content=get_dashboard_html())


async def dashboard_api(request: Request) -> JSONResponse:
    """Return dashboard data as JSON."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    query_params = request.query_params
    days = int(query_params.get("days", [30])[0])
    mode = query_params.get("mode", ["paper"])[0]

    error_message = None
    # Check if mode changed - re-fetch trades if needed
    if mode != _current_alpaca_mode:
        ok, err = _refresh_alpaca_trades(mode)
        if not ok:
            error_message = err
            # Fall back to current mode's data instead of leaving tracker empty
            mode = _current_alpaca_mode

    data = serialize_dashboard_data(provider.get_dashboard_data(days, mode))
    if error_message:
        data["error"] = error_message
    return JSONResponse(content=data)


async def equity_curve_api(request: Request) -> JSONResponse:
    """Return equity curve data as JSON."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    query_params = request.query_params
    days = int(query_params.get("days", [30])[0])
    mode = query_params.get("mode", ["paper"])[0]
    strategy = query_params.get("strategy", [None])[0]

    # Check if mode changed - re-fetch trades if needed
    if mode != _current_alpaca_mode:
        ok, _ = _refresh_alpaca_trades(mode)
        if not ok:
            mode = _current_alpaca_mode

    data = provider.get_equity_curve(days, mode, strategy)
    return JSONResponse(content=data)


async def strategy_curves_api(request: Request) -> JSONResponse:
    """Return equity curve data for all strategies as JSON."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    query_params = request.query_params
    days = int(query_params.get("days", [30])[0])
    mode = query_params.get("mode", ["paper"])[0]

    # Check if mode changed - re-fetch trades if needed
    if mode != _current_alpaca_mode:
        ok, _ = _refresh_alpaca_trades(mode)
        if not ok:
            mode = _current_alpaca_mode

    data = provider.get_strategy_equity_curves(days, mode)
    return JSONResponse(content=data)


async def strategies_api(request: Request) -> JSONResponse:
    """Return list of all strategies as JSON."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    strategies = provider.get_strategies()
    return JSONResponse(content={"strategies": strategies})


async def trades_api(request: Request) -> JSONResponse:
    """Handle trades API endpoint."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
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
        # Sync to Supabase if configured
        supabase = get_supabase()
        if supabase:
            supabase.save_trade(trade)
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
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
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
        # Sync to Supabase if configured
        supabase = get_supabase()
        if supabase:
            supabase.save_trade(trade)
        return JSONResponse(content={"status": "success", "trade_id": trade.id, "pnl": trade.pnl})
    return JSONResponse(content={"error": "Method not allowed"}, status_code=405)


async def not_found(request: Request) -> JSONResponse:
    """Handle 404 Not Found."""
    return JSONResponse(content={"error": "Not found"}, status_code=404)


async def loop_start(request: Request) -> JSONResponse:
    """Start the trading loop."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    loop = get_loop()
    loop.start()
    return JSONResponse(content={"status": "started", "loop": loop.get_status()})


async def loop_stop(request: Request) -> JSONResponse:
    """Stop the trading loop."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    loop = get_loop()
    loop.stop()
    return JSONResponse(content={"status": "stopped", "loop": loop.get_status()})


async def loop_status(request: Request) -> JSONResponse:
    """Get trading loop status."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    loop = get_loop()
    return JSONResponse(content=loop.get_status())


async def loop_iterate(request: Request) -> JSONResponse:
    """Run one iteration of the trading loop.

    This is the main endpoint called by Vercel Cron or an external scheduler.
    Each call runs one complete fetch → signal → execute cycle.
    """
    if (err_resp := auth_guard(request)) is not None:
        return err_resp

    # Extract idempotency key from header (Vercel Cron or external scheduler should set this)
    idempotency_key = request.headers.get("x-idempotency-key")

    loop = get_loop()
    try:
        result = loop.iterate(idempotency_key=idempotency_key)
        # If skipped (another instance was running), return 409
        status_code = 409 if result.get("status") == "skipped" else 200
        return JSONResponse(content=result, status_code=status_code)
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
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
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
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
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
    Route("/api/strategy-curves", strategy_curves_api),
    Route("/api/strategies", strategies_api),
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