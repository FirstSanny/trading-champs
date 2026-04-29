"""Threshold-based signal detection."""

from typing import Sequence

from trading_champs.signals.detectors.crossover import SignalType


class ThresholdDetector:
    """Detects signals based on threshold crossings.

    Used for indicators like RSI where values crossing above/below
    thresholds generate buy/sell signals.
    """

    def __init__(
        self,
        values: Sequence[float],
        upper_threshold: float = 70.0,
        lower_threshold: float = 30.0,
    ):
        """Initialize threshold detector.

        Args:
            values: Indicator values (e.g., RSI).
            upper_threshold: Upper threshold for sell signal (default 70).
            lower_threshold: Lower threshold for buy signal (default 30).
        """
        self.values = list(values)
        self.upper_threshold = upper_threshold
        self.lower_threshold = lower_threshold

    def detect(self) -> list[SignalType]:
        """Detect threshold crossing signals.

        Returns:
            List of SignalType values:
            - BUY: value crosses above lower_threshold
            - SELL: value crosses below upper_threshold
            - NEUTRAL: otherwise
        """
        result: list[SignalType] = []

        for i, value in enumerate(self.values):
            if value is None:
                result.append(SignalType.NEUTRAL)
                continue

            if i == 0:
                result.append(SignalType.NEUTRAL)
                continue

            prev = self.values[i - 1]

            if prev is None:
                result.append(SignalType.NEUTRAL)
                continue

            # Buy signal: crosses above lower threshold
            if prev <= self.lower_threshold and value > self.lower_threshold:
                result.append(SignalType.BUY)
            # Sell signal: crosses below upper threshold
            elif prev >= self.upper_threshold and value < self.upper_threshold:
                result.append(SignalType.SELL)
            else:
                result.append(SignalType.NEUTRAL)

        return result

    def get_oversold_indices(self) -> list[int]:
        """Get indices where value was oversold (below lower threshold)."""
        return [i for i, v in enumerate(self.values) if v is not None and v < self.lower_threshold]

    def get_overbought_indices(self) -> list[int]:
        """Get indices where value was overbought (above upper threshold)."""
        return [i for i, v in enumerate(self.values) if v is not None and v > self.upper_threshold]
