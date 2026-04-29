"""Momentum indicators."""

from typing import Sequence

from trading_champs.signals.indicators.moving_averages import EMA


def RSI(prices: Sequence[float], period: int = 14) -> list[float]:
    """Relative Strength Index.

    Args:
        prices: Sequence of historical prices.
        period: Number of periods for RSI (default 14).

    Returns:
        List of RSI values (0-100).
    """
    if len(prices) < period + 1:
        return [None] * len(prices)

    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    result = [None] * period

    gains = [c if c > 0 else 0 for c in changes[:period]]
    losses = [-c if c < 0 else 0 for c in changes[:period]]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        result.append(100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(100 - (100 / (1 + rs)))

    for i in range(period, len(changes)):
        gain = changes[i] if changes[i] > 0 else 0
        loss = -changes[i] if changes[i] < 0 else 0

        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - (100 / (1 + rs)))

    return result


def MACD(
    prices: Sequence[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict[str, list[float]]:
    """MACD (Moving Average Convergence Divergence).

    Args:
        prices: Sequence of historical prices.
        fast_period: Fast EMA period (default 12).
        slow_period: Slow EMA period (default 26).
        signal_period: Signal line period (default 9).

    Returns:
        Dictionary with 'macd', 'signal', and 'histogram' values.
    """
    fast_ema = EMA(prices, fast_period)
    slow_ema = EMA(prices, slow_period)

    macd_line = [
        f - s if f is not None and s is not None else None for f, s in zip(fast_ema, slow_ema)
    ]

    valid_macd = [v for v in macd_line if v is not None]
    if len(valid_macd) < signal_period:
        return {
            "macd": macd_line,
            "signal": [None] * len(macd_line),
            "histogram": [None] * len(macd_line),
        }

    signal_line = EMA(valid_macd, signal_period)

    # Pad signal line to match macd_line length
    padded_signal = [None] * (len(macd_line) - len(signal_line)) + signal_line

    histogram = [
        m - s if m is not None and s is not None else None for m, s in zip(macd_line, padded_signal)
    ]

    return {
        "macd": macd_line,
        "signal": padded_signal,
        "histogram": histogram,
    }
