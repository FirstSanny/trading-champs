"""Performance metrics calculation."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from trading_champs.pl.tracker import Trade, TradeLog, PnLTracker


@dataclass
class PerformanceMetrics:
    """Performance metrics summary."""
    total_return: float
    total_return_percent: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_percent: float
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    num_trades: int
    num_wins: int
    num_losses: int
    largest_win: float
    largest_loss: float
    avg_holding_time: timedelta | None


class MetricsCalculator:
    """Calculates trading performance metrics."""

    def __init__(self, tracker: PnLTracker):
        """Initialize metrics calculator.

        Args:
            tracker: PnLTracker with trade history.
        """
        self.tracker = tracker

    def calculate(self) -> PerformanceMetrics:
        """Calculate all performance metrics.

        Returns:
            PerformanceMetrics with calculated values.
        """
        closed_trades = self.tracker.trade_log.get_closed_trades()
        initial = self.tracker.initial_balance

        # Basic stats
        total_pnl = self.tracker.get_total_realized_pnl()
        total_return = total_pnl
        total_return_percent = (total_pnl / initial) * 100 if initial > 0 else 0

        wins = [t for t in closed_trades if t.pnl and t.pnl > 0]
        losses = [t for t in closed_trades if t.pnl and t.pnl <= 0]

        num_wins = len(wins)
        num_losses = len(losses)
        num_trades = len(closed_trades)

        win_rate = num_wins / num_trades if num_trades > 0 else 0

        # Profit factor
        total_wins = sum(t.pnl for t in wins)
        total_losses = abs(sum(t.pnl for t in losses)) if losses else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # Averages
        avg_win = total_wins / num_wins if num_wins > 0 else 0
        avg_loss = total_losses / num_losses if num_losses > 0 else 0

        # Largest win/loss
        largest_win = max((t.pnl for t in wins), default=0)
        largest_loss = min((t.pnl for t in losses), default=0)

        # Sharpe ratio (simplified - using daily returns)
        sharpe = self._calculate_sharpe_ratio()

        # Max drawdown
        max_dd, max_dd_pct = self._calculate_max_drawdown()

        # Average holding time
        avg_holding = self._calculate_avg_holding_time(closed_trades)

        return PerformanceMetrics(
            total_return=total_return,
            total_return_percent=total_return_percent,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            max_drawdown_percent=max_dd_pct,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            num_trades=num_trades,
            num_wins=num_wins,
            num_losses=num_losses,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_holding_time=avg_holding,
        )

    def _calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio.

        Args:
            risk_free_rate: Annual risk-free rate.

        Returns:
            Sharpe ratio.
        """
        closed_trades = self.tracker.trade_log.get_closed_trades()
        if len(closed_trades) < 2:
            return 0.0

        returns = []
        for trade in closed_trades:
            if trade.pnl and trade.pnl_percent:
                returns.append(trade.pnl_percent / 100)

        if not returns:
            return 0.0

        avg_return = sum(returns) / len(returns)
        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
        std_dev = variance ** 0.5

        if std_dev == 0:
            return 0.0

        sharpe = (avg_return - risk_free_rate / 252) / std_dev * (252 ** 0.5)
        return sharpe

    def _calculate_max_drawdown(self) -> tuple[float, float]:
        """Calculate maximum drawdown.

        Returns:
            Tuple of (max drawdown in dollars, max drawdown percent).
        """
        closed_trades = self.tracker.trade_log.get_closed_trades()
        if not closed_trades:
            return 0.0, 0.0

        trades_by_time = sorted(closed_trades, key=lambda t: t.exit_time or t.entry_time)
        peak = self.tracker.initial_balance
        max_dd = 0.0
        max_dd_pct = 0.0
        running_balance = self.tracker.initial_balance

        for trade in trades_by_time:
            if trade.pnl:
                running_balance += trade.pnl
                if running_balance > peak:
                    peak = running_balance
                dd = peak - running_balance
                if dd > max_dd:
                    max_dd = dd
                    max_dd_pct = (dd / peak) * 100 if peak > 0 else 0

        return max_dd, max_dd_pct

    def _calculate_avg_holding_time(self, trades: list[Trade]) -> timedelta | None:
        """Calculate average holding time.

        Args:
            trades: List of closed trades.

        Returns:
            Average holding time as timedelta or None.
        """
        holding_times = []
        for trade in trades:
            if trade.exit_time and trade.entry_time:
                delta = trade.exit_time - trade.entry_time
                holding_times.append(delta)

        if not holding_times:
            return None

        total_seconds = sum(t.total_seconds() for t in holding_times)
        avg_seconds = total_seconds / len(holding_times)
        return timedelta(seconds=avg_seconds)
