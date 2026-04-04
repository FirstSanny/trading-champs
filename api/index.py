"""Vercel serverless function for Trading Champs Dashboard using Starlette ASGI."""

import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
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

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route

from trading_champs.core.loop import TradingLoop
from trading_champs.core.loop_state import LoopConfig, LoopStateStore
from trading_champs.data.supabase_client import SupabaseClient, get_supabase_client

# Late imports to ensure path is set
from trading_champs.pl.dashboard import DashboardData, DashboardProvider
from trading_champs.pl.metrics import PerformanceMetrics
from trading_champs.pl.tracker import DailyPnL, PnLTracker, Trade, TradeSide


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
        "recent_trades": (
            [_serialize_trade(t) for t in data.recent_trades] if data.recent_trades else []
        ),
        "performance_metrics": (
            asdict(data.performance_metrics) if data.performance_metrics else None
        ),
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
        "side": trade.side.value if hasattr(trade.side, "value") else str(trade.side),
        "quantity": trade.quantity,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "entry_time": (
            trade.entry_time.isoformat()
            if isinstance(trade.entry_time, datetime)
            else trade.entry_time
        ),
        "exit_time": (
            trade.exit_time.isoformat()
            if isinstance(trade.exit_time, datetime)
            else trade.exit_time
        ),
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


def _normalize_alpaca_mode(mode: str) -> str:
    """Normalize mode string to 'paper', 'live', or 'dry_run'.

    Handles short forms like 'p'/'P', 'l'/'L', and 'd'/'dr'.
    """
    normalized = mode.lower().strip()
    if normalized in ("p", "paper"):
        return "paper"
    if normalized in ("l", "live"):
        return "live"
    if normalized in ("d", "dr", "dry_run", "dryrun"):
        return "dry_run"
    # Default to paper for any unrecognized value
    return "paper"


def _check_alpaca_credentials(mode: str) -> tuple[bool, str | None]:
    """Check if Alpaca credentials are configured for the given mode.

    Returns (ok, error_message).
    For paper and dry_run modes, credentials are optional.
    """
    import os

    mode = _normalize_alpaca_mode(mode)
    if mode == "dry_run":
        return True, None
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

    mode = _normalize_alpaca_mode(mode)
    if mode == "dry_run":
        return False, None  # Dry-run has no external trades to fetch

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


_initialized: bool = False


def _ensure_trader_state() -> None:
    """Lazily initialize trader state on first API request.

    Loads Alpaca trades (if credentials configured) and Supabase trades
    (if available) on first call. Does not block the request if either fails.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    # Fetch Alpaca trades if credentials are configured
    mode = os.environ.get("LOOP_MODE", "paper")
    _fetch_alpaca_trades(mode)

    # Load from Supabase if tracker is still empty
    if not tracker.trade_log.trades:
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

    Supports two auth modes:
    - Vercel Cron: Authorization: Bearer <CRON_SECRET> (Vercel auto-sends this)
    - External callers: Authorization: Bearer <API_SECRET>

    Returns True if valid.
    """
    import os
    import hmac

    api_secret = os.environ.get("API_SECRET", "")
    cron_secret = os.environ.get("CRON_SECRET", "")

    # Dev mode bypass: neither secret is configured
    if not api_secret and not cron_secret:
        return True

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return False

    token = auth_header[7:]  # Strip "Bearer " prefix

    # Vercel Cron: CRON_SECRET is set and token matches
    if cron_secret and hmac.compare_digest(token, cron_secret):
        return True

    # External caller: API_SECRET is set and token matches
    if api_secret and hmac.compare_digest(token, api_secret):
        return True

    return False


def auth_guard(request: Request) -> JSONResponse | None:
    """Returns 401 JSONResponse if auth fails, None if auth passes."""
    # Dashboard API is public - no auth required for main dashboard data
    if request.url.path in ("/api/dashboard", "/api/equity-curve", "/api/strategy-curves", "/api/strategies/overview"):
        return None
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
    _ensure_trader_state()
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


# Orchestrator singleton (lazily initialized)
_orchestrator: "StrategyOrchestrator | None" = None  # type: ignore[name-defined]


def get_orchestrator() -> "StrategyOrchestrator":  # type: ignore[name-defined]
    """Get or create the strategy orchestrator singleton.

    STRATEGY_REGISTRY (signals/strategies/__init__.py) is the single source of truth
    for available strategies. Each strategy starts at dry_run stage and is persisted
    across serverless restarts via SQLite.
    """
    global _orchestrator
    if _orchestrator is None:
        from trading_champs.core.orchestrator import (
            OrchestratorConfig,
            StrategyLoopConfig,
            StrategyOrchestrator,
        )
        from trading_champs.signals.strategies import (
            STRATEGY_REGISTRY,
            create_orchestrator_configs,
        )

        strategy_ids = list(STRATEGY_REGISTRY.keys())

        # Per-strategy symbols: round-robin assign ORCHESTRATOR_SYMBOLS across registry keys
        symbols_raw = os.environ.get("ORCHESTRATOR_SYMBOLS", "BTC/USDT")
        symbols_list = [s.strip() for s in symbols_raw.split(",") if s.strip()]
        per_symbol = [symbols_list[i % len(symbols_list)] for i in range(len(strategy_ids))]

        # Per-strategy overrides (list form for per-key values)
        per_strategy_defaults: list[dict] = [
            {
                "symbols": [per_symbol[i]],
                "timeframe": os.environ.get("ORCHESTRATOR_TIMEFRAME", "4h"),
                "data_connector": os.environ.get("ORCHESTRATOR_DATA_CONNECTOR", "alpaca_market"),
                "exec_connector": os.environ.get("ORCHESTRATOR_EXEC_CONNECTOR", "alpaca"),
            }
            for i in range(len(strategy_ids))
        ]

        strategy_configs = create_orchestrator_configs(
            StrategyLoopConfig,  # type: ignore[name-defined]
            defaults=per_strategy_defaults,
        )

        _orchestrator = StrategyOrchestrator(
            strategies=strategy_configs,
            config=OrchestratorConfig(),
        )
    return _orchestrator


async def strategy_stage_history(request: Request) -> JSONResponse:
    """Get stage history for a specific strategy."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    path_parts = request.url.path.split("/")
    strategy_id = path_parts[3] if len(path_parts) >= 4 else None
    if not strategy_id:
        return JSONResponse(content={"error": "Strategy ID required"}, status_code=400)

    orchestrator = get_orchestrator()
    history = orchestrator.get_stage_history(strategy_id)
    return JSONResponse(
        content={
            "strategy_id": strategy_id,
            "history": [asdict(t) for t in history],
        }
    )


async def strategy_stage_patch(request: Request) -> JSONResponse:
    """Force set a strategy's stage (manual override)."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    path_parts = request.url.path.split("/")
    strategy_id = path_parts[3] if len(path_parts) >= 4 else None
    if not strategy_id:
        return JSONResponse(content={"error": "Strategy ID required"}, status_code=400)

    body = await request.body()
    body_str = body.decode() if body else ""
    content_type = request.headers.get("content-type", "")
    data = parse_post_body(body_str, content_type)

    target_stage = data.get("stage")
    override_reason = data.get("override_reason", "manual_override")

    if not target_stage:
        return JSONResponse(content={"error": "stage is required"}, status_code=400)
    if not override_reason:
        return JSONResponse(content={"error": "override_reason is required"}, status_code=400)

    orchestrator = get_orchestrator()
    try:
        new_state = orchestrator.force_stage(
            strategy_id=strategy_id,
            target_stage=target_stage,
            reason=override_reason,
        )
        return JSONResponse(
            content={
                "status": "success",
                "strategy_id": strategy_id,
                "new_stage": new_state.stage,
                "stage_entered_at": new_state.stage_entered_at.isoformat(),
            }
        )
    except ValueError as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)


async def strategies_overview(request: Request) -> JSONResponse:
    """Return per-strategy stage overview for the dashboard.

    Query params:
        - include_archived: if 'true', includes archived strategies
    """
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    try:
        query_params = request.query_params
        include_archived = query_params.get("include_archived", ["false"])[0].lower() == "true"

        orchestrator = get_orchestrator()
        states = orchestrator.get_all_strategy_states()
        result = []
        for strategy_id, state in states.items():
            if state.stage == "archived" and not include_archived:
                continue
            # Compute metrics from the strategy loop's tracker
            strategy_loop = orchestrator._strategy_loops.get(strategy_id)
            metrics_data = {}
            if strategy_loop:
                metrics = strategy_loop.get_metrics(state.stage_entered_at)
                metrics_data = {
                    "total_trades": metrics.total_trades,
                    "win_rate": round(metrics.win_rate * 100, 1) if metrics.win_rate else 0,
                    "current_drawdown_pct": round(metrics.current_drawdown_pct, 2),
                    "total_pnl_pct": round(metrics.total_pnl_pct, 2),
                    "days_in_stage": metrics.days_in_stage,
                }
            result.append({
                "strategy_id": strategy_id,
                "stage": state.stage,
                "stage_entered_at": state.stage_entered_at.isoformat(),
                "metrics": metrics_data,
            })
        return JSONResponse(content={"strategies": result})
    except Exception as e:
        return JSONResponse(
            content={"strategies": [], "error": str(e)},
            status_code=500,
        )


async def strategy_archive(request: Request) -> JSONResponse:
    """Archive a strategy (manual or automated)."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    path_parts = request.url.path.split("/")
    strategy_id = path_parts[3] if len(path_parts) >= 4 else None
    if not strategy_id:
        return JSONResponse(content={"error": "Strategy ID required"}, status_code=400)

    body = await request.body()
    body_str = body.decode() if body else ""
    content_type = request.headers.get("content-type", "")
    data = parse_post_body(body_str, content_type)

    override_reason = data.get("reason", "manual_archive")

    orchestrator = get_orchestrator()
    try:
        new_state = orchestrator.force_archive(
            strategy_id=strategy_id,
            reason=override_reason,
            actor="manual",
        )
        return JSONResponse(
            content={
                "status": "success",
                "strategy_id": strategy_id,
                "new_stage": new_state.stage,
                "stage_entered_at": new_state.stage_entered_at.isoformat(),
            }
        )
    except ValueError as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)


async def strategy_orchestrator_iterate(request: Request) -> JSONResponse:
    """Run one iteration across all strategies via the orchestrator."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    idempotency_key = request.headers.get("x-idempotency-key")
    orchestrator = get_orchestrator()
    try:
        result = orchestrator.iterate_all(idempotency_key=idempotency_key)
        status_code = 409 if result.get("status") == "skipped" else 200
        return JSONResponse(content=result, status_code=status_code)
    except Exception as e:
        return JSONResponse(
            content={"error": str(e), "timestamp": datetime.now().isoformat()},
            status_code=500,
        )


async def trades_api(request: Request) -> JSONResponse:
    """Handle trades API endpoint."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    _ensure_trader_state()
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
    _ensure_trader_state()
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
    _ensure_trader_state()

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


def _get_alpaca_connector() -> "AlpacaPaperAPIConnector":  # type: ignore[name-defined]
    """Get or create an Alpaca connector for dashboard queries."""
    from trading_champs.data.connectors import AlpacaPaperAPIConnector

    connector = AlpacaPaperAPIConnector()
    connector.connect()
    return connector


async def account_api(request: Request) -> JSONResponse:
    """Return live Alpaca account data."""
    if (err_resp := auth_guard(request)) is not None:
        return err_resp
    try:
        connector = _get_alpaca_connector()
        account = connector.get_account()
        return JSONResponse(
            content={
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
            }
        )
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
            alpaca_positions.append(
                {
                    "symbol": pos.get("symbol"),
                    "qty": pos.get("qty"),
                    "avg_entry_price": pos.get("avg_entry_price"),
                    "current_price": pos.get("current_price"),
                    "market_value": pos.get("market_value"),
                    "unrealized_pl": pos.get("unrealized_pl"),
                    "unrealized_plpc": pos.get("unrealized_plpc"),
                    "side": pos.get("side"),
                    "asset_class": pos.get("asset_class"),
                }
            )

        # Also get open tracker trades for comparison
        open_trades = tracker.trade_log.get_open_trades()

        return JSONResponse(
            content={
                "alpaca_positions": alpaca_positions,
                "tracker_open_trades": [_serialize_trade(t) for t in open_trades],
                "count": len(alpaca_positions),
            }
        )
    except Exception as e:
        return JSONResponse(
            content={"status": "error", "error": str(e)},
            status_code=500,
        )


async def metrics(request: Request) -> PlainTextResponse:
    """Expose Prometheus metrics."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return PlainTextResponse(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# Starlette routes
routes = [
    Route("/", dashboard),
    Route("/api/dashboard", dashboard_api),
    Route("/api/equity-curve", equity_curve_api),
    Route("/api/strategy-curves", strategy_curves_api),
    Route("/api/strategies", strategies_api),
    Route("/api/strategies/overview", strategies_overview),
    Route("/api/strategies/{strategy_id}/stage_history", strategy_stage_history),
    Route("/api/strategies/{strategy_id}/stage", strategy_stage_patch, methods=["PATCH"]),
    Route("/api/strategies/{strategy_id}/archive", strategy_archive, methods=["PATCH"]),
    Route("/api/trades", trades_api),
    Route("/api/trades/{trade_id}/close", close_trade_api, methods=["POST"]),
    Route("/api/account", account_api),
    Route("/api/positions", positions_api),
    Route("/api/loop/start", loop_start, methods=["POST"]),
    Route("/api/loop/stop", loop_stop, methods=["POST"]),
    Route("/api/loop/status", loop_status),
    Route("/api/loop/iterate", loop_iterate, methods=["POST"]),
    Route("/api/orchestrator/iterate", strategy_orchestrator_iterate, methods=["POST"]),
    Route("/metrics", metrics),
]

# Create the ASGI app
starlette_app = Starlette(routes=routes)

# Export app - VercelASGI wrapper applied at runtime if available
app = starlette_app
