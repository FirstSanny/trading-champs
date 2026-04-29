"""Crossover signal detection."""

from enum import Enum
from typing import Sequence


class SignalType(Enum):
    """Signal direction type."""

    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


class CrossoverDetector:
    """Detects crossover signals between two lines.

    A crossover occurs when one line crosses above or below another,
    typically used for moving average crossover strategies.
    """

    def __init__(self, line1: Sequence[float], line2: Sequence[float]):
        """Initialize detector with two lines.

        Args:
            line1: Primary line (e.g., fast moving average).
            line2: Secondary line (e.g., slow moving average).
        """
        self.line1 = list(line1)
        self.line2 = list(line2)

    def detect(self) -> list[SignalType]:
        """Detect crossover signals between the two lines.

        Returns:
            List of SignalType values - BUY when line1 crosses above line2,
            SELL when line1 crosses below line2, NEUTRAL otherwise.
        """
        if len(self.line1) != len(self.line2):
            raise ValueError("Both lines must have the same length")

        result: list[SignalType] = []

        for i in range(len(self.line1)):
            if i == 0:
                result.append(SignalType.NEUTRAL)
                continue

            prev1, curr1 = self.line1[i - 1], self.line1[i]
            prev2, curr2 = self.line2[i - 1], self.line2[i]

            if curr1 is None or curr2 is None or prev1 is None or prev2 is None:
                result.append(SignalType.NEUTRAL)
                continue

            prev_above = prev1 > prev2
            curr_above = curr1 > curr2

            if not prev_above and curr_above:
                result.append(SignalType.BUY)
            elif prev_above and not curr_above:
                result.append(SignalType.SELL)
            else:
                result.append(SignalType.NEUTRAL)

        return result

    def get_crossover_indices(self) -> tuple[list[int], list[int]]:
        """Get indices where crossovers occurred.

        Returns:
            Tuple of (buy_indices, sell_indices).
        """
        signals = self.detect()
        buy_indices = [i for i, s in enumerate(signals) if s == SignalType.BUY]
        sell_indices = [i for i, s in enumerate(signals) if s == SignalType.SELL]
        return buy_indices, sell_indices
