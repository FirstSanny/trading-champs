"""Bollinger Bands strategies."""

from trading_champs.signals.detectors.bollinger import BollingerBandsDetector
from trading_champs.signals.detectors.crossover import SignalType
from trading_champs.signals.indicators.momentum import RSI

from .base import AbstractStrategy


class BollingerStrategy(AbstractStrategy):
    """Bollinger Bands mean reversion."""

    @property
    def name(self) -> str:
        return "bollinger"

    def detect(self) -> list[SignalType]:
        rsi_values = None
        if self.config.use_rsi_filter:
            rsi_values = RSI(self.prices, self.config.rsi_period)
        detector = BollingerBandsDetector(
            self.prices,
            period=self.config.period,
            num_std=2.0,
            use_rsi_filter=self.config.use_rsi_filter,
            rsi_values=rsi_values,
            rsi_oversold=self.config.rsi_oversold,
        )
        return detector.detect()


class BollingerRSIStrategy(AbstractStrategy):
    """Bollinger Bands with mandatory RSI confirmation."""

    @property
    def name(self) -> str:
        return "bollinger_rsi"

    def detect(self) -> list[SignalType]:
        rsi_values = RSI(self.prices, self.config.rsi_period)
        detector = BollingerBandsDetector(
            self.prices,
            period=self.config.period,
            num_std=2.0,
            use_rsi_filter=True,
            rsi_values=rsi_values,
            rsi_oversold=self.config.rsi_oversold,
        )
        return detector.detect()
