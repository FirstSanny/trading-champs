"""Signal service for orchestration."""

from typing import Sequence

from trading_champs.signals.backtester import Backtester, BacktestResult
from trading_champs.signals.detectors.crossover import SignalType
from trading_champs.signals.engine import SignalConfig, SignalEngine


class SignalService:
    """Service for signal generation and strategy backtesting.

    Provides high-level API for generating trading signals and
    running backtests on historical data.
    """

    def __init__(self, prices: Sequence[float], config: SignalConfig | None = None):
        """Initialize signal service.

        Args:
            prices: Historical price data.
            config: Signal generation configuration.
        """
        self.prices = list(prices)
        self.config = config or SignalConfig()
        self._engine = SignalEngine(self.prices, self.config)

    def get_signals(self, strategy: str = "ma_crossover") -> list[SignalType]:
        """Generate trading signals using specified strategy.

        Args:
            strategy: Strategy to use ('ma_crossover', 'rsi', 'macd').

        Returns:
            List of trading signals.
        """
        if strategy == "rsi":
            return self._engine.generate_rsi_signals()
        elif strategy == "macd":
            return self._engine.generate_macd_signals()
        else:
            return self._engine.generate_ma_crossover_signals()

    def backtest(self, strategy: str = "ma_crossover") -> BacktestResult:
        """Run backtest for specified strategy.

        Args:
            strategy: Strategy to backtest.

        Returns:
            Backtest results with trade history and metrics.
        """
        signals = self.get_signals(strategy)
        backtester = Backtester(self.prices, signals)
        return backtester.run()

    def get_all_signals(self) -> dict[str, list[SignalType]]:
        """Generate signals using all available strategies.

        Returns:
            Dictionary mapping strategy name to signals.
        """
        return {
            "ma_crossover": self._engine.generate_ma_crossover_signals(),
            "rsi": self._engine.generate_rsi_signals(),
            "macd": self._engine.generate_macd_signals(),
        }

    def get_indicators(self) -> dict[str, list[float | None]]:
        """Get all indicator values.

        Returns:
            Dictionary of all calculated indicators.
        """
        return self._engine.get_indicator_values()
