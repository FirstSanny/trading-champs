"""Trade logging and P&L tracking."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Sequence


class TradeSide(Enum):
    """Trade direction."""
    LONG = "long"
    SHORT = "short"


@dataclass
class Trade:
    """Represents a single trade."""
    id: str
    symbol: str
    side: TradeSide
    entry_price: float
    exit_price: float | None
    quantity: float
    entry_time: datetime
    exit_time: datetime | None
    pnl: float | None
    pnl_percent: float | None
    commission: float = 0.0
    tags: list[str] = field(default_factory=list)

    def close(self, exit_price: float, exit_time: datetime, commission: float = 0.0) -> None:
        """Close the trade and calculate P&L."""
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.commission += commission

        if self.side == TradeSide.LONG:
            raw_pnl = (exit_price - self.entry_price) * self.quantity
        else:
            raw_pnl = (self.entry_price - exit_price) * self.quantity

        self.pnl = raw_pnl - self.commission
        self.pnl_percent = (self.pnl / (self.entry_price * self.quantity)) * 100 if self.entry_price > 0 else 0


class TradeLog:
    """Log of all trades."""

    def __init__(self):
        """Initialize empty trade log."""
        self.trades: list[Trade] = []
        self._next_id = 1

    def add_trade(self, trade: Trade) -> None:
        """Add a trade to the log."""
        self.trades.append(trade)

    def get_open_trades(self) -> list[Trade]:
        """Get all open (unclosed) trades."""
        return [t for t in self.trades if t.exit_price is None]

    def get_closed_trades(self) -> list[Trade]:
        """Get all closed trades."""
        return [t for t in self.trades if t.exit_price is not None]

    def get_trades_by_symbol(self, symbol: str) -> list[Trade]:
        """Get all trades for a specific symbol."""
        return [t for t in self.trades if t.symbol == symbol]

    def get_trades_in_range(self, start: datetime, end: datetime) -> list[Trade]:
        """Get trades entered within a date range."""
        return [t for t in self.trades if start <= t.entry_time <= end]


@dataclass
class DailyPnL:
    """Daily P&L summary."""
    date: datetime
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    trade_count: int
    win_count: int
    loss_count: int


class PnLTracker:
    """Tracks P&L across all trades."""

    def __init__(self, initial_balance: float = 10000.0):
        """Initialize P&L tracker.

        Args:
            initial_balance: Starting account balance.
        """
        self.initial_balance = initial_balance
        self.trade_log = TradeLog()
        self.current_balance = initial_balance

    def open_trade(
        self,
        symbol: str,
        side: TradeSide,
        entry_price: float,
        quantity: float,
        entry_time: datetime | None = None,
        tags: list[str] | None = None,
    ) -> Trade:
        """Open a new trade.

        Args:
            symbol: Trading symbol.
            side: Trade direction.
            entry_price: Entry price.
            quantity: Position size.
            entry_time: Entry timestamp.
            tags: Optional tags for the trade.

        Returns:
            The opened Trade object.
        """
        if entry_time is None:
            entry_time = datetime.now()

        trade = Trade(
            id=f"trade_{self.trade_log._next_id}",
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            exit_price=None,
            quantity=quantity,
            entry_time=entry_time,
            exit_time=None,
            pnl=None,
            pnl_percent=None,
            tags=tags or [],
        )
        self.trade_log._next_id += 1
        self.trade_log.add_trade(trade)
        return trade

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_time: datetime | None = None,
        commission: float = 0.0,
    ) -> Trade | None:
        """Close an open trade.

        Args:
            trade_id: ID of the trade to close.
            exit_price: Exit price.
            exit_time: Exit timestamp.
            commission: Commission paid.

        Returns:
            The closed Trade or None if not found.
        """
        if exit_time is None:
            exit_time = datetime.now()

        for trade in self.trade_log.get_open_trades():
            if trade.id == trade_id:
                trade.close(exit_price, exit_time, commission)
                self.current_balance += trade.pnl if trade.pnl else 0
                return trade
        return None

    def get_total_realized_pnl(self) -> float:
        """Get total realized P&L from closed trades."""
        return sum(t.pnl for t in self.trade_log.get_closed_trades() if t.pnl is not None)

    def get_total_unrealized_pnl(self) -> float:
        """Get total unrealized P&L from open trades.

        Note: This returns 0 since we don't have current market prices.
        The dashboard should calculate unrealized P&L using current prices.
        """
        return 0.0

    def get_current_balance(self) -> float:
        """Get current account balance including unrealized P&L."""
        return self.current_balance + self.get_total_unrealized_pnl()

    def get_win_rate(self) -> float:
        """Calculate win rate across closed trades."""
        closed = self.trade_log.get_closed_trades()
        if not closed:
            return 0.0

        wins = sum(1 for t in closed if t.pnl and t.pnl > 0)
        return wins / len(closed)

    def get_daily_pnl(self, date: datetime) -> DailyPnL:
        """Get P&L summary for a specific date.

        Args:
            date: Date to get summary for.

        Returns:
            DailyPnL with that day's statistics.
        """
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date.replace(hour=23, minute=59, second=59, microsecond=999999)

        day_trades = self.trade_log.get_trades_in_range(start, end)
        closed = [t for t in day_trades if t.exit_time and start <= t.exit_time <= end]

        realized = sum(t.pnl for t in closed if t.pnl is not None)
        unrealized = sum(
            (t.exit_price or t.entry_price) - t.entry_price if t.side == TradeSide.LONG
            else t.entry_price - (t.exit_price or t.entry_price)
            for t in day_trades if t.exit_price is None
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
