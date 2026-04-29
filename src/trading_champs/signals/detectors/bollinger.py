"""Bollinger Bands mean reversion signal detection."""

from typing import Sequence

from trading_champs.signals.detectors.crossover import SignalType
from trading_champs.signals.indicators.volatility import BollingerBands


class BollingerBandsDetector:
    """Detects mean reversion signals using Bollinger Bands.

    Generates signals when price touches or crosses the bands:
    - BUY: Price closes below lower band (oversold, expect reversion up)
    - SELL: Price closes above upper band (overbought, expect reversion down)
    - Exit signals when price crosses middle band
    """

    def __init__(
        self,
        prices: Sequence[float],
        period: int = 20,
        num_std: float = 2.0,
        use_rsi_filter: bool = False,
        rsi_values: Sequence[float] | None = None,
        rsi_oversold: float = 30.0,
    ):
        """Initialize Bollinger Bands detector.

        Args:
            prices: Historical price sequence.
            period: Bollinger Bands period (default 20).
            num_std: Standard deviations for bands (default 2.0).
            use_rsi_filter: If True, only generate BUY when RSI also oversold.
            rsi_values: RSI values for filtering (required if use_rsi_filter=True).
            rsi_oversold: RSI threshold for oversold (default 30).
        """
        self.prices = list(prices)
        self.period = period
        self.num_std = num_std
        self.use_rsi_filter = use_rsi_filter
        self.rsi_values = list(rsi_values) if rsi_values else []
        self.rsi_oversold = rsi_oversold

        # Calculate Bollinger Bands
        self.bands = BollingerBands(prices, period, num_std)

    def detect(self) -> list[SignalType]:
        """Detect Bollinger Bands mean reversion signals.

        Returns:
            List of SignalType values:
            - BUY: Price closes below lower band (and RSI filter passes if enabled)
            - SELL: Price closes above upper band
            - NEUTRAL: Price within bands
        """
        result: list[SignalType] = []
        lower = self.bands["lower"]
        middle = self.bands["middle"]
        upper = self.bands["upper"]

        for i, price in enumerate(self.prices):
            if price is None:
                result.append(SignalType.NEUTRAL)
                continue

            lower_val = lower[i]
            middle_val = middle[i]
            upper_val = upper[i]

            # Need valid bands
            if lower_val is None or middle_val is None or upper_val is None:
                result.append(SignalType.NEUTRAL)
                continue

            # Check RSI filter for BUY signals
            if self.use_rsi_filter and self.rsi_values:
                rsi = self.rsi_values[i] if i < len(self.rsi_values) else None
                if rsi is not None and rsi >= self.rsi_oversold:
                    # RSI not oversold, skip this index
                    result.append(SignalType.NEUTRAL)
                    continue

            # BUY: Price closes below lower band (mean reversion up)
            if price < lower_val:
                result.append(SignalType.BUY)
            # SELL: Price closes above upper band (mean reversion down)
            elif price > upper_val:
                result.append(SignalType.SELL)
            else:
                result.append(SignalType.NEUTRAL)

        return result

    def get_exit_signals(self) -> list[SignalType]:
        """Detect exit signals based on middle band crossings.

        For long positions: exit when price crosses above middle band
        For short positions: exit when price crosses below middle band

        Returns:
            List of exit signal types:
            - BUY: Exit short (price crossed above middle from below)
            - SELL: Exit long (price crossed below middle from above)
            - NEUTRAL: No exit signal
        """
        result: list[SignalType] = []
        middle = self.bands["middle"]

        for i, price in enumerate(self.prices):
            if price is None:
                result.append(SignalType.NEUTRAL)
                continue

            middle_val = middle[i]
            if middle_val is None:
                result.append(SignalType.NEUTRAL)
                continue

            if i == 0:
                result.append(SignalType.NEUTRAL)
                continue

            prev_price = self.prices[i - 1]
            prev_middle = middle[i - 1]

            if prev_price is None or prev_middle is None:
                result.append(SignalType.NEUTRAL)
                continue

            # Exit short: price crosses above middle band
            if prev_price <= prev_middle and price > middle_val:
                result.append(SignalType.BUY)
            # Exit long: price crosses below middle band
            elif prev_price >= prev_middle and price < middle_val:
                result.append(SignalType.SELL)
            else:
                result.append(SignalType.NEUTRAL)

        return result

    def get_touch_indices(self) -> tuple[list[int], list[int]]:
        """Get indices where price touched the bands.

        Returns:
            Tuple of (lower_touch_indices, upper_touch_indices).
        """
        lower_touches: list[int] = []
        upper_touches: list[int] = []
        lower = self.bands["lower"]
        upper = self.bands["upper"]

        for i, price in enumerate(self.prices):
            if price is None:
                continue

            lower_val = lower[i]
            upper_val = upper[i]

            if lower_val is not None and price <= lower_val:
                lower_touches.append(i)
            if upper_val is not None and price >= upper_val:
                upper_touches.append(i)

        return lower_touches, upper_touches
