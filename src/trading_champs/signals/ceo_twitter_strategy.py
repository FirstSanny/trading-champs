"""CEO/Executive Twitter trading strategy.

Monitors CEO and executive Twitter/X accounts for trading signals.
Famous examples: Elon Musk tweets affecting Tesla/crypto, Mark Zuckerberg affecting Meta.

Key components:
1. Track predefined list of executive accounts
2. Detect signal keywords: buy, sell, hold, bull, bear, moon, dump, etc.
3. Sentiment analysis on tweet context
4. Time decay for signal potency
5. Require confirmation from multiple signals before trading (HIGH RISK)

NOTE: This is HIGH RISK - require confirmation from multiple signals before trading.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Sequence

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except ImportError:
    SentimentIntensityAnalyzer = None  # type: ignore[assignment, misc]

from trading_champs.signals.backtester import Backtester, BacktestResult, PositionSide, SignalType


class ExecutiveType(Enum):
    """Type of executive."""

    CEO = "ceo"
    CFO = "cfo"
    FOUNDER = "founder"
    BOARD_MEMBER = "board_member"
    ANALYST = "analyst"
    EXECUTIVE = "executive"


@dataclass(frozen=True)
class ExecutiveAccount:
    """A tracked executive Twitter account."""

    handle: str
    name: str
    company: str
    executive_type: ExecutiveType
    symbols: tuple[str, ...]  # Symbols this executive can influence


# Predefined list of influential executives
# In production, this would be fetched from a database or config
EXECUTIVE_ACCOUNTS: dict[str, ExecutiveAccount] = {
    "elonmusk": ExecutiveAccount(
        handle="elonmusk",
        name="Elon Musk",
        company="Tesla/SpaceX/X",
        executive_type=ExecutiveType.CEO,
        symbols=("TSLA", "BTC", "DOGE", "X"),
    ),
    "wartman": ExecutiveAccount(
        handle="wartman",
        name="Cathie Wood",
        company="ARK Invest",
        executive_type=ExecutiveType.CEO,
        symbols=("ARKK", "TSLA", "COIN", "SQ"),
    ),
    "pmarca": ExecutiveAccount(
        handle="pmarca",
        name="Marc Andreessen",
        company="Andreessen Horowitz",
        executive_type=ExecutiveType.FOUNDER,
        symbols=("FB", "SNAP", "TWTR", "COIN"),
    ),
    "saylor": ExecutiveAccount(
        handle="saylor",
        name="Michael Saylor",
        company="MicroStrategy",
        executive_type=ExecutiveType.EXECUTIVE,
        symbols=("MSTR", "BTC"),
    ),
    "cz_binance": ExecutiveAccount(
        handle="cz_binance",
        name="CZ Zhao",
        company="Binance",
        executive_type=ExecutiveType.CEO,
        symbols=("BNB", "BTC", "ETH"),
    ),
    "jack": ExecutiveAccount(
        handle="jack",
        name="Jack Dorsey",
        company="Block/Square",
        executive_type=ExecutiveType.CEO,
        symbols=("SQ", "BTC", "TWTR"),
    ),
    "satrn": ExecutiveAccount(
        handle="satrn",
        name="Cathie Wood",
        company="ARK Invest",
        executive_type=ExecutiveType.CEO,
        symbols=("ARKK", "TSLA", "COIN"),
    ),
    "tyler": ExecutiveAccount(
        handle="tyler",
        name="Tyler Winklevoss",
        company="Gemini",
        executive_type=ExecutiveType.CFO,
        symbols=("BTC", "ETH"),
    ),
}


# Trading signal keywords with their associated sentiment
class SignalKeyword(Enum):
    """Keywords that trigger trading signals."""

    # Bullish keywords
    BUY = "buy", "loaded up", "accumulating", "adding", "long"
    MOON = "moon", "to the moon", "🚀", "lamborghini"
    BULL = "bull", "bullish", "bull case", "buy the dip"
    HOLD = "hold", "holding", "hodl", "still holding"
    UP = "up", "higher", "rising", "surge", "squeeze"

    # Bearish keywords
    SELL = "sell", "sold", "exiting", "liquidated", "sold out"
    DUMP = "dump", "dumping", "crash", "plunge", "tanking"
    BEAR = "bear", "bearish", "bear case", "short"
    DOWN = "down", "lower", "drop", "falling", "crash"

    # Neutral/uncertain
    WATCH = "watch", "watching", "monitoring", "waiting"

    @property
    def keywords(self) -> tuple[str, ...]:
        return self.value

    @property
    def sentiment(self) -> float:
        return SIGNAL_SENTIMENTS.get(self.name, 0.0)


# Keyword sentiments for SignalKeyword
SIGNAL_SENTIMENTS: dict[str, float] = {
    "BUY": 1.0,
    "MOON": 0.9,
    "BULL": 0.7,
    "HOLD": 0.2,
    "UP": 0.5,
    "SELL": -1.0,
    "DUMP": -0.9,
    "BEAR": -0.7,
    "DOWN": -0.5,
    "WATCH": 0.0,
}


@dataclass
class TweetSignal:
    """A signal extracted from a single tweet."""

    executive_handle: str
    executive_name: str
    company: str
    symbol: str
    keyword: SignalKeyword
    raw_sentiment: float  # VADER sentiment -1 to +1
    confidence: float  # 0 to 1
    is_direct_mention: bool  # Tweet mentions the symbol directly
    timestamp: datetime
    text: str


@dataclass
class AggregatedSignal:
    """Multiple tweet signals aggregated into a trading signal."""

    symbol: str
    executive_signals: list[TweetSignal]
    aggregated_sentiment: float
    total_confidence: float
    signal_count: int
    most_recent_timestamp: datetime
    side: str  # "long", "short", or "neutral"
    strength: str  # "weak", "moderate", "strong"


@dataclass
class CEOTwitterConfig:
    """Configuration for CEO Twitter strategy."""

    # Signal thresholds
    min_signals_for_action: int = 2  # Require multiple signals (HIGH RISK)
    min_confidence: float = 0.6  # Minimum confidence to act
    sentiment_threshold: float = 0.3  # Sentiment above this → bullish direction

    # Time decay settings
    signal_decay_hours: int = 4  # Signals lose potency after this
    max_age_hours: int = 24  # Ignore signals older than this

    # Keyword weighting
    keyword_weights: dict[str, float] = field(
        default_factory=lambda: {
            "BUY": 1.5,
            "MOON": 1.3,
            "BULL": 1.2,
            "HOLD": 0.8,
            "UP": 1.0,
            "SELL": -1.5,
            "DUMP": -1.3,
            "BEAR": -1.2,
            "DOWN": -1.0,
            "WATCH": 0.0,
        }
    )

    # Sentiment weight for direct mentions (vs indirect)
    direct_mention_multiplier: float = 1.5

    # Executives to track (handle keys from EXECUTIVE_ACCOUNTS)
    tracked_handles: tuple[str, ...] = tuple(EXECUTIVE_ACCOUNTS.keys())

    # Symbols to track
    symbols: tuple[str, ...] = ("TSLA", "BTC", "ETH", "MSTR", "ARKK", "COIN", "SQ", "DOGE")


class CEOTwitterScorer:
    """NLP sentiment scoring for executive tweets using VADER."""

    def __init__(self) -> None:
        """Initialize VADER sentiment analyzer."""
        if SentimentIntensityAnalyzer is None:
            raise ImportError(
                "vaderSentiment is required. Install with: pip install vaderSentiment"
            )
        self._analyzer = SentimentIntensityAnalyzer()

    def score(self, text: str) -> float:
        """Score text sentiment.

        Args:
            text: Input text to analyze.

        Returns:
            Compound sentiment score from -1 to +1.
        """
        scores: dict[str, float] = self._analyzer.polarity_scores(text)
        return float(scores["compound"])


class CEOTwitterFetcher:
    """Fetches executive tweets for analysis.

    In production, this connects to Twitter/X API v2.
    For now, generates realistic mock data.
    """

    # Sentiment profiles per executive
    EXECUTIVE_PROFILES: dict[str, dict] = {
        "elonmusk": {
            "base_sentiment": 0.1,
            "volatility": 0.5,
            "style": "impulsive",
            "topics": ["Tesla", "SpaceX", "Twitter", "Mars", "AI"],
        },
        "wartman": {
            "base_sentiment": 0.2,
            "volatility": 0.3,
            "style": "analytical",
            "topics": ["innovation", "disruption", "ARKK", "growth stocks"],
        },
        "pmarca": {
            "base_sentiment": 0.15,
            "volatility": 0.25,
            "style": "intellectual",
            "topics": ["tech", "software", "startups", "bitcoin"],
        },
        "saylor": {
            "base_sentiment": 0.3,
            "volatility": 0.2,
            "style": "evangelical",
            "topics": ["bitcoin", "buying", "HODL", "inflation hedge"],
        },
        "cz_binance": {
            "base_sentiment": 0.1,
            "volatility": 0.35,
            "style": "confident",
            "topics": ["crypto", "BNB", "bullish", "adoption"],
        },
        "jack": {
            "base_sentiment": 0.05,
            "volatility": 0.3,
            "style": "philosophical",
            "topics": ["bitcoin", "decentralization", "open internet"],
        },
        "tyler": {
            "base_sentiment": 0.15,
            "volatility": 0.25,
            "style": "measured",
            "topics": ["bitcoin", "ethereal", "long-term"],
        },
    }

    def __init__(self, api_key: Optional[str] = None):
        """Initialize fetcher.

        Args:
            api_key: Optional Twitter/X API bearer token.
        """
        self._api_key = api_key

    def fetch_tweets(
        self,
        handle: str,
        hours: int = 24,
    ) -> list[dict]:
        """Fetch recent tweets from an executive account.

        Args:
            handle: Twitter handle (without @).
            hours: Lookback window in hours.

        Returns:
            List of tweet dicts with 'text', 'timestamp', 'likes', 'retweets'.
        """
        # In production: make real Twitter API calls
        # For now: generate realistic mock data
        return self._generate_mock_tweets(handle, hours)

    def _generate_mock_tweets(self, handle: str, hours: int) -> list[dict]:
        """Generate realistic mock tweets for an executive.

        Args:
            handle: Twitter handle.
            hours: Lookback window.

        Returns:
            List of mock tweet dicts.
        """
        profile = self.EXECUTIVE_PROFILES.get(
            handle,
            {"base_sentiment": 0.0, "volatility": 0.3, "style": "neutral", "topics": [handle]},
        )

        tweets: list[dict] = []
        num_tweets = random.randint(3, 15)
        now = datetime.now()

        for i in range(num_tweets):
            hours_ago = random.uniform(0, hours)
            timestamp = now - timedelta(hours=hours_ago)

            topic = random.choice(profile["topics"])
            sentiment = random.gauss(profile["base_sentiment"], profile["volatility"])
            sentiment = max(-1.0, min(1.0, sentiment))

            text = self._mock_tweet(handle, topic, sentiment)
            likes = random.randint(100, 50000)
            retweets = int(likes * random.uniform(0.1, 0.5))

            tweets.append(
                {
                    "text": text,
                    "timestamp": timestamp,
                    "likes": likes,
                    "retweets": retweets,
                    "handle": handle,
                }
            )

        tweets.sort(key=lambda t: t["timestamp"], reverse=True)
        return tweets

    def _mock_tweet(self, handle: str, topic: str, sentiment: float) -> str:
        """Generate mock tweet text."""
        if handle == "elonmusk":
            return self._mock_elon_tweet(topic, sentiment)
        elif handle == "saylor":
            return self._mock_saylor_tweet(topic, sentiment)
        else:
            return self._mock_generic_tweet(handle, topic, sentiment)

    def _mock_elon_tweet(self, topic: str, sentiment: float) -> str:
        """Generate mock Elon Musk tweet."""
        if sentiment > 0.3:
            templates = [
                f"Exciting developments at Tesla! {topic} is going to change everything",
                f"Just approved a big {topic} order. The future is bright!",
                f"{topic} team is doing amazing work",
                f"🚀 {topic} momentum is building",
            ]
        elif sentiment < -0.3:
            templates = [
                f"{topic} concerns are valid, but we're working through it",
                f"Not happy with {topic} performance lately",
                f"Reviewing {topic} strategy now",
                f"{topic} headwinds are real",
            ]
        else:
            templates = [
                f"Thinking about {topic} today",
                f"Any thoughts on {topic}?",
                f"Watching {topic} closely",
                f"{topic} update coming soon",
            ]
        return random.choice(templates)

    def _mock_saylor_tweet(self, topic: str, sentiment: float) -> str:
        """Generate mock Michael Saylor tweet."""
        if sentiment > 0.3:
            templates = [
                f"Bitcoin is the key to financial freedom. Accumulating {topic}",
                f"If you want to preserve your wealth, buy {topic} now",
                f"The {topic} trade of a lifetime is happening",
                f"Holding {topic} for the long term. This is just the beginning",
            ]
        elif sentiment < -0.3:
            templates = [
                f"Concerns about {topic} are overblown. Stay the course",
                f"If you're selling {topic}, you're making a mistake",
                f"Every dip is a buying opportunity for {topic}",
            ]
        else:
            templates = [
                f"Monitoring {topic} developments",
                f"The {topic} market is evolving",
                f"Long-term view on {topic} unchanged",
            ]
        return random.choice(templates)

    def _mock_generic_tweet(self, handle: str, topic: str, sentiment: float) -> str:
        """Generate generic executive tweet."""
        if sentiment > 0.3:
            templates = [
                f"Great progress on {topic}!",
                f" bullish on {topic}",
                f"{topic} looking strong today",
                f"Exciting times ahead for {topic}",
            ]
        elif sentiment < -0.3:
            templates = [
                f"Concerns about {topic} are mounting",
                f"Watching {topic} situation carefully",
                f"{topic} facing some headwinds",
            ]
        else:
            templates = [
                f"Thoughts on {topic}?",
                f"Monitoring {topic}",
                f"Any {topic} news to share?",
            ]
        prefix = f"@{handle}: " if random.random() > 0.7 else ""
        return prefix + random.choice(templates)


class CEOTwitterStrategy:
    """CEO/Executive Twitter trading strategy.

    Monitors executive accounts and generates trading signals when
    sentiment and keywords indicate directional bias.

    NOTE: This is HIGH RISK - require confirmation from multiple signals.
    """

    def __init__(
        self,
        config: Optional[CEOTwitterConfig] = None,
        api_key: Optional[str] = None,
    ):
        """Initialize strategy.

        Args:
            config: Strategy configuration.
            api_key: Optional Twitter/X API key.
        """
        self._config = config or CEOTwitterConfig()
        self._scorer = CEOTwitterScorer()
        self._fetcher = CEOTwitterFetcher(api_key=api_key)

    @property
    def config(self) -> CEOTwitterConfig:
        """Get strategy configuration."""
        return self._config

    def fetch_and_analyze(
        self,
        handle: str,
        symbol: Optional[str] = None,
    ) -> list[TweetSignal]:
        """Fetch tweets from an executive and analyze for signals.

        Args:
            handle: Twitter handle (without @).
            symbol: Optional specific symbol to look for.

        Returns:
            List of TweetSignal objects.
        """
        tweets = self._fetcher.fetch_tweets(handle, hours=self._config.max_age_hours)
        signals: list[TweetSignal] = []

        # Get executive info
        exec_info = EXECUTIVE_ACCOUNTS.get(handle)
        if not exec_info:
            return signals

        target_symbols = [symbol] if symbol else list(exec_info.symbols)

        for tweet in tweets:
            text = tweet["text"].lower()

            # Check each target symbol
            for sym in target_symbols:
                signal, keyword = self._extract_signal(text, tweet["text"], sym, handle, exec_info)
                if signal:
                    signals.append(signal)

        return signals

    def _extract_signal(
        self,
        text: str,
        raw_text: str,
        symbol: str,
        handle: str,
        exec_info: ExecutiveAccount,
    ) -> tuple[Optional[TweetSignal], Optional[SignalKeyword]]:
        """Extract trading signal from tweet text.

        Returns:
            Tuple of (TweetSignal or None, matched keyword or None).
        """
        # Check for symbol mention
        is_direct = symbol.lower() in text or f"${symbol.lower()}" in text

        # Check for signal keywords
        matched_keyword = None
        for kw in SignalKeyword:
            if any(k in text for k in kw.value):
                matched_keyword = kw
                break

        if not matched_keyword:
            return None, None

        # Score sentiment
        raw_sentiment = self._scorer.score(raw_text)

        # Calculate confidence based on engagement and sentiment strength
        engagement_factor = min(1.0, 0.3)  # Simplified for mock
        confidence = min(0.95, max(0.3, abs(raw_sentiment) * engagement_factor))

        # Time decay
        now = datetime.now()
        hours_old = (now - tweet["timestamp"]).total_seconds() / 3600
        decay_factor = max(0.5, 1.0 - (hours_old / self._config.signal_decay_hours))
        confidence *= decay_factor

        return (
            TweetSignal(
                executive_handle=handle,
                executive_name=exec_info.name,
                company=exec_info.company,
                symbol=symbol,
                keyword=matched_keyword,
                raw_sentiment=raw_sentiment,
                confidence=confidence,
                is_direct_mention=is_direct,
                timestamp=datetime.now(),
                text=raw_text,
            ),
            matched_keyword,
        )

    def aggregate_signals(
        self,
        signals: list[TweetSignal],
    ) -> AggregatedSignal:
        """Aggregate multiple tweet signals into a trading signal.

        Args:
            signals: List of individual tweet signals.

        Returns:
            AggregatedSignal with combined analysis.
        """
        if not signals:
            return AggregatedSignal(
                symbol="",
                executive_signals=[],
                aggregated_sentiment=0.0,
                total_confidence=0.0,
                signal_count=0,
                most_recent_timestamp=datetime.now(),
                side="neutral",
                strength="weak",
            )

        # Group by symbol
        by_symbol: dict[str, list[TweetSignal]] = {}
        for sig in signals:
            by_symbol.setdefault(sig.symbol, []).append(sig)

        # Find symbol with strongest signal
        best_symbol = ""
        best_score = float("-inf")

        for sym, sym_signals in by_symbol.items():
            symbol_score = sum(s.raw_sentiment * s.confidence for s in sym_signals)
            if symbol_score > best_score:
                best_score = symbol_score
                best_symbol = sym

        # Calculate aggregated metrics for best symbol
        symbol_signals = by_symbol.get(best_symbol, [])
        agg_sentiment = sum(s.raw_sentiment for s in symbol_signals) / len(symbol_signals)
        total_conf = sum(s.confidence for s in symbol_signals) / len(symbol_signals)
        most_recent = max(s.timestamp for s in symbol_signals)

        # Determine side and strength
        if agg_sentiment > self._config.sentiment_threshold:
            side = "long"
        elif agg_sentiment < -self._config.sentiment_threshold:
            side = "short"
        else:
            side = "neutral"

        signal_count = len(symbol_signals)
        if (
            signal_count >= self._config.min_signals_for_action
            and total_conf > self._config.min_confidence
        ):
            if abs(agg_sentiment) > 0.5:
                strength = "strong"
            elif abs(agg_sentiment) > 0.3:
                strength = "moderate"
            else:
                strength = "weak"
        else:
            strength = "weak"

        return AggregatedSignal(
            symbol=best_symbol,
            executive_signals=symbol_signals,
            aggregated_sentiment=agg_sentiment,
            total_confidence=total_conf,
            signal_count=signal_count,
            most_recent_timestamp=most_recent,
            side=side,
            strength=strength,
        )

    def should_trade(self, aggregated: AggregatedSignal) -> tuple[bool, str]:
        """Determine if we should act on an aggregated signal.

        Args:
            aggregated: Aggregated signal to evaluate.

        Returns:
            Tuple of (should_trade, reason).
        """
        # Check minimum signals requirement (HIGH RISK mitigation)
        if aggregated.signal_count < self._config.min_signals_for_action:
            return (
                False,
                f"Insufficient signals: {aggregated.signal_count} < {self._config.min_signals_for_action}",
            )

        # Check confidence
        if aggregated.total_confidence < self._config.min_confidence:
            return (
                False,
                f"Low confidence: {aggregated.total_confidence:.2f} < {self._config.min_confidence}",
            )

        # Check sentiment threshold
        if abs(aggregated.aggregated_sentiment) < self._config.sentiment_threshold:
            return False, f"Neutral sentiment: {aggregated.aggregated_sentiment:.2f}"

        # All checks passed
        return (
            True,
            f"Signal accepted: {aggregated.side} {aggregated.symbol} ({aggregated.strength})",
        )

    def generate_signal(
        self,
        handle: str,
        symbol: Optional[str] = None,
    ) -> tuple[AggregatedSignal, bool, str]:
        """Generate a trading signal from executive tweets.

        Args:
            handle: Twitter handle to analyze.
            symbol: Optional specific symbol.

        Returns:
            Tuple of (AggregatedSignal, should_trade, reason).
        """
        signals = self.fetch_and_analyze(handle, symbol)
        aggregated = self.aggregate_signals(signals)
        should_trade, reason = self.should_trade(aggregated)
        return aggregated, should_trade, reason

    def get_signals_for_all_handles(
        self,
        symbol: Optional[str] = None,
    ) -> dict[str, tuple[AggregatedSignal, bool, str]]:
        """Get signals for all tracked executive handles.

        Args:
            symbol: Optional symbol to filter for.

        Returns:
            Dict mapping handle -> (AggregatedSignal, should_trade, reason).
        """
        results: dict[str, tuple[AggregatedSignal, bool, str]] = {}

        for handle in self._config.tracked_handles:
            aggregated, should_trade, reason = self.generate_signal(handle, symbol)
            results[handle] = (aggregated, should_trade, reason)

        return results

    def backtest(
        self,
        symbol: str,
        prices: Sequence[float],
        handle: str,
    ) -> BacktestResult:
        """Backtest strategy on historical data.

        Args:
            symbol: Symbol to backtest.
            prices: Historical price series.
            handle: Executive handle to simulate.

        Returns:
            BacktestResult with performance metrics.
        """
        # Generate mock historical signals
        historical_signals = self._generate_historical_signals(handle, symbol, len(prices))

        # Generate trading signals
        signals: list[SignalType] = []
        for score in historical_signals:
            if score > self._config.sentiment_threshold:
                signals.append(SignalType.BUY)
            elif score < -self._config.sentiment_threshold:
                signals.append(SignalType.SELL)
            else:
                signals.append(SignalType.NEUTRAL)

        # Pad signals to match prices length
        while len(signals) < len(prices):
            signals.append(SignalType.NEUTRAL)

        backtester = Backtester(prices, signals)
        return backtester.run()

    def _generate_historical_signals(
        self,
        handle: str,
        symbol: str,
        length: int,
    ) -> list[float]:
        """Generate realistic mock historical sentiment data.

        Args:
            handle: Executive handle.
            symbol: Symbol.
            length: Number of data points.

        Returns:
            List of sentiment scores.
        """
        rng = random.Random(hash(handle + symbol) % 2**32)
        sentiment = 0.0
        scores: list[float] = []

        profile = CEOTwitterFetcher.EXECUTIVE_PROFILES.get(handle, {"volatility": 0.3})

        for _ in range(length):
            # Random walk with mean reversion
            change = rng.gauss(0.0, profile.get("volatility", 0.3))
            reversion = -sentiment * 0.1
            sentiment = max(-1.0, min(1.0, sentiment + change + reversion))
            scores.append(sentiment)

        return scores
