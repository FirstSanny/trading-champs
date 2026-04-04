"""Moving Average Crossover strategies."""

from typing import Sequence

from trading_champs.signals.detectors.crossover import CrossoverDetector, SignalType
from trading_champs.signals.engine import SignalConfig
from trading_champs.signals.indicators.moving_averages import SMA

from .base import AbstractStrategy


class MACrossoverStrategy(AbstractStrategy):
    """Plain SMA fast/slow crossover."""

    @property
    def name(self) -> str:
        return "ma_crossover"

    def detect(self) -> list[SignalType]:
        fast_ma = SMA(self.prices, self.config.fast_ma_period)
        slow_ma = SMA(self.prices, self.config.slow_ma_period)
        detector = CrossoverDetector(fast_ma, slow_ma)
        return detector.detect()


class MACrossoverPresetStrategy(AbstractStrategy):
    """SMA crossover with a named period preset.

    Uses the preset from SignalConfig.ma_presets if available,
    otherwise falls back to SignalConfig.fast_ma_period / slow_ma_period.
    """

    @property
    def name(self) -> str:
        return "ma_crossover_preset"

    def detect(self) -> list[SignalType]:
        preset = self.config.ma_presets[0] if self.config.ma_presets else None
        if preset is None:
            # Fall back to config periods
            fast_ma = SMA(self.prices, self.config.fast_ma_period)
            slow_ma = SMA(self.prices, self.config.slow_ma_period)
        else:
            fast_ma = SMA(self.prices, preset.fast_period)
            slow_ma = SMA(self.prices, preset.slow_period)
        detector = CrossoverDetector(fast_ma, slow_ma)
        return detector.detect()
