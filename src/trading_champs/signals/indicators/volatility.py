"""Volatility indicators."""

import math
from typing import Sequence

from trading_champs.signals.indicators.moving_averages import SMA


def BollingerBands(
    prices: Sequence[float],
    period: int = 20,
    num_std: float = 2.0,
) -> dict[str, list[float]]:
    """Bollinger Bands.

    Args:
        prices: Sequence of historical prices.
        period: Number of periods for SMA (default 20).
        num_std: Number of standard deviations (default 2.0).

    Returns:
        Dictionary with 'upper', 'middle', and 'lower' band values.
    """
    middle = SMA(prices, period)
    upper = [None] * len(prices)
    lower = [None] * len(prices)

    for i in range(period - 1, len(prices)):
        if middle[i] is None:
            continue

        window = prices[i - period + 1 : i + 1]
        variance = sum((p - middle[i]) ** 2 for p in window) / period
        std = math.sqrt(variance)

        upper[i] = middle[i] + num_std * std
        lower[i] = middle[i] - num_std * std

    return {"upper": upper, "middle": middle, "lower": lower}
