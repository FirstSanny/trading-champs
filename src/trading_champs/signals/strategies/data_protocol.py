"""Data-driven strategy protocol for external-data strategies.

These strategies fetch external data (Twitter, news, options flow) rather than
analyzing price series. They require an API key or fetcher and return signals
based on off-chart data sources.
"""

from typing import Any, Protocol, TypedDict

from trading_champs.signals.detectors.crossover import SignalType


class StrategyMetadata(TypedDict, total=False):
    """Metadata returned alongside a signal."""

    confidence: float
    sentiment: float
    signal_count: int
    urgency: str | None
    strength: str | None
    side: str | None
    event_type: str | None
    phase: str | None
    squeeze_probability: float | None


class DataDrivenStrategy(Protocol):
    """Protocol for strategies that fetch external data.

    These differ from price-series strategies (AbstractStrategy) in that they
    require external data sources (Twitter, news, options flow) and are
    typically async or fetcher-based.
    """

    @property
    def name(self) -> str:
        """Strategy identifier, used as registry key."""
        ...

    def generate_signal(self, symbol: str) -> tuple[SignalType, StrategyMetadata, str]:
        """Generate a trading signal for a symbol.

        Args:
            symbol: Trading symbol to analyze.

        Returns:
            Tuple of (signal, metadata, reason):
            - signal: BUY, SELL, or NEUTRAL
            - metadata: Dict with strategy-specific metrics (confidence, etc.)
            - reason: Human-readable explanation of the signal
        """
        ...
