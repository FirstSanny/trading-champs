"""Backtesting framework for trading strategies."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from trading_champs.signals.detectors.crossover import SignalType


class PositionSide(Enum):
    """Position direction."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class Trade:
    """Represents a single trade."""

    entry_index: int
    entry_price: float
    exit_index: int
    exit_price: float
    side: PositionSide
    pnl: float
    pnl_pct: float


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    trades: list[Trade] = field(default_factory=list)
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    win_rate: float = 0.0
    num_trades: int = 0
    num_wins: int = 0
    num_losses: int = 0

    def add_trade(self, trade: Trade) -> None:
        """Add a trade and update statistics."""
        self.trades.append(trade)
        self.total_pnl += trade.pnl
        self.total_pnl_pct += trade.pnl_pct
        self.num_trades += 1
        if trade.pnl > 0:
            self.num_wins += 1
        else:
            self.num_losses += 1
        if self.num_trades > 0:
            self.win_rate = self.num_wins / self.num_trades


class Backtester:
    """Framework for backtesting trading strategies.

    Simulates trading based on signals and calculates performance metrics.
    """

    def __init__(
        self,
        prices: Sequence[float],
        signals: Sequence[SignalType],
        initial_capital: float = 10000.0,
    ):
        """Initialize backtester.

        Args:
            prices: Historical price data.
            signals: Generated trading signals.
            initial_capital: Starting capital for backtest.
        """
        self.prices = list(prices)
        self.signals = list(signals)
        self.initial_capital = initial_capital

        if len(prices) != len(signals):
            raise ValueError("Prices and signals must have the same length")

    def run(self) -> BacktestResult:
        """Run backtest simulation.

        Returns:
            BacktestResult with trade history and performance metrics.
        """
        result = BacktestResult()
        position: PositionSide = PositionSide.FLAT
        entry_price = 0.0
        entry_index = 0

        for i, (price, signal) in enumerate(zip(self.prices, self.signals)):
            if signal == SignalType.BUY and position == PositionSide.FLAT:
                position = PositionSide.LONG
                entry_price = price
                entry_index = i

            elif signal == SignalType.SELL and position != PositionSide.FLAT:
                exit_price = price
                pnl = exit_price - entry_price
                pnl_pct = (pnl / entry_price) * 100 if entry_price != 0 else 0

                trade = Trade(
                    entry_index=entry_index,
                    entry_price=entry_price,
                    exit_index=i,
                    exit_price=exit_price,
                    side=position,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                )
                result.add_trade(trade)
                position = PositionSide.FLAT

        return result
