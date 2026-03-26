"""Signal generation engine."""

from dataclasses import dataclass
from typing import Sequence

from trading_champs.signals.detectors.crossover import CrossoverDetector, SignalType
from trading_champs.signals.detectors.threshold import ThresholdDetector
from trading_champs.signals.indicators.moving_averages import EMA, SMA
from trading_champs.signals.indicators.momentum import MACD, RSI
from trading_champs.signals.indicators.volatility import BollingerBands


@dataclass
class SignalConfig:
    """Configuration for signal generation."""
    fast_ma_period: int = 10
    slow_ma_period: int = 20
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9


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

    def generate_ma_crossover_signals(self) -> list[SignalType]:
        """Generate signals based on moving average crossovers.

        Returns:
            List of signal types.
        """
        fast_ma = SMA(self.prices, self.config.fast_ma_period)
        slow_ma = SMA(self.prices, self.config.slow_ma_period)

        detector = CrossoverDetector(fast_ma, slow_ma)
        return detector.detect()

    def generate_rsi_signals(self) -> list[SignalType]:
        """Generate signals based on RSI threshold crossings.

        Returns:
            List of signal types.
        """
        rsi_values = RSI(self.prices, self.config.rsi_period)
        detector = ThresholdDetector(
            rsi_values,
            upper_threshold=self.config.rsi_overbought,
            lower_threshold=self.config.rsi_oversold,
        )
        return detector.detect()

    def generate_macd_signals(self) -> list[SignalType]:
        """Generate signals based on MACD crossovers.

        Returns:
            List of signal types.
        """
        macd_data = MACD(
            self.prices,
            fast_period=self.config.macd_fast,
            slow_period=self.config.macd_slow,
            signal_period=self.config.macd_signal,
        )

        detector = CrossoverDetector(macd_data["macd"], macd_data["signal"])
        return detector.detect()

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
