"""Short Squeeze Detection Strategy.

Identifies stocks with high short interest and triggers trades during
short squeeze events. Famous examples: GameStop (GME), AMC, BBBY, VW.

Key components:
1. Track short interest data from FINRA, Ortex, S3 Partners
2. Identify stocks with SI > 20% of float OR days-to-cover > 5
3. Monitor for catalytic events (earnings, FDA decisions, binary events)
4. Detect early squeeze indicators: rapid price rise + high volume + increasing cost to borrow
5. Enter on momentum, exit when SI% drops or reverse split announced
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Sequence

from trading_champs.signals.backtester import Backtester, BacktestResult, SignalType


class SqueezePhase(Enum):
    """Short squeeze phase detection."""

    ACCUMULATION = "accumulation"  # Short interest building
    BUILDUP = "buildup"  # Price starting to rise, short interest high
    SQUEEZE = "squeeze"  # Rapid price rise, short covering
    PEAK = "peak"  # Maximum squeeze, likely reversal soon
    COOLDOWN = "cooldown"  # Short interest dropping, squeeze ending


class CatalyticEvent(Enum):
    """Catalytic events that trigger short squeezes."""

    EARNINGS = "earnings"
    FDA_DECISION = "fda_decision"
    BINARY_EVENT = "binary_event"
    INDEX_REBALANCE = "index_rebalance"
    SHORT_EXCLUSION = "short_exclusion"
    MAJOR_NEWS = "major_news"
    BUYBACK_ANNOUNCEMENT = "buyback_announcement"


@dataclass(frozen=True)
class ShortInterestData:
    """Short interest metrics for a stock."""

    symbol: str
    short_interest_percent: float  # % of float sold short
    days_to_cover: float  # Days to cover at current volume
    short_volume: int  # Number of shares sold short
    total_volume: int  # Total trading volume
    cost_to_borrow: float  # Current fee to borrow shares (%)
    available_shares: int  # Available shares to borrow
    date: datetime
    source: str  # e.g., "finra", "ortex", "s3_partners"


@dataclass(frozen=True)
class PriceMomentum:
    """Price and volume momentum indicators."""

    symbol: str
    price_change_1d: float  # % change over 1 day
    price_change_5d: float  # % change over 5 days
    volume_ratio: float  # Current volume / average volume
    price_velocity: float  # Rate of price change
    borrowed_shares_trend: str  # "increasing", "stable", "decreasing"
    timestamp: datetime


@dataclass
class SqueezeSignal:
    """Combined short squeeze signal."""

    symbol: str
    phase: SqueezePhase
    short_interest: ShortInterestData
    momentum: PriceMomentum
    catalytic_event: Optional[CatalyticEvent]
    squeeze_probability: float  # 0 to 1
    urgency: str  # "low", "medium", "high", "critical"
    confidence: float  # 0 to 1
    entry_price_target: float
    stop_loss: float
    rationale: str
    timestamp: datetime


@dataclass
class ShortSqueezeConfig:
    """Configuration for short squeeze strategy."""

    # Short interest thresholds
    min_short_interest_percent: float = 20.0  # SI > 20% of float
    high_short_interest_percent: float = 30.0  # Very high SI

    # Days to cover thresholds
    min_days_to_cover: float = 5.0  # DTC > 5
    high_days_to_cover: float = 10.0  # Very high DTC

    # Cost to borrow thresholds
    min_cost_to_borrow: float = 1.0  # % fee to borrow
    high_cost_to_borrow: float = 5.0  # Very expensive to borrow

    # Price momentum thresholds
    min_price_velocity: float = 2.0  # % per day
    squeeze_price_velocity: float = 5.0  # % per day (strong squeeze)
    min_volume_ratio: float = 2.0  # Volume vs average

    # Squeeze probability thresholds
    low_squeeze_probability: float = 0.3
    medium_squeeze_probability: float = 0.5
    high_squeeze_probability: float = 0.7

    # Risk management
    max_position_size: float = 0.1  # 10% of portfolio
    stop_loss_percent: float = 0.05  # 5% stop loss
    profit_target_percent: float = 0.20  # 20% profit target

    # Catalytic event settings
    track_earnings: bool = True
    track_fda_events: bool = True
    track_binary_events: bool = True

    # Lookback settings
    momentum_lookback_days: int = 5
    short_interest_lookback_days: int = 14

    # Symbols to track (high short interest candidates)
    symbols: tuple[str, ...] = (
        "GME",
        "AMC",
        "BBBY",
        "BB",
        "NOK",
        "KOSS",
        "EXPR",
        "SOS",
        "NAKD",
        "SNAP",
        "TWTR",
    )


class ShortInterestFetcher:
    """Fetches short interest data from various providers.

    In production, connects to FINRA, Ortex, S3 Partners APIs.
    For now, generates realistic mock data.
    """

    # Symbol profiles for short interest characteristics
    SYMBOL_PROFILES: dict[str, dict] = {
        "GME": {
            "base_si_percent": 25.0,
            "base_dtc": 8.0,
            "base_ctb": 2.5,
            "volatility": 15.0,
            "catalyst_type": "earnings",
        },
        "AMC": {
            "base_si_percent": 20.0,
            "base_dtc": 6.0,
            "base_ctb": 1.5,
            "volatility": 12.0,
            "catalyst_type": "earnings",
        },
        "BBBY": {
            "base_si_percent": 35.0,
            "base_dtc": 12.0,
            "base_ctb": 5.0,
            "volatility": 20.0,
            "catalyst_type": "binary_event",
        },
        "BB": {
            "base_si_percent": 15.0,
            "base_dtc": 4.0,
            "base_ctb": 1.0,
            "volatility": 8.0,
            "catalyst_type": "major_news",
        },
        "NOK": {
            "base_si_percent": 12.0,
            "base_dtc": 3.5,
            "base_ctb": 0.8,
            "volatility": 7.0,
            "catalyst_type": "earnings",
        },
        "KOSS": {
            "base_si_percent": 40.0,
            "base_dtc": 15.0,
            "base_ctb": 8.0,
            "volatility": 25.0,
            "catalyst_type": "major_news",
        },
        "EXPR": {
            "base_si_percent": 30.0,
            "base_dtc": 10.0,
            "base_ctb": 4.0,
            "volatility": 18.0,
            "catalyst_type": "binary_event",
        },
        "SNAP": {
            "base_si_percent": 10.0,
            "base_dtc": 3.0,
            "base_ctb": 0.5,
            "volatility": 6.0,
            "catalyst_type": "earnings",
        },
    }

    # Data sources
    SOURCES: tuple[str, ...] = ("finra", "ortex", "s3_partners", "fintel")

    def __init__(self, api_keys: Optional[dict] = None):
        """Initialize fetcher.

        Args:
            api_keys: Optional API keys for data providers.
        """
        self._keys = api_keys or {}

    def fetch_short_interest(
        self,
        symbol: str,
        date: Optional[datetime] = None,
    ) -> ShortInterestData:
        """Fetch short interest data for a symbol.

        Args:
            symbol: Trading symbol.
            date: Optional specific date (defaults to most recent).

        Returns:
            ShortInterestData with current metrics.
        """
        return self._generate_mock_si_data(symbol)

    def fetch_historical_short_interest(
        self,
        symbol: str,
        days: int = 30,
    ) -> list[ShortInterestData]:
        """Fetch historical short interest data.

        Args:
            symbol: Trading symbol.
            days: Number of days of history.

        Returns:
            List of historical ShortInterestData.
        """
        data: list[ShortInterestData] = []
        now = datetime.now()

        for i in range(min(days, 30)):
            date = now - timedelta(days=i)
            mock_date = date.replace(hour=16, minute=0, second=0, microsecond=0)
            data.append(self._generate_mock_si_data(symbol, mock_date))

        return list(reversed(data))

    def _generate_mock_si_data(
        self,
        symbol: str,
        date: Optional[datetime] = None,
    ) -> ShortInterestData:
        """Generate realistic mock short interest data.

        Args:
            symbol: Trading symbol.
            date: Optional date for the data.

        Returns:
            Mock ShortInterestData.
        """
        profile = self.SYMBOL_PROFILES.get(
            symbol,
            {
                "base_si_percent": 10.0,
                "base_dtc": 3.0,
                "base_ctb": 0.5,
                "volatility": 5.0,
            },
        )

        # Add some randomness to the data
        si_percent = random.gauss(profile["base_si_percent"], profile["volatility"] / 3)
        si_percent = max(1.0, min(60.0, si_percent))

        dtc = random.gauss(profile["base_dtc"], profile["base_dtc"] / 3)
        dtc = max(0.5, min(25.0, dtc))

        ctb = random.gauss(profile["base_ctb"], profile["base_ctb"] / 2)
        ctb = max(0.1, min(15.0, ctb))

        # Calculate volume metrics
        avg_volume = random.randint(5_000_000, 50_000_000)
        short_volume = int(avg_volume * si_percent / 100)
        total_volume = avg_volume + random.randint(-avg_volume // 4, avg_volume // 2)

        # Available shares to borrow
        available = (
            random.randint(100_000, 5_000_000)
            if si_percent > 15
            else random.randint(1_000_000, 20_000_000)
        )

        return ShortInterestData(
            symbol=symbol,
            short_interest_percent=round(si_percent, 2),
            days_to_cover=round(dtc, 1),
            short_volume=short_volume,
            total_volume=total_volume,
            cost_to_borrow=round(ctb, 2),
            available_shares=available,
            date=date or datetime.now(),
            source=random.choice(self.SOURCES),
        )


class MomentumFetcher:
    """Fetches price momentum and volume data."""

    # Typical volume ratios for high SI stocks
    VOLUME_PROFILES: dict[str, float] = {
        "GME": 3.5,
        "AMC": 2.8,
        "BBBY": 5.0,
        "BB": 1.5,
        "NOK": 1.3,
        "KOSS": 4.0,
        "EXPR": 3.0,
        "SNAP": 1.2,
    }

    def __init__(self, api_keys: Optional[dict] = None):
        """Initialize fetcher.

        Args:
            api_keys: Optional API keys for data providers.
        """
        self._keys = api_keys or {}

    def fetch_momentum(
        self,
        symbol: str,
        days: int = 5,
    ) -> PriceMomentum:
        """Fetch price momentum data for a symbol.

        Args:
            symbol: Trading symbol.
            days: Number of days for momentum calculation.

        Returns:
            PriceMomentum with current metrics.
        """
        return self._generate_mock_momentum(symbol, days)

    def _generate_mock_momentum(
        self,
        symbol: str,
        days: int,
    ) -> PriceMomentum:
        """Generate realistic mock momentum data.

        Args:
            symbol: Trading symbol.
            days: Lookback period.

        Returns:
            Mock PriceMomentum.
        """
        profile = self.VOLUME_PROFILES.get(symbol, 1.5)

        # Generate price changes with some squeeze characteristics
        base_change_1d = random.gauss(2.0, 5.0)
        change_1d = max(-15.0, min(30.0, base_change_1d))

        # 5-day change correlates somewhat with 1-day
        change_5d = random.gauss(change_1d * 2.5, 10.0)
        change_5d = max(-30.0, min(60.0, change_5d))

        # Volume ratio
        volume_ratio = random.gauss(profile, profile / 3)
        volume_ratio = max(0.5, min(8.0, volume_ratio))

        # Price velocity (rate of change)
        price_velocity = change_1d / 1.0  # % per day

        # Borrowed shares trend
        if change_1d > 5:
            borrowed_trend = "increasing"
        elif change_1d < -3:
            borrowed_trend = "decreasing"
        else:
            borrowed_trend = random.choice(["increasing", "stable", "decreasing"])

        return PriceMomentum(
            symbol=symbol,
            price_change_1d=round(change_1d, 2),
            price_change_5d=round(change_5d, 2),
            volume_ratio=round(volume_ratio, 2),
            price_velocity=round(price_velocity, 2),
            borrowed_shares_trend=borrowed_trend,
            timestamp=datetime.now(),
        )


class SqueezeDetector:
    """Detects short squeeze conditions and phases."""

    def __init__(self, config: Optional[ShortSqueezeConfig] = None):
        """Initialize detector.

        Args:
            config: Squeeze detection configuration.
        """
        self._config = config or ShortSqueezeConfig()

    def detect_phase(
        self,
        short_interest: ShortInterestData,
        momentum: PriceMomentum,
        historical_si: Optional[list[ShortInterestData]] = None,
    ) -> SqueezePhase:
        """Detect current squeeze phase.

        Args:
            short_interest: Current short interest data.
            momentum: Current price momentum.
            historical_si: Optional historical SI data for trend detection.

        Returns:
            SqueezePhase enum value.
        """
        si = short_interest.short_interest_percent
        velocity = momentum.price_velocity
        vol_ratio = momentum.volume_ratio

        # High SI + low price movement = accumulation
        if (
            si > self._config.min_short_interest_percent
            and velocity < self._config.min_price_velocity
        ):
            return SqueezePhase.ACCUMULATION

        # Rising price + high SI = buildup
        if (
            si > self._config.min_short_interest_percent
            and velocity >= self._config.min_price_velocity
        ):
            if vol_ratio >= self._config.min_volume_ratio:
                return SqueezePhase.SQUEEZE
            return SqueezePhase.BUILDUP

        # Very high velocity + high volume = squeeze
        if (
            velocity >= self._config.squeeze_price_velocity
            and vol_ratio >= self._config.min_volume_ratio
        ):
            return SqueezePhase.SQUEEZE

        # Check for cooldown phase
        if historical_si and len(historical_si) >= 2:
            latest_si = historical_si[-1].short_interest_percent
            previous_si = historical_si[-2].short_interest_percent
            if latest_si < previous_si * 0.9:  # SI dropped by 10%+
                return SqueezePhase.COOLDOWN

        # Check for peak
        if (
            si > self._config.high_short_interest_percent
            and velocity > self._config.squeeze_price_velocity
        ):
            return SqueezePhase.PEAK

        return SqueezePhase.ACCUMULATION

    def calculate_squeeze_probability(
        self,
        short_interest: ShortInterestData,
        momentum: PriceMomentum,
        phase: SqueezePhase,
    ) -> float:
        """Calculate probability of short squeeze occurring.

        Args:
            short_interest: Short interest data.
            momentum: Price momentum data.
            phase: Current squeeze phase.

        Returns:
            Probability from 0 to 1.
        """
        # Start with base probability from phase
        phase_probabilities = {
            SqueezePhase.ACCUMULATION: 0.2,
            SqueezePhase.BUILDUP: 0.4,
            SqueezePhase.SQUEEZE: 0.75,
            SqueezePhase.PEAK: 0.5,
            SqueezePhase.COOLDOWN: 0.15,
        }
        prob = phase_probabilities.get(phase, 0.2)

        # Adjust for short interest level
        if short_interest.short_interest_percent >= self._config.high_short_interest_percent:
            prob += 0.2
        elif short_interest.short_interest_percent >= self._config.min_short_interest_percent:
            prob += 0.1

        # Adjust for days to cover
        if short_interest.days_to_cover >= self._config.high_days_to_cover:
            prob += 0.15
        elif short_interest.days_to_cover >= self._config.min_days_to_cover:
            prob += 0.08

        # Adjust for cost to borrow (high CTB = high conviction)
        if short_interest.cost_to_borrow >= self._config.high_cost_to_borrow:
            prob += 0.15
        elif short_interest.cost_to_borrow >= self._config.min_cost_to_borrow:
            prob += 0.05

        # Adjust for momentum
        if momentum.price_velocity >= self._config.squeeze_price_velocity:
            prob += 0.15
        elif momentum.price_velocity >= self._config.min_price_velocity:
            prob += 0.08

        # Adjust for volume
        if momentum.volume_ratio >= self._config.min_volume_ratio * 2:
            prob += 0.1
        elif momentum.volume_ratio >= self._config.min_volume_ratio:
            prob += 0.05

        return min(0.95, max(0.05, prob))

    def determine_urgency(
        self,
        phase: SqueezePhase,
        squeeze_prob: float,
        momentum: PriceMomentum,
    ) -> str:
        """Determine urgency level for trading.

        Args:
            phase: Current squeeze phase.
            squeeze_prob: Calculated squeeze probability.
            momentum: Price momentum data.

        Returns:
            Urgency string: "low", "medium", "high", "critical".
        """
        if phase == SqueezePhase.SQUEEZE and squeeze_prob >= self._config.high_squeeze_probability:
            return "critical"
        if phase == SqueezePhase.SQUEEZE or (
            phase == SqueezePhase.PEAK and squeeze_prob >= self._config.medium_squeeze_probability
        ):
            return "high"
        if (
            phase == SqueezePhase.BUILDUP
            and squeeze_prob >= self._config.medium_squeeze_probability
        ):
            return "medium"
        return "low"


class ShortSqueezeStrategy:
    """Short Squeeze Detection trading strategy.

    Identifies stocks with high short interest and triggers trades
    during short squeeze events.

    WARNING: This is a HIGH RISK strategy. Only trade with money you can afford to lose.
    Short squeezes are unpredictable and can reverse suddenly.
    """

    def __init__(
        self,
        config: Optional[ShortSqueezeConfig] = None,
        api_keys: Optional[dict] = None,
    ):
        """Initialize strategy.

        Args:
            config: Strategy configuration.
            api_keys: Optional API keys for data sources.
        """
        self._config = config or ShortSqueezeConfig()
        self._si_fetcher = ShortInterestFetcher(api_keys=api_keys)
        self._momentum_fetcher = MomentumFetcher(api_keys=api_keys)
        self._detector = SqueezeDetector(config=self._config)

    @property
    def config(self) -> ShortSqueezeConfig:
        """Get strategy configuration."""
        return self._config

    def fetch_and_analyze(self, symbol: str) -> SqueezeSignal:
        """Fetch data and analyze for short squeeze signals.

        Args:
            symbol: Trading symbol.

        Returns:
            SqueezeSignal with analysis and recommendations.
        """
        # Fetch current data
        short_interest = self._si_fetcher.fetch_short_interest(symbol)
        momentum = self._momentum_fetcher.fetch_momentum(
            symbol, days=self._config.momentum_lookback_days
        )
        historical_si = self._si_fetcher.fetch_historical_short_interest(
            symbol, days=self._config.short_interest_lookback_days
        )

        # Detect squeeze phase
        phase = self._detector.detect_phase(short_interest, momentum, historical_si)

        # Calculate probability
        squeeze_prob = self._detector.calculate_squeeze_probability(short_interest, momentum, phase)

        # Determine urgency
        urgency = self._detector.determine_urgency(phase, squeeze_prob, momentum)

        # Calculate entry and stop loss targets (mock prices)
        current_price = 100.0  # Would come from price data in production
        entry_target = current_price * (1 + momentum.price_change_1d / 100)
        stop_loss = current_price * (1 - self._config.stop_loss_percent)

        # Generate rationale
        rationale = self._generate_rationale(symbol, short_interest, momentum, phase, squeeze_prob)

        return SqueezeSignal(
            symbol=symbol,
            phase=phase,
            short_interest=short_interest,
            momentum=momentum,
            catalytic_event=None,  # Would be determined from event calendar in production
            squeeze_probability=squeeze_prob,
            urgency=urgency,
            confidence=min(0.9, squeeze_prob + 0.1),
            entry_price_target=round(entry_target, 2),
            stop_loss=round(stop_loss, 2),
            rationale=rationale,
            timestamp=datetime.now(),
        )

    def _generate_rationale(
        self,
        symbol: str,
        short_interest: ShortInterestData,
        momentum: PriceMomentum,
        phase: SqueezePhase,
        squeeze_prob: float,
    ) -> str:
        """Generate human-readable rationale for the signal.

        Args:
            symbol: Trading symbol.
            short_interest: Short interest data.
            momentum: Price momentum data.
            phase: Detected squeeze phase.
            squeeze_prob: Calculated squeeze probability.

        Returns:
            Rationale string.
        """
        parts = [
            f"{symbol} in {phase.value.upper()} phase",
            f"SI: {short_interest.short_interest_percent:.1f}%",
            f"DTC: {short_interest.days_to_cover:.1f} days",
            f"CTB: {short_interest.cost_to_borrow:.1f}%",
            f"Momentum: {momentum.price_change_1d:.1f}% 1D",
            f"Volume ratio: {momentum.volume_ratio:.1f}x",
            f"Squeeze probability: {squeeze_prob:.0%}",
        ]
        return " | ".join(parts)

    def should_trade(self, signal: SqueezeSignal) -> tuple[bool, str]:
        """Determine if we should trade this signal.

        Args:
            signal: SqueezeSignal to evaluate.

        Returns:
            Tuple of (should_trade, reason).
        """
        # Check squeeze probability threshold
        if signal.squeeze_probability < self._config.low_squeeze_probability:
            return False, f"Low squeeze probability: {signal.squeeze_probability:.0%}"

        # Only trade in certain phases
        tradeable_phases = [SqueezePhase.BUILDUP, SqueezePhase.SQUEEZE]
        if signal.phase not in tradeable_phases:
            return False, f"Phase {signal.phase.value} not tradeable"

        # Check urgency
        if signal.urgency == "low":
            return False, f"Low urgency: {signal.urgency}"

        # All checks passed
        return (
            True,
            f"Trade signal: {signal.urgency.upper()} {signal.phase.value} for {signal.symbol}",
        )

    def generate_signal(
        self,
        symbol: str,
    ) -> tuple[SqueezeSignal, bool, str]:
        """Generate a trading signal for a symbol.

        Args:
            symbol: Trading symbol.

        Returns:
            Tuple of (SqueezeSignal, should_trade, reason).
        """
        signal = self.fetch_and_analyze(symbol)
        should_trade, reason = self.should_trade(signal)
        return signal, should_trade, reason

    def get_signals_for_symbols(
        self,
        symbols: Optional[list[str]] = None,
    ) -> dict[str, tuple[SqueezeSignal, bool, str]]:
        """Get trading signals for multiple symbols.

        Args:
            symbols: List of symbols to analyze. Uses config symbols if None.

        Returns:
            Dict mapping symbol -> (SqueezeSignal, should_trade, reason).
        """
        target_symbols = list(symbols) if symbols else list(self._config.symbols)
        results: dict[str, tuple[SqueezeSignal, bool, str]] = {}

        for symbol in target_symbols:
            results[symbol] = self.generate_signal(symbol)

        return results

    def backtest(
        self,
        symbol: str,
        prices: Sequence[float],
    ) -> BacktestResult:
        """Backtest strategy on historical data.

        Args:
            symbol: Symbol to backtest.
            prices: Historical price series.

        Returns:
            BacktestResult with performance metrics.
        """
        # Generate mock squeeze signals for historical data
        historical_signals = self._generate_historical_signals(symbol, len(prices))

        # Convert to SignalType
        signals: list[SignalType] = []
        for prob in historical_signals:
            if prob > self._config.high_squeeze_probability:
                signals.append(SignalType.BUY)
            elif prob < self._config.low_squeeze_probability:
                signals.append(SignalType.SELL)
            else:
                signals.append(SignalType.NEUTRAL)

        # Pad signals to match prices
        while len(signals) < len(prices):
            signals.append(SignalType.NEUTRAL)

        backtester = Backtester(prices, signals)
        return backtester.run()

    def _generate_historical_signals(
        self,
        symbol: str,
        length: int,
    ) -> list[float]:
        """Generate realistic mock historical squeeze probability data.

        Args:
            symbol: Trading symbol.
            length: Number of data points.

        Returns:
            List of squeeze probabilities.
        """
        rng = random.Random(hash(symbol + "squeeze") % 2**32)
        prob = 0.3
        probabilities: list[float] = []

        for _ in range(length):
            # Random walk with mean reversion toward 0.3
            change = rng.gauss(0.0, 0.15)
            reversion = -prob * 0.1
            prob = max(0.05, min(0.95, prob + change + reversion))
            probabilities.append(prob)

        return probabilities
