"""Position sizing strategies."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PositionSize:
    """Calculated position size."""

    units: float
    dollar_risk: float
    risk_percent: float


class PositionSizer(ABC):
    """Base class for position sizing strategies."""

    @abstractmethod
    def calculate(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float | None = None,
    ) -> PositionSize:
        """Calculate position size.

        Args:
            account_balance: Current account balance.
            entry_price: Entry price for the position.
            stop_loss_price: Stop loss price (if known).

        Returns:
            PositionSize with units, dollar risk, and risk percent.
        """


class FixedSize(PositionSizer):
    """Fixed number of units per trade."""

    def __init__(self, units: float):
        """Initialize fixed size sizer.

        Args:
            units: Fixed number of units per trade.
        """
        self.units = units

    def calculate(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float | None = None,
    ) -> PositionSize:
        return PositionSize(
            units=self.units,
            dollar_risk=0.0,
            risk_percent=0.0,
        )


class PercentRisk(PositionSizer):
    """Risk a fixed percentage of account per trade."""

    def __init__(self, risk_percent: float = 1.0):
        """Initialize percent risk sizer.

        Args:
            risk_percent: Percentage of account to risk (default 1.0).
        """
        self.risk_percent = risk_percent

    def calculate(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float | None = None,
    ) -> PositionSize:
        if stop_loss_price is None:
            raise ValueError("stop_loss_price required for PercentRisk sizing")

        dollar_risk = account_balance * (self.risk_percent / 100)
        price_risk = abs(entry_price - stop_loss_price)
        units = dollar_risk / price_risk if price_risk > 0 else 0

        return PositionSize(
            units=units,
            dollar_risk=dollar_risk,
            risk_percent=self.risk_percent,
        )


class KellyCriterion(PositionSizer):
    """Kelly Criterion for optimal position sizing.

    Requires historical win rate and average win/loss amounts.
    """

    def __init__(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        kelly_fraction: float = 0.25,
    ):
        """Initialize Kelly Criterion sizer.

        Args:
            win_rate: Historical win rate (0.0 to 1.0).
            avg_win: Average win amount.
            avg_loss: Average loss amount.
            kelly_fraction: Kelly fraction to use (default 0.25, conservative).
        """
        self.win_rate = win_rate
        self.avg_win = avg_win
        self.avg_loss = avg_loss
        self.kelly_fraction = kelly_fraction

    def calculate(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float | None = None,
    ) -> PositionSize:
        win_loss_ratio = self.avg_win / self.avg_loss if self.avg_loss != 0 else 0
        p = self.win_rate
        q = 1 - p

        # Kelly formula: f* = (bp - q) / b
        kelly = (win_loss_ratio * p - q) / win_loss_ratio if win_loss_ratio > 0 else 0
        kelly = max(0, kelly) * self.kelly_fraction

        dollar_risk = account_balance * kelly
        units = dollar_risk / abs(entry_price - stop_loss_price) if stop_loss_price else 0

        return PositionSize(
            units=units,
            dollar_risk=dollar_risk,
            risk_percent=kelly * 100,
        )
