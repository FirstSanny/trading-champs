"""FastAPI application for P&L Dashboard."""

from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from trading_champs.pl.tracker import PnLTracker, TradeSide
from trading_champs.pl.dashboard import DashboardProvider


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
    async def root():
        """Serve the main dashboard page."""
        return _DASHBOARD_HTML

    @app.get("/api/dashboard")
    async def get_dashboard(days: int = 30):
        """Get dashboard data."""
        return provider.get_dashboard_data(days)

    @app.get("/api/equity-curve")
    async def get_equity_curve(days: int = 30):
        """Get equity curve data."""
        return provider.get_equity_curve(days)

    @app.post("/api/trades")
    async def create_trade(trade_data: dict):
        """Log a new trade."""
        side = TradeSide.LONG if trade_data.get("side", "").upper() == "LONG" else TradeSide.SHORT
        entry_time = datetime.fromisoformat(trade_data["entry_time"]) if "entry_time" in trade_data else datetime.now()

        trade = tracker.open_trade(
            symbol=trade_data["symbol"],
            side=side,
            quantity=float(trade_data["quantity"]),
            entry_price=float(trade_data["entry_price"]),
            entry_time=entry_time,
        )
        return {"status": "success", "trade_id": trade.id}

    @app.post("/api/trades/{trade_id}/close")
    async def close_trade(trade_id: str, exit_price: float, exit_time: datetime | None = None):
        """Close a trade."""
        if exit_time is None:
            exit_time = datetime.now()

        trade = tracker.close_trade(trade_id, exit_price, exit_time)
        if trade is None:
            raise HTTPException(status_code=404, detail="Trade not found")
        return {"status": "success", "trade_id": trade.id, "pnl": trade.pnl}

    @app.get("/api/trades")
    async def get_trades(status: str | None = None):
        """Get trades with optional status filter."""
        if status == "open":
            return tracker.trade_log.get_open_trades()
        elif status == "closed":
            return tracker.trade_log.get_closed_trades()
        return tracker.trade_log.trades

    return app


# Dashboard HTML - kept at module level for cleanliness
_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Champs Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f1419; color: #e7e9ea; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { margin-bottom: 20px; color: #1d9bf0; }
        .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .metric-card { background: #1c1f23; border-radius: 12px; padding: 20px; border: 1px solid #2f3336; }
        .metric-label { font-size: 12px; color: #71767b; text-transform: uppercase; margin-bottom: 8px; }
        .metric-value { font-size: 24px; font-weight: 600; }
        .positive { color: #00ba7c; }
        .negative { color: #f4212e; }
        .chart { background: #1c1f23; border-radius: 12px; padding: 20px; margin-bottom: 24px; border: 1px solid #2f3336; }
        .chart-title { font-size: 16px; margin-bottom: 16px; color: #71767b; }
        canvas { width: 100% !important; }
        .trades { background: #1c1f23; border-radius: 12px; padding: 20px; border: 1px solid #2f3336; }
        .trade { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #2f3336; }
        .trade:last-child { border-bottom: none; }
        .trade-symbol { font-weight: 600; }
        .trade-side { font-size: 12px; padding: 2px 8px; border-radius: 4px; margin-left: 8px; }
        .trade-side.long { background: #00ba7c33; color: #00ba7c; }
        .trade-side.short { background: #f4212e33; color: #f4212e; }
        .loading { text-align: center; padding: 40px; color: #71767b; }
        .error { background: #f4212e33; border: 1px solid #f4212e; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Trading Champs Dashboard</h1>

        <div id="error" class="error hidden"></div>

        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">Current Balance</div>
                <div class="metric-value" id="balance">-</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total P&L</div>
                <div class="metric-value" id="total-pnl">-</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Realized P&L</div>
                <div class="metric-value" id="realized-pnl">-</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Return %</div>
                <div class="metric-value" id="return-pct">-</div>
            </div>
        </div>

        <div class="chart">
            <div class="chart-title">Equity Curve</div>
            <canvas id="equityChart" height="200"></canvas>
        </div>

        <div class="chart">
            <div class="chart-title">Daily P&L</div>
            <canvas id="dailyChart" height="200"></canvas>
        </div>

        <div class="trades">
            <div class="chart-title">Recent Trades</div>
            <div id="trades-container">
                <div class="loading">Loading trades...</div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3.0.6/dist/purify.min.js"></script>
    <script>
    (function() {
        'use strict';

        var API_BASE = '/api';
        var equityChart, dailyChart;

        function formatCurrency(v) {
            return '$' + v.toFixed(2).replace(/\\B(?=(\\d{3})+(?!\\d))/g, ',');
        }

        function formatPct(v) {
            return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
        }

        function escapeHtml(str) {
            var div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }

        function fetchJSON(url) {
            return fetch(url).then(function(resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            });
        }

        function initCharts() {
            var commonOpts = {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { color: '#2f3336' }, ticks: { color: '#71767b' } },
                    y: { grid: { color: '#2f3336' }, ticks: { color: '#71767b' } }
                }
            };

            equityChart = new Chart(document.getElementById('equityChart'), {
                type: 'line',
                data: { labels: [], datasets: [{ data: [], borderColor: '#1d9bf0', backgroundColor: '#1d9bf033', fill: true, tension: 0.3 }] },
                options: commonOpts
            });

            dailyChart = new Chart(document.getElementById('dailyChart'), {
                type: 'bar',
                data: { labels: [], datasets: [{ data: [], backgroundColor: [] }] },
                options: commonOpts
            });
        }

        function renderTrades(trades) {
            var container = document.getElementById('trades-container');
            if (!trades || trades.length === 0) {
                container.innerHTML = '<div class="loading">No trades yet</div>';
                return;
            }

            var html = '';
            trades.forEach(function(t) {
                var symbol = escapeHtml(t.symbol);
                var side = escapeHtml(t.side ? t.side.value : '');
                var qty = escapeHtml(String(t.quantity));
                var price = formatCurrency(t.entry_price);
                var pnl = t.pnl || 0;
                var pnlClass = pnl >= 0 ? 'positive' : 'negative';
                var pnlStr = formatCurrency(pnl);

                html += '<div class="trade">' +
                    '<div><span class="trade-symbol">' + symbol + '</span>' +
                    '<span class="trade-side ' + side.toLowerCase() + '">' + side + '</span>' +
                    '<span style="color: #71767b; margin-left: 8px;">' + qty + ' @ ' + price + '</span></div>' +
                    '<div style="text-align: right;"><div class="' + pnlClass + '">' + pnlStr + '</div></div>' +
                    '</div>';
            });
            container.innerHTML = DOMPurify.sanitize(html);
        }

        function loadDashboard() {
            fetchJSON(API_BASE + '/dashboard')
                .then(function(data) {
                    document.getElementById('balance').textContent = formatCurrency(data.current_balance);

                    var totalPnlEl = document.getElementById('total-pnl');
                    totalPnlEl.textContent = formatCurrency(data.total_pnl);
                    totalPnlEl.className = 'metric-value ' + (data.total_pnl >= 0 ? 'positive' : 'negative');

                    var realizedEl = document.getElementById('realized-pnl');
                    realizedEl.textContent = formatCurrency(data.total_realized_pnl);
                    realizedEl.className = 'metric-value ' + (data.total_realized_pnl >= 0 ? 'positive' : 'negative');

                    var returnEl = document.getElementById('return-pct');
                    returnEl.textContent = formatPct(data.total_return_percent);
                    returnEl.className = 'metric-value ' + (data.total_return_percent >= 0 ? 'positive' : 'negative');

                    renderTrades(data.recent_trades);

                    document.getElementById('error').classList.add('hidden');
                })
                .then(function() {
                    return fetchJSON(API_BASE + '/equity-curve');
                })
                .then(function(curve) {
                    equityChart.data.labels = curve.map(function(d) { return d.date; });
                    equityChart.data.datasets[0].data = curve.map(function(d) { return d.equity; });
                    equityChart.update();
                })
                .then(function() {
                    return fetchJSON(API_BASE + '/dashboard');
                })
                .then(function(data) {
                    dailyChart.data.labels = data.daily_pnl.map(function(d) { return d.date; });
                    dailyChart.data.datasets[0].data = data.daily_pnl.map(function(d) { return d.total_pnl; });
                    dailyChart.data.datasets[0].backgroundColor = data.daily_pnl.map(function(d) {
                        return d.total_pnl >= 0 ? '#00ba7c' : '#f4212e';
                    });
                    dailyChart.update();
                })
                .catch(function(e) {
                    var errEl = document.getElementById('error');
                    errEl.textContent = 'Failed to load dashboard: ' + e.message;
                    errEl.classList.remove('hidden');
                });
        }

        initCharts();
        loadDashboard();
        setInterval(loadDashboard, 30000);
    })();
    </script>
</body>
</html>"""
