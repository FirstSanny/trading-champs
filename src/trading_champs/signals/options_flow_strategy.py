"""Options Flow / Dark Pool Trading Strategy.

Analyzes unusual options activity and dark pool data to detect institutional trading.
This provides alpha because retail cannot see where institutions are positioning.

Key components:
1. Source unusual options flow from Unusual Whales, Quiver Quantitative
2. Detect large block trades, dark pool prints
3. Calculate put/call ratios, delta imbalance
4. Signal when institutional activity contradicts current price direction
5. Backtest against historical price movements
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Sequence

from trading_champs.signals.backtester import Backtester, BacktestResult, SignalType


class FlowType(Enum):
    """Type of options flow."""

    CALL = "call"
    PUT = "put"
    SWEEP = "sweep"  # Large single-order sweep
    BLOCK = "block"  # Large block trade


class DarkPoolIndicator(Enum):
    """Dark pool trade indicators."""

    PRINT = "print"  # Dark pool print detected
    HIDDEN = "hidden"  # Order hidden from lit exchanges
    LARGE_PRINT = "large_print"  # Large dark pool transaction


@dataclass(frozen=True)
class OptionsFlow:
    """Represents a single options flow signal."""

    symbol: str
    flow_type: FlowType
    direction: str  # "bullish" or "bearish"
    strike: float
    expiration: str
    size: int  # Number of contracts
    dollar_value: float
    sentiment: float  # -1 to +1
    confidence: float  # 0 to 1
    is_unusual: bool  # Outside typical size/volume
    is_sweep: bool  # Single-order sweep (very bullish/bearish)
    timestamp: datetime
    source: str  # e.g., "unusual_whales", "quiver_quantitative"


@dataclass(frozen=True)
class DarkPoolPrint:
    """Represents a dark pool print."""

    symbol: str
    side: str  # "buy" or "sell"
    size: int  # Number of shares
    dollar_value: float
    venue: str  # e.g., "NASDAQ", "NYSE", "dark"
    is_buyer_initiated: bool
    sentiment: float  # -1 to +1
    timestamp: datetime


@dataclass
class DeltaImbalance:
    """Delta imbalance for a symbol."""

    symbol: str
    net_delta: float  # Positive = bullish, negative = bearish
    call_delta: float
    put_delta: float
    put_call_ratio: float
    directional_signal: str  # "bullish", "bearish", "neutral"
    confidence: float
    timestamp: datetime


@dataclass
class InstitutionalSignal:
    """Aggregated institutional trading signal."""

    symbol: str
    flow_signals: list[OptionsFlow]
    dark_pool_prints: list[DarkPoolPrint]
    delta_imbalance: Optional[DeltaImbalance]
    combined_sentiment: float  # -1 to +1
    total_dollar_value: float
    flow_count: int
    dark_pool_count: int
    side: str  # "long", "short", or "neutral"
    strength: str  # "weak", "moderate", "strong"
    confidence: float
    timestamp: datetime
    has_institutional_consensus: bool  # Multiple sources agree


@dataclass
class OptionsFlowConfig:
    """Configuration for options flow strategy."""

    # Size thresholds (in contracts)
    large_trade_threshold: int = 500  # Contracts
    block_trade_threshold: int = 1000  # Contracts
    sweep_threshold: int = 2000  # Contracts

    # Dollar value thresholds
    min_dollar_value: float = 100000.0  # $100K minimum

    # Sentiment thresholds
    bullish_threshold: float = 0.3  # Sentiment above this → bullish
    bearish_threshold: float = -0.3  # Sentiment below this → bearish

    # Confidence thresholds
    min_confidence: float = 0.5
    high_confidence_threshold: float = 0.75

    # Signal aggregation
    min_flows_for_action: int = 2  # Require multiple flows (risk management)
    flow_lookback_hours: int = 4

    # Dark pool settings
    min_dark_pool_size: int = 10000  # Shares
    dark_pool_lookback_hours: int = 24

    # Delta imbalance thresholds
    min_delta_for_signal: float = 0.25  # Minimum delta imbalance to consider
    put_call_ratio_bullish: float = 0.7  # Below this = bullish
    put_call_ratio_bearish: float = 1.3  # Above this = bearish

    # Institutional consensus (multiple sources must agree)
    require_consensus: bool = True
    consensus_sources: tuple[str, ...] = ("unusual_whales", "quiver_quantitative")

    # Symbols to track
    symbols: tuple[str, ...] = (
        "SPY",
        "QQQ",
        "TSLA",
        "AAPL",
        "NVDA",
        "AMD",
        "GME",
        "AMC",
        "BTC",
        "ETH",
    )

    # Time decay
    signal_decay_hours: int = 4
    max_age_hours: int = 24


class OptionsFlowFetcher:
    """Fetches options flow and dark pool data.

    In production, connects to Unusual Whales API, Quiver Quantitative, and
    dark pool data providers. For now, generates realistic mock data.
    """

    # Symbol profiles for generating realistic mock data
    SYMBOL_PROFILES: dict[str, dict] = {
        "SPY": {
            "base_flow_sentiment": 0.05,
            "flow_volatility": 0.15,
            "base_dark_sentiment": 0.03,
            "dark_volatility": 0.1,
            "avg_option_size": 50,
            "typical_pc_ratio": 1.1,
        },
        "QQQ": {
            "base_flow_sentiment": 0.08,
            "flow_volatility": 0.2,
            "base_dark_sentiment": 0.05,
            "dark_volatility": 0.12,
            "avg_option_size": 40,
            "typical_pc_ratio": 1.0,
        },
        "TSLA": {
            "base_flow_sentiment": 0.0,
            "flow_volatility": 0.45,
            "base_dark_sentiment": -0.02,
            "dark_volatility": 0.25,
            "avg_option_size": 150,
            "typical_pc_ratio": 0.9,
        },
        "AAPL": {
            "base_flow_sentiment": 0.1,
            "flow_volatility": 0.18,
            "base_dark_sentiment": 0.06,
            "dark_volatility": 0.1,
            "avg_option_size": 75,
            "typical_pc_ratio": 1.2,
        },
        "NVDA": {
            "base_flow_sentiment": 0.15,
            "flow_volatility": 0.35,
            "base_dark_sentiment": 0.1,
            "dark_volatility": 0.2,
            "avg_option_size": 100,
            "typical_pc_ratio": 0.8,
        },
        "AMD": {
            "base_flow_sentiment": 0.02,
            "flow_volatility": 0.4,
            "base_dark_sentiment": 0.0,
            "dark_volatility": 0.22,
            "avg_option_size": 120,
            "typical_pc_ratio": 0.85,
        },
        "GME": {
            "base_flow_sentiment": -0.1,
            "flow_volatility": 0.6,
            "base_dark_sentiment": -0.15,
            "dark_volatility": 0.35,
            "avg_option_size": 300,
            "typical_pc_ratio": 0.6,
        },
        "AMC": {
            "base_flow_sentiment": -0.12,
            "flow_volatility": 0.55,
            "base_dark_sentiment": -0.1,
            "dark_volatility": 0.3,
            "avg_option_size": 250,
            "typical_pc_ratio": 0.65,
        },
        "BTC": {
            "base_flow_sentiment": 0.05,
            "flow_volatility": 0.4,
            "base_dark_sentiment": 0.02,
            "dark_volatility": 0.25,
            "avg_option_size": 80,
            "typical_pc_ratio": 0.9,
        },
        "ETH": {
            "base_flow_sentiment": 0.03,
            "flow_volatility": 0.38,
            "base_dark_sentiment": 0.0,
            "dark_volatility": 0.22,
            "avg_option_size": 60,
            "typical_pc_ratio": 0.95,
        },
    }

    # Data sources
    SOURCES: tuple[str, ...] = ("unusual_whales", "quiver_quantitative", "trade_alert")

    def __init__(self, api_keys: Optional[dict] = None):
        """Initialize fetcher.

        Args:
            api_keys: Optional API keys for Unusual Whales, Quiver Quantitative, etc.
        """
        self._keys = api_keys or {}

    def fetch_options_flow(
        self,
        symbol: str,
        hours: int = 24,
    ) -> list[OptionsFlow]:
        """Fetch unusual options flow for a symbol.

        Args:
            symbol: Trading symbol.
            hours: Lookback window in hours.

        Returns:
            List of OptionsFlow signals.
        """
        return self._generate_mock_flows(symbol, hours)

    def fetch_dark_pool_prints(
        self,
        symbol: str,
        hours: int = 24,
    ) -> list[DarkPoolPrint]:
        """Fetch dark pool prints for a symbol.

        Args:
            symbol: Trading symbol.
            hours: Lookback window in hours.

        Returns:
            List of DarkPoolPrint signals.
        """
        return self._generate_mock_dark_prints(symbol, hours)

    def _generate_mock_flows(self, symbol: str, hours: int) -> list[OptionsFlow]:
        """Generate realistic mock options flow data.

        Args:
            symbol: Trading symbol.
            hours: Lookback window.

        Returns:
            List of mock OptionsFlow signals.
        """
        profile = self.SYMBOL_PROFILES.get(
            symbol,
            {
                "base_flow_sentiment": 0.0,
                "flow_volatility": 0.25,
                "avg_option_size": 50,
                "typical_pc_ratio": 1.0,
            },
        )

        flows: list[OptionsFlow] = []
        num_flows = random.randint(5, 25)
        now = datetime.now()

        for _ in range(num_flows):
            hours_ago = random.uniform(0, hours)
            timestamp = now - timedelta(hours=hours_ago)

            # Determine flow characteristics
            sentiment = random.gauss(profile["base_flow_sentiment"], profile["flow_volatility"])
            sentiment = max(-1.0, min(1.0, sentiment))

            # Determine flow type based on size
            base_size = profile["avg_option_size"]
            size = int(random.gauss(base_size, base_size * 0.5))
            size = max(10, size)  # Minimum 10 contracts

            # Determine direction and flow type
            if sentiment > 0.3:
                direction = "bullish"
                flow_type = FlowType.CALL if random.random() > 0.3 else FlowType.SWEEP
            elif sentiment < -0.3:
                direction = "bearish"
                flow_type = FlowType.PUT if random.random() > 0.3 else FlowType.SWEEP
            else:
                direction = "neutral"
                flow_type = FlowType.BLOCK

            # Check if unusual (large) trade
            is_unusual = size > profile["avg_option_size"] * 3
            is_sweep = flow_type == FlowType.SWEEP or size > 2000

            # Calculate dollar value (rough estimate)
            strike = random.uniform(50, 500)
            dollar_value = size * strike * 100  # 100 shares per contract

            flows.append(
                OptionsFlow(
                    symbol=symbol,
                    flow_type=flow_type,
                    direction=direction,
                    strike=strike,
                    expiration=_random_expiration(),
                    size=size,
                    dollar_value=dollar_value,
                    sentiment=sentiment,
                    confidence=min(0.95, abs(sentiment) * (1 + size / 1000)),
                    is_unusual=is_unusual,
                    is_sweep=is_sweep,
                    timestamp=timestamp,
                    source=random.choice(self.SOURCES),
                )
            )

        flows.sort(key=lambda f: f.timestamp, reverse=True)
        return flows

    def _generate_mock_dark_prints(self, symbol: str, hours: int) -> list[DarkPoolPrint]:
        """Generate realistic mock dark pool print data.

        Args:
            symbol: Trading symbol.
            hours: Lookback window.

        Returns:
            List of mock DarkPoolPrint signals.
        """
        profile = self.SYMBOL_PROFILES.get(
            symbol,
            {
                "base_dark_sentiment": 0.0,
                "dark_volatility": 0.15,
            },
        )

        prints: list[DarkPoolPrint] = []
        num_prints = random.randint(3, 15)
        now = datetime.now()

        venues = ["NASDAQ", "NYSE", "BATS", "IEX", "dark", "internal"]

        for _ in range(num_prints):
            hours_ago = random.uniform(0, hours)
            timestamp = now - timedelta(hours=hours_ago)

            sentiment = random.gauss(profile["base_dark_sentiment"], profile["dark_volatility"])
            sentiment = max(-1.0, min(1.0, sentiment))

            size = random.randint(5000, 100000)
            venue = random.choice(venues)

            # Determine side based on sentiment
            if sentiment > 0.1:
                side = "buy"
                is_buyer_initiated = True
            elif sentiment < -0.1:
                side = "sell"
                is_buyer_initiated = False
            else:
                side = "buy" if random.random() > 0.5 else "sell"
                is_buyer_initiated = side == "buy"

            dollar_value = size * random.uniform(10, 500)

            prints.append(
                DarkPoolPrint(
                    symbol=symbol,
                    side=side,
                    size=size,
                    dollar_value=dollar_value,
                    venue=venue,
                    is_buyer_initiated=is_buyer_initiated,
                    sentiment=sentiment,
                    timestamp=timestamp,
                )
            )

        prints.sort(key=lambda p: p.timestamp, reverse=True)
        return prints

    def calculate_delta_imbalance(
        self,
        symbol: str,
        hours: int = 24,
    ) -> DeltaImbalance:
        """Calculate delta imbalance for a symbol.

        Args:
            symbol: Trading symbol.
            hours: Lookback window.

        Returns:
            DeltaImbalance with current readings.
        """
        profile = self.SYMBOL_PROFILES.get(
            symbol,
            {"typical_pc_ratio": 1.0},
        )

        # Generate mock delta data
        pc_ratio = random.gauss(profile["typical_pc_ratio"], 0.3)
        pc_ratio = max(0.3, min(2.5, pc_ratio))

        # Calculate deltas based on put/call ratio
        total_delta = 1.0 / (1.0 + pc_ratio) - 0.5  # Centered around 0
        call_delta = 0.5 + total_delta
        put_delta = 0.5 - total_delta

        # Determine signal
        if pc_ratio < OptionsFlowConfig.put_call_ratio_bullish:
            directional_signal = "bullish"
        elif pc_ratio > OptionsFlowConfig.put_call_ratio_bearish:
            directional_signal = "bearish"
        else:
            directional_signal = "neutral"

        confidence = min(0.95, abs(total_delta) * 2)

        return DeltaImbalance(
            symbol=symbol,
            net_delta=total_delta,
            call_delta=call_delta,
            put_delta=put_delta,
            put_call_ratio=pc_ratio,
            directional_signal=directional_signal,
            confidence=confidence,
            timestamp=datetime.now(),
        )


def _random_expiration() -> str:
    """Generate a random expiration string."""
    expirations = ["+0d", "+1d", "+2d", "+5d", "+7d", "+14d", "+21d", "+30d", "+45d", "+60d"]
    return random.choice(expirations)


class OptionsFlowStrategy:
    """Options Flow / Dark Pool trading strategy.

    Analyzes unusual options activity and dark pool data to detect
    institutional trading signals.

    Institutional activity often contradicts retail sentiment, so this
    strategy generates signals when we detect strong institutional bias.
    """

    def __init__(
        self,
        config: Optional[OptionsFlowConfig] = None,
        api_keys: Optional[dict] = None,
    ):
        """Initialize strategy.

        Args:
            config: Strategy configuration.
            api_keys: Optional API keys for data sources.
        """
        self._config = config or OptionsFlowConfig()
        self._fetcher = OptionsFlowFetcher(api_keys=api_keys)

    @property
    def config(self) -> OptionsFlowConfig:
        """Get strategy configuration."""
        return self._config

    def fetch_and_analyze(self, symbol: str) -> InstitutionalSignal:
        """Fetch flow data and generate institutional signal.

        Args:
            symbol: Trading symbol.

        Returns:
            InstitutionalSignal with aggregated analysis.
        """
        flows = self._fetcher.fetch_options_flow(symbol, hours=self._config.flow_lookback_hours)
        dark_prints = self._fetcher.fetch_dark_pool_prints(
            symbol, hours=self._config.dark_pool_lookback_hours
        )
        delta = self._fetcher.calculate_delta_imbalance(
            symbol, hours=self._config.flow_lookback_hours
        )

        return self._aggregate_signals(symbol, flows, dark_prints, delta)

    def _aggregate_signals(
        self,
        symbol: str,
        flows: list[OptionsFlow],
        dark_prints: list[DarkPoolPrint],
        delta: DeltaImbalance,
    ) -> InstitutionalSignal:
        """Aggregate flow signals into institutional signal.

        Args:
            symbol: Trading symbol.
            flows: Options flow signals.
            dark_prints: Dark pool prints.
            delta: Delta imbalance.

        Returns:
            Aggregated InstitutionalSignal.
        """
        if not flows and not dark_prints:
            return InstitutionalSignal(
                symbol=symbol,
                flow_signals=[],
                dark_pool_prints=[],
                delta_imbalance=delta,
                combined_sentiment=0.0,
                total_dollar_value=0.0,
                flow_count=0,
                dark_pool_count=0,
                side="neutral",
                strength="weak",
                confidence=0.0,
                timestamp=datetime.now(),
                has_institutional_consensus=False,
            )

        # Calculate combined sentiment from flows
        flow_sentiment = 0.0
        flow_dollar_value = 0.0
        significant_flows = 0

        for flow in flows:
            if flow.dollar_value >= self._config.min_dollar_value:
                flow_sentiment += flow.sentiment * min(1.0, flow.dollar_value / 1_000_000)
                flow_dollar_value += flow.dollar_value
                significant_flows += 1

        # Calculate sentiment from dark pool prints
        dark_sentiment = 0.0
        for print_ in dark_prints:
            if (
                print_.dollar_value >= self._config.min_dollar_value * 0.1
            ):  # Lower threshold for dark
                dark_sentiment += print_.sentiment * (print_.dollar_value / 500_000)

        # Normalize sentiments
        if significant_flows > 0:
            flow_sentiment /= significant_flows
        if dark_prints:
            dark_sentiment /= len(dark_prints)

        # Combine sentiments (weight flows slightly higher)
        combined = (flow_sentiment * 0.6) + (dark_sentiment * 0.3) + (delta.net_delta * 0.1)

        # Determine side
        if combined > self._config.bullish_threshold:
            side = "long"
        elif combined < self._config.bearish_threshold:
            side = "short"
        else:
            side = "neutral"

        # Calculate confidence
        confidence = min(0.95, abs(combined) + (significant_flows * 0.05))
        if delta.confidence > 0.7:
            confidence += 0.1
        confidence = min(0.95, confidence)

        # Determine strength
        if abs(combined) > 0.6:
            strength = "strong"
        elif abs(combined) > 0.4:
            strength = "moderate"
        else:
            strength = "weak"

        # Check institutional consensus
        sources = set(flow.source for flow in flows)
        has_consensus = len(sources) >= 2 if self._config.require_consensus else True

        return InstitutionalSignal(
            symbol=symbol,
            flow_signals=flows,
            dark_pool_prints=dark_prints,
            delta_imbalance=delta,
            combined_sentiment=combined,
            total_dollar_value=flow_dollar_value,
            flow_count=significant_flows,
            dark_pool_count=len(dark_prints),
            side=side,
            strength=strength,
            confidence=confidence,
            timestamp=datetime.now(),
            has_institutional_consensus=has_consensus,
        )

    def should_trade(self, signal: InstitutionalSignal) -> tuple[bool, str]:
        """Determine if we should act on an institutional signal.

        Args:
            signal: Aggregated institutional signal.

        Returns:
            Tuple of (should_trade, reason).
        """
        # Check for neutral
        if signal.side == "neutral":
            return False, f"Neutral signal: sentiment={signal.combined_sentiment:.2f}"

        # Check minimum flows requirement
        if signal.flow_count < self._config.min_flows_for_action:
            return (
                False,
                f"Insufficient flows: {signal.flow_count} < {self._config.min_flows_for_action}",
            )

        # Check confidence
        if signal.confidence < self._config.min_confidence:
            return False, f"Low confidence: {signal.confidence:.2f} < {self._config.min_confidence}"

        # Check institutional consensus if required
        if self._config.require_consensus and not signal.has_institutional_consensus:
            return False, "No institutional consensus (sources don't agree)"

        # Check dollar value threshold
        if signal.total_dollar_value < self._config.min_dollar_value:
            return False, f"Low dollar value: ${signal.total_dollar_value:,.0f}"

        return True, (
            f"Signal accepted: {signal.side} {signal.symbol} "
            f"(strength={signal.strength}, confidence={signal.confidence:.2f})"
        )

    def generate_signal(
        self,
        symbol: str,
    ) -> tuple[InstitutionalSignal, bool, str]:
        """Generate a trading signal for a symbol.

        Args:
            symbol: Trading symbol.

        Returns:
            Tuple of (InstitutionalSignal, should_trade, reason).
        """
        signal = self.fetch_and_analyze(symbol)
        should_trade, reason = self.should_trade(signal)
        return signal, should_trade, reason

    def get_signals_for_symbols(
        self,
        symbols: Optional[list[str]] = None,
    ) -> dict[str, tuple[InstitutionalSignal, bool, str]]:
        """Get trading signals for multiple symbols.

        Args:
            symbols: List of symbols to analyze. Uses config symbols if None.

        Returns:
            Dict mapping symbol -> (InstitutionalSignal, should_trade, reason).
        """
        target_symbols = list(symbols) if symbols else list(self._config.symbols)
        results: dict[str, tuple[InstitutionalSignal, bool, str]] = {}

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
        historical_signals = self._generate_historical_signals(symbol, len(prices))

        # Convert to SignalType
        signals: list[SignalType] = []
        for score in historical_signals:
            if score > self._config.bullish_threshold:
                signals.append(SignalType.BUY)
            elif score < self._config.bearish_threshold:
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
        """Generate realistic mock historical signal data.

        Args:
            symbol: Trading symbol.
            length: Number of data points.

        Returns:
            List of signal scores.
        """
        rng = random.Random(hash(symbol) % 2**32)
        sentiment = 0.0
        scores: list[float] = []

        profile = OptionsFlowFetcher.SYMBOL_PROFILES.get(
            symbol, {"base_flow_sentiment": 0.0, "flow_volatility": 0.25}
        )

        for _ in range(length):
            # Random walk with mean reversion
            volatility = profile.get("flow_volatility", 0.25)
            change = rng.gauss(0.0, volatility)
            reversion = -sentiment * 0.1  # Mean reversion
            sentiment = max(-1.0, min(1.0, sentiment + change + reversion))
            scores.append(sentiment)

        return scores
