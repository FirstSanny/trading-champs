"""Dashboard data provider for P&L visualization."""

from dataclasses import dataclass
from datetime import datetime, timedelta

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


class DashboardProvider:
    """Provides data for the P&L dashboard."""

    def __init__(self, tracker: PnLTracker):
        """Initialize dashboard provider.

        Args:
            tracker: PnLTracker with trade history.
        """
        self.tracker = tracker
        self.metrics_calculator = MetricsCalculator(tracker)

    def get_dashboard_data(self, days: int = 30) -> DashboardData:
        """Get all dashboard data.

        Args:
            days: Number of days to include in daily P&L.

        Returns:
            DashboardData with all dashboard information.
        """
        current_balance = self.tracker.get_current_balance()
        initial_balance = self.tracker.initial_balance
        total_realized = self.tracker.get_total_realized_pnl()
        total_unrealized = self.tracker.get_total_unrealized_pnl()

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

        # Open positions summary
        open_positions = []
        for trade in self.tracker.trade_log.get_open_trades():
            if trade.side == TradeSide.LONG:
                pnl = (trade.exit_price or trade.entry_price) - trade.entry_price
            else:
                pnl = trade.entry_price - (trade.exit_price or trade.entry_price)
            pnl *= trade.quantity

            open_positions.append(
                {
                    "id": trade.id,
                    "symbol": trade.symbol,
                    "side": trade.side.value,
                    "quantity": trade.quantity,
                    "entry_price": trade.entry_price,
                    "current_price": trade.exit_price or trade.entry_price,
                    "unrealized_pnl": pnl,
                    "entry_time": trade.entry_time.isoformat(),
                }
            )

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
        )

    def get_equity_curve(self, days: int = 30) -> list[dict]:
        """Get equity curve data for charting.

        Args:
            days: Number of days to include.

        Returns:
            List of dicts with date and equity value.
        """
        curve = []
        today = datetime.now()
        running_equity = self.tracker.initial_balance

        for i in range(days):
            date = today - timedelta(days=days - i - 1)
            daily = self.tracker.get_daily_pnl(date)
            running_equity += daily.total_pnl
            curve.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "equity": running_equity,
                    "daily_pnl": daily.total_pnl,
                }
            )

        return curve
