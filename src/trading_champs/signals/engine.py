"""Signal generation engine."""

from dataclasses import dataclass, field
from typing import Sequence

from trading_champs.signals.backtester import BacktestResult
from trading_champs.signals.detectors.crossover import SignalType
from trading_champs.signals.indicators.momentum import MACD, RSI
from trading_champs.signals.indicators.moving_averages import SMA
from trading_champs.signals.indicators.volatility import BollingerBands


@dataclass
class MAPeriodPreset:
    """A preset configuration for MA crossover periods."""

    name: str
    fast_period: int
    slow_period: int


# Predefined MA crossover period presets
MA_PRESETS: list[MAPeriodPreset] = [
    MAPeriodPreset(name="5/15", fast_period=5, slow_period=15),
    MAPeriodPreset(name="8/24", fast_period=8, slow_period=24),
    MAPeriodPreset(name="12/26", fast_period=12, slow_period=26),
    MAPeriodPreset(name="10/20", fast_period=10, slow_period=20),
]


@dataclass
class SignalConfig:
    """Configuration for signal generation."""

    period: int = 20  # General lookback period (used by Bollinger, etc.)
    fast_ma_period: int = 20
    slow_ma_period: int = 50
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    # Trend filter settings
    use_trend_filter: bool = False
    trend_ma_period: int = 200
    # RSI filter for Bollinger strategies
    use_rsi_filter: bool = False
    # Dynamic RSI settings
    use_dynamic_rsi: bool = False
    rsi_percentile_low: float = 25.0
    rsi_percentile_high: float = 75.0
    # MA presets for optimization
    ma_presets: list[MAPeriodPreset] = field(default_factory=lambda: MA_PRESETS.copy())


class SignalEngine:
    """Core engine for generating trading signals.

    Combines multiple indicators and detection strategies to produce
    actionable trading signals.
    """

    def __init__(self, prices: Sequence[float], config: SignalConfig | None = None):
        """Initialize signal engine.

        Args:
            prices: Historical price data.
            config: Signal generation configuration.
        """
        self.prices = list(prices)
        self.config = config or SignalConfig()

    def _strategy(self, cls):
        """Instantiate a strategy class with self.prices and self.config."""
        return cls(self.prices, self.config)

    def generate_ma_crossover_signals(self) -> list[SignalType]:
        """Generate signals based on moving average crossovers.

        Returns:
            List of signal types.
        """
        from trading_champs.signals.strategies.ma_crossover import MACrossoverStrategy

        return self._strategy(MACrossoverStrategy).detect()

    def generate_rsi_signals(self) -> list[SignalType]:
        """Generate signals based on RSI threshold crossings.

        Returns:
            List of signal types.
        """
        from trading_champs.signals.strategies.rsi import RSIStrategy

        return self._strategy(RSIStrategy).detect()

    def generate_macd_signals(self) -> list[SignalType]:
        """Generate signals based on MACD crossovers.

        Returns:
            List of signal types.
        """
        from trading_champs.signals.strategies.macd import MACDStrategy

        return self._strategy(MACDStrategy).detect()

    def generate_ma_crossover_signals_with_preset(self, preset: MAPeriodPreset) -> list[SignalType]:
        """Generate MA crossover signals using a specific period preset.

        Args:
            preset: MA period preset to use.

        Returns:
            List of signal types.
        """
        from trading_champs.signals.strategies.ma_crossover import MACrossoverPresetStrategy

        return MACrossoverPresetStrategy(self.prices, preset, self.config).detect()

    def generate_macd_signals_with_trend_filter(self) -> list[SignalType]:
        """Generate MACD signals filtered by 200-day MA trend.

        Only takes BUY when price is above 200-day MA, and SELL when below.

        Returns:
            List of signal types.
        """
        from trading_champs.signals.strategies.macd import MACDTrendFilterStrategy

        return self._strategy(MACDTrendFilterStrategy).detect()

    def _calculate_dynamic_rsi_thresholds(self) -> tuple[float, float]:
        """Calculate dynamic RSI thresholds based on historical percentiles.

        Returns:
            Tuple of (lower_threshold, upper_threshold).
        """
        rsi_values = RSI(self.prices, self.config.rsi_period)
        valid_rsi = [v for v in rsi_values if v is not None]

        if len(valid_rsi) < 10:
            # Not enough data, use defaults
            return self.config.rsi_oversold, self.config.rsi_overbought

        lower_percentile = self.config.rsi_percentile_low
        upper_percentile = self.config.rsi_percentile_high

        lower_threshold = float(sorted(valid_rsi)[int(len(valid_rsi) * lower_percentile / 100)])
        upper_threshold = float(sorted(valid_rsi)[int(len(valid_rsi) * upper_percentile / 100)])

        return lower_threshold, upper_threshold

    def generate_rsi_signals_with_dynamic_threshold(self) -> list[SignalType]:
        """Generate RSI signals using dynamic percentile-based thresholds.

        Returns:
            List of signal types.
        """
        from trading_champs.signals.strategies.rsi import RSIDynamicThresholdStrategy

        return self._strategy(RSIDynamicThresholdStrategy).detect()

    def generate_bollinger_signals(self) -> list[SignalType]:
        """Generate signals based on Bollinger Bands mean reversion.

        Buy when price closes below lower band (oversold).
        Sell when price closes above upper band (overbought).

        Returns:
            List of signal types.
        """
        from trading_champs.signals.strategies.bollinger import BollingerStrategy

        return self._strategy(BollingerStrategy).detect()

    def generate_bollinger_signals_with_rsi(self) -> list[SignalType]:
        """Generate Bollinger Bands signals with RSI confirmation.

        Buy only when price touches lower band AND RSI is oversold.
        Sell only when price touches upper band AND RSI is overbought.

        Returns:
            List of signal types.
        """
        from trading_champs.signals.strategies.bollinger import BollingerRSIStrategy

        return self._strategy(BollingerRSIStrategy).detect()

    def get_indicator_values(self) -> dict[str, list[float | None]]:
        """Get all calculated indicator values.

        Returns:
            Dictionary containing all indicator arrays.
        """
        fast_ma = SMA(self.prices, self.config.fast_ma_period)
        slow_ma = SMA(self.prices, self.config.slow_ma_period)
        rsi = RSI(self.prices, self.config.rsi_period)
        macd_data = MACD(
            self.prices,
            fast_period=self.config.macd_fast,
            slow_period=self.config.macd_slow,
            signal_period=self.config.macd_signal,
        )
        bb = BollingerBands(self.prices)

        return {
            "prices": self.prices,
            "fast_ma": fast_ma,
            "slow_ma": slow_ma,
            "rsi": rsi,
            "macd": macd_data["macd"],
            "macd_signal": macd_data["signal"],
            "macd_histogram": macd_data["histogram"],
            "bb_upper": bb["upper"],
            "bb_middle": bb["middle"],
            "bb_lower": bb["lower"],
        }

    def optimize_ma_presets(self) -> dict[str, BacktestResult]:
        """Run backtest across all MA presets and return results.

        Returns:
            Dictionary mapping preset name to backtest result.
        """
        from trading_champs.signals.backtester import Backtester

        results = {}
        for preset in self.config.ma_presets:
            signals = self.generate_ma_crossover_signals_with_preset(preset)
            backtester = Backtester(self.prices, signals)
            result = backtester.run()
            results[preset.name] = result

        return results
