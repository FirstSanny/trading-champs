"""Dashboard data provider for P&L visualization."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from trading_champs.data.connectors.alpaca_connector import AlpacaPaperConnector
from trading_champs.pl.metrics import MetricsCalculator, PerformanceMetrics
from trading_champs.pl.tracker import DailyPnL, PnLTracker, Trade, TradeSide


@dataclass
class DashboardData:
    """Data structure for dashboard rendering."""

    current_balance: float
    initial_balance: float
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_pnl: float
    total_return_percent: float
    daily_pnl: list[DailyPnL]
    recent_trades: list[Trade]
    performance_metrics: PerformanceMetrics | None
    open_positions: list[dict]
    alpaca_connected: bool = False
    alpaca_account: Optional[dict] = None
    mode: str = "paper"


class DashboardProvider:
    """Provides data for the P&L dashboard."""

    def __init__(
        self, tracker: PnLTracker, alpaca_connector: Optional[AlpacaPaperConnector] = None
    ):
        """Initialize dashboard provider.

        Args:
            tracker: PnLTracker with trade history.
            alpaca_connector: Optional AlpacaPaperConnector for live account data.
        """
        self.tracker = tracker
        self.metrics_calculator = MetricsCalculator(tracker)
        self._alpaca_connector = alpaca_connector

    def set_alpaca_connector(self, connector: AlpacaPaperConnector) -> None:
        """Set the Alpaca connector for live account data."""
        self._alpaca_connector = connector

    def get_dashboard_data(self, days: int = 30, mode: str = "paper") -> DashboardData:
        """Get all dashboard data.

        Args:
            days: Number of days to include in daily P&L.
            mode: 'paper' or 'live' trading mode.

        Returns:
            DashboardData with all dashboard information.
        """
        current_balance = self.tracker.get_current_balance()
        initial_balance = self.tracker.initial_balance
        total_realized = self.tracker.get_total_realized_pnl()
        total_unrealized = self.tracker.get_total_unrealized_pnl()
        alpaca_connected = False
        alpaca_account: Optional[dict] = None

        # Pull live account data from Alpaca if connector is set
        if self._alpaca_connector is not None:
            try:
                if self._alpaca_connector.is_connected():
                    account = self._alpaca_connector.get_account()
                    # Use live values from Alpaca when available
                    live_equity = float(account.get("equity", 0))
                    live_portfolio_value = float(account.get("portfolio_value", 0))
                    if live_portfolio_value > 0:
                        current_balance = live_portfolio_value
                    elif live_equity > 0:
                        current_balance = live_equity
                    alpaca_connected = True
                    alpaca_account = account
            except Exception:
                pass  # Fall back to tracker data

        # Daily P&L for the last N days
        daily_pnl = []
        today = datetime.now()
        for i in range(days):
            date = today - timedelta(days=i)
            daily = self.tracker.get_daily_pnl(date)
            daily_pnl.append(daily)

        daily_pnl.reverse()  # Oldest first

        # Recent trades (last 10)
        all_trades = sorted(
            self.tracker.trade_log.trades,
            key=lambda t: t.entry_time,
            reverse=True,
        )
        recent_trades = all_trades[:10]

        # Performance metrics
        metrics = None
        if self.tracker.trade_log.get_closed_trades():
            metrics = self.metrics_calculator.calculate()

        # Open positions summary - merge tracker trades with Alpaca positions
        open_positions = []

        # Get Alpaca positions if connected
        alpaca_positions: dict[str, dict] = {}
        if alpaca_connected and self._alpaca_connector is not None:
            try:
                for pos in self._alpaca_connector.get_positions():
                    alpaca_positions[pos["symbol"]] = pos
            except Exception:
                pass

        for trade in self.tracker.trade_log.get_open_trades():
            if trade.side == TradeSide.LONG:
                pnl = (trade.exit_price or trade.entry_price) - trade.entry_price
            else:
                pnl = trade.entry_price - (trade.exit_price or trade.entry_price)
            pnl *= trade.quantity

            pos_data = {
                "id": trade.id,
                "symbol": trade.symbol,
                "side": trade.side.value,
                "quantity": trade.quantity,
                "entry_price": trade.entry_price,
                "current_price": trade.exit_price or trade.entry_price,
                "unrealized_pnl": pnl,
                "entry_time": trade.entry_time.isoformat(),
            }

            # Enhance with live Alpaca data if available
            if trade.symbol in alpaca_positions:
                ap = alpaca_positions[trade.symbol]
                pos_data["current_price"] = float(
                    ap.get("current_price", pos_data["current_price"])
                )
                pos_data["market_value"] = float(ap.get("market_value", 0))
                pos_data["unrealized_pnl"] = float(ap.get("unrealized_pl", pnl))
                pos_data["alpaca_position"] = True

            open_positions.append(pos_data)

        return DashboardData(
            current_balance=current_balance,
            initial_balance=initial_balance,
            total_realized_pnl=total_realized,
            total_unrealized_pnl=total_unrealized,
            total_pnl=total_realized + total_unrealized,
            total_return_percent=(
                (total_realized / initial_balance * 100) if initial_balance > 0 else 0
            ),
            daily_pnl=daily_pnl,
            recent_trades=recent_trades,
            performance_metrics=metrics,
            open_positions=open_positions,
            alpaca_connected=alpaca_connected,
            alpaca_account=alpaca_account,
            mode=mode,
        )

    def get_equity_curve(
        self, days: int = 30, mode: str = "paper", strategy: str | None = None
    ) -> list[dict]:
        """Get equity curve data for charting.

        Args:
            days: Number of days to include.
            mode: 'paper' or 'live' trading mode.
            strategy: Optional strategy name to filter by.

        Returns:
            List of dicts with date and equity value.
        """
        curve = []
        today = datetime.now()
        running_equity = self.tracker.initial_balance

        for i in range(days):
            date = today - timedelta(days=days - i - 1)
            daily = self._get_daily_pnl_for_strategy(date, strategy)
            running_equity += daily.total_pnl
            curve.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "equity": running_equity,
                    "daily_pnl": daily.total_pnl,
                }
            )

        return curve

    def _get_daily_pnl_for_strategy(self, date: datetime, strategy: str | None) -> DailyPnL:
        """Get daily P&L for a specific strategy or all trades."""
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date.replace(hour=23, minute=59, second=59, microsecond=999999)

        if strategy:
            day_trades = [
                t
                for t in self.tracker.trade_log.trades
                if t.strategy == strategy and start <= t.entry_time <= end
            ]
        else:
            day_trades = [t for t in self.tracker.trade_log.trades if start <= t.entry_time <= end]

        closed = [t for t in day_trades if t.exit_time and start <= t.exit_time <= end]
        realized = sum(t.pnl for t in closed if t.pnl is not None)
        unrealized = sum(
            (
                (t.exit_price or t.entry_price) - t.entry_price
                if t.side == TradeSide.LONG
                else t.entry_price - (t.exit_price or t.entry_price)
            )
            for t in day_trades
            if t.exit_price is None
        )
        wins = sum(1 for t in closed if t.pnl and t.pnl > 0)
        losses = sum(1 for t in closed if t.pnl and t.pnl <= 0)

        return DailyPnL(
            date=date,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            total_pnl=realized + unrealized,
            trade_count=len(day_trades),
            win_count=wins,
            loss_count=losses,
        )

    def get_strategies(self) -> list[str]:
        """Get all strategy names.

        Returns strategies from STRATEGY_REGISTRY and DATA_STRATEGY_REGISTRY (single source of truth),
        augmented with any strategy names that appear in trades but are not
        in the registry (e.g. legacy strategies).
        """
        from trading_champs.signals.strategies import DATA_STRATEGY_REGISTRY, STRATEGY_REGISTRY

        strategies = set(STRATEGY_REGISTRY.keys()) | set(DATA_STRATEGY_REGISTRY.keys())
        for trade in self.tracker.trade_log.trades:
            if trade.strategy:
                strategies.add(trade.strategy)
        return sorted(strategies)

    def get_strategy_equity_curves(
        self, days: int = 30, mode: str = "paper"
    ) -> dict[str, list[dict]]:
        """Get equity curves for all strategies.

        Args:
            days: Number of days to include.
            mode: 'paper' or 'live' trading mode.

        Returns:
            Dict mapping strategy name to equity curve data.
        """
        strategies = self.get_strategies()
        result = {}
        for strat in strategies:
            result[strat] = self.get_equity_curve(days, mode, strat)
        return result
