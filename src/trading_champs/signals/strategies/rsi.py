"""RSI-based strategies."""

from typing import Sequence

from trading_champs.signals.detectors.crossover import SignalType
from trading_champs.signals.detectors.threshold import ThresholdDetector
from trading_champs.signals.engine import SignalConfig
from trading_champs.signals.indicators.momentum import RSI

from .base import AbstractStrategy


class RSIStrategy(AbstractStrategy):
    """Fixed-threshold RSI."""

    @property
    def name(self) -> str:
        return "rsi"

    def detect(self) -> list[SignalType]:
        rsi_values = RSI(self.prices, self.config.rsi_period)
        detector = ThresholdDetector(
            rsi_values,
            upper_threshold=self.config.rsi_overbought,
            lower_threshold=self.config.rsi_oversold,
        )
        return detector.detect()


class RSIDynamicThresholdStrategy(AbstractStrategy):
    """RSI with percentile-based dynamic thresholds."""

    @property
    def name(self) -> str:
        return "rsi_dynamic"

    def _calc_thresholds(self) -> tuple[float, float]:
        rsi_values = RSI(self.prices, self.config.rsi_period)
        valid = [v for v in rsi_values if v is not None]
        if len(valid) < 10:
            return self.config.rsi_oversold, self.config.rsi_overbought
        lower = float(sorted(valid)[int(len(valid) * self.config.rsi_percentile_low / 100)])
        upper = float(sorted(valid)[int(len(valid) * self.config.rsi_percentile_high / 100)])
        return lower, upper

    def detect(self) -> list[SignalType]:
        rsi_values = RSI(self.prices, self.config.rsi_period)
        lower, upper = self._calc_thresholds()
        detector = ThresholdDetector(rsi_values, upper_threshold=upper, lower_threshold=lower)
        return detector.detect()
