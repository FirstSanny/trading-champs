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


def ATR(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[float | None]:
    """Calculate Average True Range (ATR) indicator.

    True Range = max(H - L, |H - Close_prev|, |L - Close_prev|)

    Args:
        highs: Sequence of high prices.
        lows: Sequence of low prices.
        closes: Sequence of close prices.
        period: ATR period (default 14).

    Returns:
        List of ATR values (None for first 'period' values).
    """
    if len(highs) != len(lows) or len(highs) != len(closes):
        raise ValueError("highs, lows, and closes must have same length")

    n = len(highs)
    tr = [None] * n  # True Range

    # Calculate True Range for each bar
    for i in range(1, n):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]

        hl = high - low
        hc = abs(high - prev_close)
        lc = abs(low - prev_close)

        tr[i] = max(hl, hc, lc)

    # Calculate ATR using EMA (Wilder's smoothing)
    atr = [None] * n

    # First ATR is simple average of first 'period' TR values
    valid_tr = [v for v in tr[1 : period + 1] if v is not None]
    if valid_tr:
        atr[period] = sum(valid_tr) / len(valid_tr)

    # Subsequent ATR values use EMA-style smoothing
    for i in range(period + 1, n):
        if atr[i - 1] is not None and tr[i] is not None:
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr
