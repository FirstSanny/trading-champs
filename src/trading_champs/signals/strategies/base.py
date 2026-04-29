"""Base class providing common wiring for all strategies."""

from abc import ABC, abstractmethod
from typing import Sequence

from trading_champs.signals.detectors.crossover import SignalType
from trading_champs.signals.engine import SignalConfig


class AbstractStrategy(ABC):
    """Base class for all strategies.

    Provides the standard constructor signature expected by SignalService
    and the strategy registry.
    """

    def __init__(
        self,
        prices: Sequence[float],
        config: SignalConfig | None = None,
    ) -> None:
        self.prices: list[float] = list(prices)
        self.config: SignalConfig = config or SignalConfig()

    @property
    @abstractmethod
    def name(self) -> str:
        """Registry key for this strategy."""
        ...

    @abstractmethod
    def detect(self) -> list[SignalType]:
        """Subclasses implement signal generation."""
        ...
