"""Data-driven strategy service for external-data strategies.

Provides high-level API for generating trading signals from strategies
that fetch external data (Twitter, news, options flow, social sentiment)
rather than analyzing price series.
"""

from dataclasses import dataclass
from typing import Any

from trading_champs.signals.backtester import SignalType
from trading_champs.signals.strategies.data_protocol import DataDrivenStrategy, StrategyMetadata
from trading_champs.signals.strategies.data_registry import DATA_STRATEGY_REGISTRY


@dataclass
class DataSignalResult:
    """Result of a data-driven signal generation."""

    symbol: str
    strategy: str
    signal: SignalType
    metadata: StrategyMetadata
    reason: str


class DataStrategyService:
    """Service for generating signals from external-data strategies.

    Works with DataDrivenStrategy implementations that fetch data from
    Twitter, news APIs, options flow providers, and social media.
    """

    def __init__(self, strategy_configs: dict[str, Any] | None = None) -> None:
        """Initialize the data strategy service.

        Args:
            strategy_configs: Optional dict mapping strategy name to
                (config, api_keys) tuple for initialization.
                E.g. {"ceo_twitter": (CEOTwitterConfig(), "api_key")}
        """
        self._configs = strategy_configs or {}
        self._instances: dict[str, DataDrivenStrategy] = {}

    def _get_instance(self, strategy: str) -> DataDrivenStrategy:
        """Get or create a strategy instance.

        Args:
            strategy: Strategy name from DATA_STRATEGY_REGISTRY.

        Returns:
            Cached or newly created strategy instance.
        """
        if strategy not in DATA_STRATEGY_REGISTRY:
            raise ValueError(
                f"Unknown data strategy: {strategy!r}. "
                f"Available: {list(DATA_STRATEGY_REGISTRY.keys())}"
            )
        if strategy not in self._instances:
            cls = DATA_STRATEGY_REGISTRY[strategy]
            config_and_keys = self._configs.get(strategy)
            if config_and_keys is not None:
                config, api_keys = config_and_keys
                self._instances[strategy] = cls(config=config, api_keys=api_keys)
            else:
                self._instances[strategy] = cls()
        return self._instances[strategy]

    def get_signal(self, strategy: str = "news_nlp", symbol: str = "AAPL") -> DataSignalResult:
        """Generate a trading signal for a symbol using a named strategy.

        Args:
            strategy: Strategy name. Supported: 'ceo_twitter', 'news_nlp',
                'options_flow', 'short_squeeze', 'sentiment'.
            symbol: Trading symbol to analyze.

        Returns:
            DataSignalResult with signal, metadata, and reason.

        Raises:
            ValueError: If strategy name is unknown.
        """
        instance = self._get_instance(strategy)
        signal, metadata, reason = instance.generate_signal(symbol)
        return DataSignalResult(
            symbol=symbol,
            strategy=instance.name,
            signal=signal,
            metadata=metadata,
            reason=reason,
        )

    def get_all_signals(self, symbol: str = "AAPL") -> dict[str, DataSignalResult]:
        """Generate signals using all available data-driven strategies.

        Args:
            symbol: Trading symbol to analyze.

        Returns:
            Dictionary mapping strategy name to DataSignalResult.
        """
        return {
            name: self.get_signal(strategy=name, symbol=symbol) for name in DATA_STRATEGY_REGISTRY
        }

    def get_signals_for_symbols(
        self, strategy: str, symbols: list[str]
    ) -> dict[str, DataSignalResult]:
        """Generate signals for multiple symbols using a named strategy.

        Args:
            strategy: Strategy name.
            symbols: List of trading symbols.

        Returns:
            Dictionary mapping symbol to DataSignalResult.
        """
        return {sym: self.get_signal(strategy=strategy, symbol=sym) for sym in symbols}
