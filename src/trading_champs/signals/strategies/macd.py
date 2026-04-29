"""MACD-based strategies."""

from trading_champs.signals.detectors.crossover import CrossoverDetector, SignalType
from trading_champs.signals.indicators.momentum import MACD
from trading_champs.signals.indicators.moving_averages import EMA

from .base import AbstractStrategy


class MACDStrategy(AbstractStrategy):
    """Plain MACD/signal line crossover."""

    @property
    def name(self) -> str:
        return "macd"

    def detect(self) -> list[SignalType]:
        macd_data = MACD(
            self.prices,
            fast_period=self.config.macd_fast,
            slow_period=self.config.macd_slow,
            signal_period=self.config.macd_signal,
        )
        detector = CrossoverDetector(macd_data["macd"], macd_data["signal"])
        return detector.detect()


class MACDTrendFilterStrategy(AbstractStrategy):
    """MACD crossover filtered by 200-day EMA trend."""

    @property
    def name(self) -> str:
        return "macd_trend"

    def detect(self) -> list[SignalType]:
        macd_data = MACD(
            self.prices,
            fast_period=self.config.macd_fast,
            slow_period=self.config.macd_slow,
            signal_period=self.config.macd_signal,
        )
        trend_ma = EMA(self.prices, self.config.trend_ma_period)
        detector = CrossoverDetector(macd_data["macd"], macd_data["signal"])
        raw = detector.detect()

        filtered: list[SignalType] = []
        for i, sig in enumerate(raw):
            if sig == SignalType.NEUTRAL:
                filtered.append(SignalType.NEUTRAL)
                continue
            price = self.prices[i]
            trend = trend_ma[i]
            if price is None or trend is None:
                filtered.append(SignalType.NEUTRAL)
                continue
            if sig == SignalType.BUY and price > trend:
                filtered.append(SignalType.BUY)
            elif sig == SignalType.SELL and price < trend:
                filtered.append(SignalType.SELL)
            else:
                filtered.append(SignalType.NEUTRAL)
        return filtered
