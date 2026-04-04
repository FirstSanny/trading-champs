"""Strategy Protocol definition."""

from typing import Protocol, Sequence

from trading_champs.signals.detectors.crossover import SignalType


class Strategy(Protocol):
    """Protocol that all trading strategies must satisfy.

    A strategy receives price data at construction and produces
    a list of SignalType values via detect().
    """

    @property
    def name(self) -> str:
        """Strategy identifier, used as registry key."""
        ...

    def detect(self) -> Sequence[SignalType]:
        """Run the strategy and return signals."""
        ...
