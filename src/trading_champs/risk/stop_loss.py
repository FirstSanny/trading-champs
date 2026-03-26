"""Stop loss and take profit implementations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ExitLevel:
    """Exit level with price and reason."""

    price: float
    reason: str


class StopLoss(ABC):
    """Base class for stop loss strategies."""

    @abstractmethod
    def calculate(self, entry_price: float, high: float, low: float, **kwargs) -> ExitLevel:
        """Calculate stop loss level.

        Args:
            entry_price: Entry price of the position.
            high: Current high price.
            low: Current low price.

        Returns:
            ExitLevel with stop price and reason.
        """


class FixedStopLoss(StopLoss):
    """Fixed percentage stop loss."""

    def __init__(self, percent: float = 2.0):
        """Initialize fixed stop loss.

        Args:
            percent: Stop loss percentage (default 2.0).
        """
        self.percent = percent

    def calculate(self, entry_price: float, high: float, low: float, **kwargs) -> ExitLevel:
        stop_price = entry_price * (1 - self.percent / 100)
        return ExitLevel(price=stop_price, reason=f"fixed_{self.percent}%")


class TakeProfit(ABC):
    """Base class for take profit strategies."""

    @abstractmethod
    def calculate(self, entry_price: float, **kwargs) -> ExitLevel:
        """Calculate take profit level.

        Args:
            entry_price: Entry price of the position.

        Returns:
            ExitLevel with target price and reason.
        """


class FixedTakeProfit(TakeProfit):
    """Fixed percentage take profit."""

    def __init__(self, percent: float = 4.0):
        """Initialize fixed take profit.

        Args:
            percent: Take profit percentage (default 4.0).
        """
        self.percent = percent

    def calculate(self, entry_price: float, **kwargs) -> ExitLevel:
        target_price = entry_price * (1 + self.percent / 100)
        return ExitLevel(price=target_price, reason=f"fixed_{self.percent}%")


class ATRStopLoss(StopLoss):
    """ATR-based stop loss that adapts to volatility."""

    def __init__(self, atr_periods: int = 14, multiplier: float = 2.0):
        """Initialize ATR stop loss.

        Args:
            atr_periods: Number of periods for ATR calculation.
            multiplier: ATR multiplier for stop distance.
        """
        self.atr_periods = atr_periods
        self.multiplier = multiplier

    def calculate(
        self,
        entry_price: float,
        high: float,
        low: float,
        atr: float | None = None,
        **kwargs,
    ) -> ExitLevel:
        if atr is None:
            atr = self._calculate_simple_atr(high, low)

        stop_price = entry_price - (atr * self.multiplier)
        return ExitLevel(
            price=stop_price,
            reason=f"atr_{self.multiplier}x",
        )

    def _calculate_simple_atr(self, high: float, low: float) -> float:
        """Simple ATR approximation using high-low range."""
        return high - low


class TrailingStopLoss(StopLoss):
    """Trailing stop that locks in profits."""

    def __init__(self, percent: float = 2.0):
        """Initialize trailing stop loss.

        Args:
            percent: Trailing percentage below highest price.
        """
        self.percent = percent

    def calculate(
        self,
        entry_price: float,
        high: float,
        low: float,
        highest_since_entry: float | None = None,
        **kwargs,
    ) -> ExitLevel:
        if highest_since_entry is None:
            highest_since_entry = high

        stop_price = highest_since_entry * (1 - self.percent / 100)
        # Don't trail below entry
        stop_price = max(stop_price, entry_price * (1 - self.percent / 100))
        return ExitLevel(price=stop_price, reason=f"trailing_{self.percent}%")
