"""Moving average indicators."""

from typing import Sequence


def SMA(prices: Sequence[float], period: int) -> list[float]:
    """Simple Moving Average.

    Args:
        prices: Sequence of historical prices.
        period: Number of periods for the average.

    Returns:
        List of SMA values (same length as input, with None for insufficient data).
    """
    if len(prices) < period:
        return [None] * len(prices)

    result = [None] * (period - 1)
    window_sum = sum(prices[:period])

    for i in range(period - 1, len(prices)):
        result.append(window_sum / period)
        if i + 1 < len(prices):
            window_sum += prices[i + 1] - prices[i - period + 1]

    return result


def EMA(prices: Sequence[float], period: int) -> list[float]:
    """Exponential Moving Average.

    Args:
        prices: Sequence of historical prices.
        period: Number of periods for the EMA.

    Returns:
        List of EMA values.
    """
    if len(prices) < period:
        return [None] * len(prices)

    multiplier = 2 / (period + 1)
    result = [None] * (period - 1)

    # First EMA is SMA
    first_ema = sum(prices[:period]) / period
    result.append(first_ema)

    for i in range(period, len(prices)):
        ema = (prices[i] - result[-1]) * multiplier + result[-1]
        result.append(ema)

    return result
