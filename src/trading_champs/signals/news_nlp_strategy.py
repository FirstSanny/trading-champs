"""News NLP sentiment trading strategy.

Analyzes financial news articles using NLP to generate trading signals
before the market reacts fully. Uses named entity recognition to identify
companies and events, with time-decay weighting for signal freshness.

Key components:
1. Sources: News API, PR Newswire, Business Wire, SEC filings
2. NLP pipeline: Named Entity Recognition to identify companies,
   sentiment around specific events
3. Event detection: earnings, M&A, FDA decisions, regulatory changes
4. Time-series analysis: how did price react historically to similar
   news patterns?
5. Generate signals with confidence scores and time decay
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Sequence

from trading_champs.signals.backtester import Backtester, BacktestResult, PositionSide, SignalType


class EventType(Enum):
    """Types of financial events detected in news."""

    EARNINGS = "earnings"
    MERGERS_ACQUISITIONS = "ma"
    FDA_DECISION = "fda"
    REGULATORY = "regulatory"
    PRODUCT_LAUNCH = "product"
    PARTNERSHIP = "partnership"
    INSIDER_TRADING = "insider"
    ANALYST_UPGRADE = "upgrade"
    ANALYST_DOWNGRADE = "downgrade"
    DIVIDEND = "dividend"
    BUYBACK = "buyback"
    GENERAL = "general"


@dataclass(frozen=True)
class NewsArticle:
    """A single news article with NLP metadata."""

    headline: str
    source: str
    url: str
    timestamp: datetime
    symbols: tuple[str, ...]
    entities: tuple[str, ...]
    sentiment_score: float  # -1 to +1
    event_type: EventType
    confidence: float  # 0 to 1
    relevance_score: float  # 0 to 1


@dataclass
class NLPSignal:
    """A trading signal generated from news NLP analysis."""

    symbol: str
    article: NewsArticle
    direction: SignalType
    confidence: float
    time_decay_factor: float  # 0 to 1, decreases with age
    event_type: EventType
    historical_reaction_strength: float  # How similar events historically moved price
    combined_score: float  # Weighted combination of all factors


@dataclass
class NewsNLPConfig:
    """Configuration for news NLP strategy."""

    # Sentiment thresholds
    buy_threshold: float = 0.25
    sell_threshold: float = -0.25
    # Minimum confidence to act
    min_confidence: float = 0.55
    min_relevance: float = 0.5
    # Time decay settings
    decay_half_life_hours: int = 4  # Score halves after this many hours
    max_age_hours: int = 24
    # Symbols to track
    symbols: list[str] = field(
        default_factory=lambda: ["AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "META", "NVDA"]
    )
    # Event type weights (how much each event type affects signal)
    event_weights: dict[EventType, float] = field(
        default_factory=lambda: {
            EventType.EARNINGS: 1.5,
            EventType.FDA_DECISION: 1.5,
            EventType.MERGERS_ACQUISITIONS: 1.4,
            EventType.REGULATORY: 1.3,
            EventType.ANALYST_UPGRADE: 1.2,
            EventType.ANALYST_DOWNGRADE: 1.2,
            EventType.INSIDER_TRADING: 1.1,
            EventType.DIVIDEND: 0.9,
            EventType.BUYBACK: 1.0,
            EventType.PRODUCT_LAUNCH: 1.1,
            EventType.PARTNERSHIP: 1.0,
            EventType.GENERAL: 0.8,
        }
    )
    # Lookback for historical pattern matching
    pattern_lookback_days: int = 90


# Mock news data profiles per symbol
SYMBOL_NEWS_PROFILES: dict[str, dict] = {
    "AAPL": {
        "base_sentiment": 0.08,
        "volatility": 0.18,
        "keywords": ["Apple", "iPhone", "WWDC", "Tim Cook", "services", "Mac", "iPad"],
        "events": [EventType.EARNINGS, EventType.PRODUCT_LAUNCH, EventType.DIVIDEND],
    },
    "TSLA": {
        "base_sentiment": 0.0,
        "volatility": 0.4,
        "keywords": ["Tesla", "Elon Musk", "EV", "autopilot", "robotaxi", "battery"],
        "events": [EventType.EARNINGS, EventType.PRODUCT_LAUNCH, EventType.REGULATORY],
    },
    "MSFT": {
        "base_sentiment": 0.1,
        "volatility": 0.15,
        "keywords": ["Microsoft", "Azure", "OpenAI", "Copilot", "LinkedIn", "Xbox"],
        "events": [EventType.EARNINGS, EventType.PARTNERSHIP, EventType.DIVIDEND],
    },
    "GOOGL": {
        "base_sentiment": 0.06,
        "volatility": 0.17,
        "keywords": ["Google", "Alphabet", "AI", "Search", "YouTube", "Android", "Cloud"],
        "events": [EventType.EARNINGS, EventType.REGULATORY, EventType.DIVIDEND],
    },
    "AMZN": {
        "base_sentiment": 0.07,
        "volatility": 0.2,
        "keywords": ["Amazon", "AWS", "Prime", "e-commerce", "logistics", "AI"],
        "events": [EventType.EARNINGS, EventType.DIVIDEND, EventType.REGULATORY],
    },
    "META": {
        "base_sentiment": 0.04,
        "volatility": 0.25,
        "keywords": ["Meta", "Facebook", "Instagram", "Reels", "VR", "元宇宙", "AI"],
        "events": [EventType.EARNINGS, EventType.REGULATORY, EventType.ANALYST_UPGRADE],
    },
    "NVDA": {
        "base_sentiment": 0.15,
        "volatility": 0.35,
        "keywords": ["Nvidia", "GPU", "AI chip", "H100", "data center", "gaming"],
        "events": [EventType.EARNINGS, EventType.PRODUCT_LAUNCH, EventType.DIVIDEND],
    },
    "GME": {
        "base_sentiment": -0.1,
        "volatility": 0.5,
        "keywords": ["GameStop", "Reddit", "short squeeze", "Ryan Cohen"],
        "events": [EventType.EARNINGS, EventType.INSIDER_TRADING],
    },
}


class EventDetector:
    """Detects financial event types from news text."""

    EVENT_PATTERNS: dict[EventType, list[str]] = {
        EventType.EARNINGS: [
            "earnings", "revenue", "eps", "guidance", "quarterly results",
            "q1", "q2", "q3", "q4", "fiscal year", "beat estimates",
        ],
        EventType.MERGERS_ACQUISITIONS: [
            "acquire", "acquisition", "merger", "buyout", "takeover",
            "deal", "purchase", "merge with", "acquire stake",
        ],
        EventType.FDA_DECISION: [
            "fda", "approval", "drug approval", "clinical trial",
            "fda panel", "new drug application", "nda", "biotech",
        ],
        EventType.REGULATORY: [
            "sec", "ftc", "doj", "antitrust", "investigation", "fine",
            "regulation", "compliance", "lawsuit", "settlement",
        ],
        EventType.ANALYST_UPGRADE: [
            "upgrade", "raise price target", "buy rating", "outperform",
            "overweight", "bullish", "upgrade from",
        ],
        EventType.ANALYST_DOWNGRADE: [
            "downgrade", "lower price target", "sell rating", "underperform",
            "underweight", "bearish", "downgrade from",
        ],
        EventType.INSIDER_TRADING: [
            "insider buying", "insider selling", "ceo buys", "cfo sells",
            "director purchases", "exec exercises options",
        ],
        EventType.DIVIDEND: [
            "dividend", "quarterly dividend", "special dividend",
            "dividend yield", "shareholder payout",
        ],
        EventType.BUYBACK: [
            "buyback", "repurchase", "share repurchase", "stock buyback",
        ],
        EventType.PRODUCT_LAUNCH: [
            "launch", "unveil", "new product", "release", "debut",
            "announce", "preview",
        ],
        EventType.PARTNERSHIP: [
            "partnership", "collaboration", "joint venture", "deal with",
            "strategic alliance", "partner",
        ],
        EventType.GENERAL: [],
    }

    def detect(self, headline: str, body: str = "") -> EventType:
        """Detect event type from headline and optional body text.

        Args:
            headline: News headline.
            body: Optional article body.

        Returns:
            Detected EventType.
        """
        text = (headline + " " + body).lower()

        detected_events: list[tuple[EventType, int]] = []

        for event_type, patterns in self.EVENT_PATTERNS.items():
            if event_type == EventType.GENERAL:
                continue
            count = sum(1 for pattern in patterns if pattern in text)
            if count > 0:
                detected_events.append((event_type, count))

        if detected_events:
            # Return the event with most pattern matches
            return max(detected_events, key=lambda x: x[1])[0]

        return EventType.GENERAL

    def detect_symbols(self, headline: str, known_symbols: list[str]) -> list[str]:
        """Detect mentioned symbols in headline.

        Args:
            headline: News headline.
            known_symbols: List of known symbols to check.

        Returns:
            List of detected symbol strings.
        """
        headline_upper = headline.upper()
        found: list[str] = []

        for symbol in known_symbols:
            # Check for symbol alone (not as part of another word)
            if symbol in headline_upper.split():
                found.append(symbol)
            elif f"${symbol}" in headline_upper:
                found.append(symbol)

        return found


class SentimentScorer:
    """NLP sentiment scoring using VADER.

    Returns compound scores from -1 (most negative) to +1 (most positive).
    """

    def __init__(self) -> None:
        """Initialize VADER sentiment analyzer."""
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._analyzer = SentimentIntensityAnalyzer()
            self._available = True
        except ImportError:
            self._analyzer = None
            self._available = False

    @property
    def is_available(self) -> bool:
        """Check if VADER is available."""
        return self._available

    def score(self, text: str) -> float:
        """Score text sentiment.

        Args:
            text: Input text to analyze.

        Returns:
            Compound sentiment score from -1 to +1.
        """
        if not self._available:
            # Fallback to simple keyword-based scoring
            return self._fallback_score(text)

        scores: dict[str, float] = self._analyzer.polarity_scores(text)
        return float(scores["compound"])

    def _fallback_score(self, text: str) -> float:
        """Fallback keyword-based sentiment scoring."""
        text_lower = text.lower()
        positive_words = [
            "beat", "surge", "jump", "rise", "gain", "grow", "profit",
            "upgrade", "buy", "bullish", "strong", "growth", "innovative",
            "partnership", "launch", "approval", "acquire",
        ]
        negative_words = [
            "miss", "fall", "drop", "decline", "loss", "cut", "reduce",
            "downgrade", "sell", "bearish", "weak", "investigation",
            "fine", "lawsuit", "antitrust", "regulation",
        ]

        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)
        total = pos_count + neg_count

        if total == 0:
            return 0.0
        return (pos_count - neg_count) / total


class NewsFetcher:
    """Fetches financial news articles.

    In production, connects to News API, PR Newswire, Business Wire, SEC filings.
    For now, generates realistic mock data based on symbol profiles.
    """

    SOURCES = [
        "Reuters", "Bloomberg", "CNBC", "WSJ", "Financial Times",
        "Barrons", "MarketWatch", "Seeking Alpha", "PR Newswire", "Business Wire",
    ]

    def __init__(self, api_keys: Optional[dict] = None):
        """Initialize fetcher.

        Args:
            api_keys: Optional dict with news_api_key, prnewswire_key, etc.
        """
        self._keys = api_keys or {}

    def fetch_articles(
        self,
        symbol: str,
        hours: int = 24,
    ) -> list[NewsArticle]:
        """Fetch news articles for a symbol.

        Args:
            symbol: Stock symbol.
            hours: Lookback window in hours.

        Returns:
            List of NewsArticle objects.
        """
        # In production: make real API calls based on self._keys
        return self._generate_mock_articles(symbol, hours)

    def _generate_mock_articles(self, symbol: str, hours: int) -> list[NewsArticle]:
        """Generate realistic mock news articles.

        Args:
            symbol: Trading symbol.
            hours: Lookback window.

        Returns:
            List of mock NewsArticle objects.
        """
        profile = SYMBOL_NEWS_PROFILES.get(
            symbol,
            {
                "base_sentiment": 0.0,
                "volatility": 0.25,
                "keywords": [symbol],
                "events": [EventType.GENERAL],
            },
        )

        articles: list[NewsArticle] = []
        num_articles = random.randint(8, 25)
        now = datetime.now()

        for i in range(num_articles):
            hours_ago = random.uniform(0, hours)
            timestamp = now - timedelta(hours=hours_ago)

            source = random.choice(self.SOURCES)
            keyword = random.choice(profile["keywords"])
            event_type = random.choice(profile["events"])

            # Generate sentiment based on profile
            sentiment = random.gauss(profile["base_sentiment"], profile["volatility"])
            sentiment = max(-1.0, min(1.0, sentiment))

            headline = self._generate_headline(symbol, keyword, event_type, sentiment)
            entities = self._extract_entities(headline, symbol)

            # Relevance based on how closely headline mentions symbol
            relevance = 0.5 + 0.3 * int(symbol.lower() in headline.lower())
            confidence = min(0.95, abs(sentiment) + 0.2)

            articles.append(
                NewsArticle(
                    headline=headline,
                    source=source,
                    url=f"https://example.com/news/{random.randint(1000000, 9999999)}",
                    timestamp=timestamp,
                    symbols=(symbol,),
                    entities=entities,
                    sentiment_score=sentiment,
                    event_type=event_type,
                    confidence=confidence,
                    relevance_score=relevance,
                )
            )

        # Sort by timestamp descending
        articles.sort(key=lambda a: a.timestamp, reverse=True)
        return articles

    def _generate_headline(
        self,
        symbol: str,
        keyword: str,
        event_type: EventType,
        sentiment: float,
    ) -> str:
        """Generate mock headline based on event type and sentiment."""
        templates: dict[EventType, list[str]] = {
            EventType.EARNINGS: {
                "positive": [
                    f"{symbol} Reports Strong {keyword} Earnings, Beats Estimates",
                    f"{symbol} Q4 Revenue Jumps on {keyword} Growth",
                    f"{symbol} Raises Full-Year Guidance After {keyword} Beat",
                ],
                "negative": [
                    f"{symbol} Misses {keyword} Revenue Expectations",
                    f"{symbol} Cuts Guidance Despite {keyword} Performance",
                    f"{symbol} Earnings Disappoint on {keyword} Weakness",
                ],
                "neutral": [
                    f"{symbol} Reports In-Line {keyword} Earnings",
                    f"{symbol} {keyword} Results In-Line with Expectations",
                ],
            },
            EventType.FDA_DECISION: {
                "positive": [
                    f"FDA Approves {symbol} {keyword} Drug Candidate",
                    f"{symbol} {keyword} Treatment Wins FDA Panel Backing",
                ],
                "negative": [
                    f"FDA Rejects {symbol} {keyword} Application",
                    f"{symbol} {keyword} Drug Faces Regulatory Setback",
                ],
                "neutral": [
                    f"FDA Reviews {symbol} {keyword} Application",
                    f"{symbol} {keyword} Decision Expected Soon",
                ],
            },
            EventType.MERGERS_ACQUISITIONS: {
                "positive": [
                    f"{symbol} to Acquire {keyword} in $2B Deal",
                    f"{symbol} Announces Strategic {keyword} Partnership",
                ],
                "negative": [
                    f"{symbol} {keyword} Deal Faces Antitrust Scrutiny",
                    f"{symbol} Terminates {keyword} Acquisition Talks",
                ],
                "neutral": [
                    f"{symbol} in Talks Over {keyword} Potential Deal",
                    f"{symbol} Evaluates {keyword} Strategic Options",
                ],
            },
            EventType.REGULATORY: {
                "positive": [
                    f"{symbol} Wins Regulatory Approval for {keyword}",
                    f"{symbol} {keyword} Investigation Dropped by FTC",
                ],
                "negative": [
                    f"DOJ Opens {symbol} {keyword} Investigation",
                    f"{symbol} Faces {keyword} Regulatory Fine",
                ],
                "neutral": [
                    f"{symbol} Cooperates with {keyword} Regulators",
                    f"{symbol} Monitors {keyword} Regulatory Developments",
                ],
            },
            EventType.ANALYST_UPGRADE: {
                "positive": [
                    f"Analysts Upgrade {symbol} to Buy on {keyword} Outlook",
                    f"Wells Fargo Raises {symbol} Price Target on {keyword}",
                ],
                "negative": [
                    f"Analyst Downgrades {symbol} on {keyword} Concerns",
                    f"Barclays Cuts {symbol} Rating on {keyword}",
                ],
                "neutral": [
                    f"Analysts Maintain {symbol} Rating on {keyword}",
                ],
            },
        }

        templates_for_event = templates.get(event_type, templates[EventType.EARNINGS])

        if sentiment > 0.2:
            choices = templates_for_event["positive"]
        elif sentiment < -0.2:
            choices = templates_for_event["negative"]
        else:
            choices = templates_for_event["neutral"]

        return random.choice(choices)

    def _extract_entities(self, headline: str, symbol: str) -> tuple[str, ...]:
        """Extract named entities from headline.

        In production, would use spaCy NER.
        For now, extract capitalized words as entities.
        """
        words = headline.upper().split()
        entities = [w.strip(",.():") for w in words if w[0].isupper() and len(w) > 2]
        # Dedupe while preserving order
        seen = set()
        unique_entities = []
        for e in entities:
            if e not in seen and e != symbol:
                seen.add(e)
                unique_entities.append(e)
        return tuple(unique_entities)


class HistoricalPatternMatcher:
    """Analyzes how price historically reacted to similar news events.

    Maintains a mock history of event->price reaction patterns.
    """

    def __init__(self, lookback_days: int = 90) -> None:
        """Initialize pattern matcher.

        Args:
            lookback_days: How many days of history to consider.
        """
        self._lookback_days = lookback_days
        self._patterns: dict[str, list[float]] = {}  # event_type -> list of % changes

        # Initialize with realistic mock patterns
        self._init_mock_patterns()

    def _init_mock_patterns(self) -> None:
        """Initialize mock historical reaction patterns."""
        # Event type -> (mean % move, std dev)
        event_stats: dict[EventType, tuple[float, float]] = {
            EventType.EARNINGS: (2.5, 5.0),
            EventType.FDA_DECISION: (5.0, 12.0),
            EventType.MERGERS_ACQUISITIONS: (3.0, 8.0),
            EventType.REGULATORY: (-2.0, 6.0),
            EventType.ANALYST_UPGRADE: (1.5, 3.0),
            EventType.ANALYST_DOWNGRADE: (-2.0, 3.5),
            EventType.INSIDER_TRADING: (0.5, 2.0),
            EventType.DIVIDEND: (0.3, 1.0),
            EventType.BUYBACK: (0.5, 1.5),
            EventType.PRODUCT_LAUNCH: (1.0, 3.0),
            EventType.PARTNERSHIP: (0.8, 2.0),
            EventType.GENERAL: (0.2, 1.0),
        }

        for event_type, (mean, std) in event_stats.items():
            # Generate 30 mock historical reactions
            rng = random.Random(hash(event_type.value) % 1000)
            self._patterns[event_type.value] = [
                max(-15, min(15, rng.gauss(mean, std))) for _ in range(30)
            ]

    def get_reaction_strength(
        self,
        event_type: EventType,
        sentiment: float,
    ) -> float:
        """Get historical reaction strength for an event type.

        Args:
            event_type: Type of detected event.
            sentiment: Sentiment of the news (positive or negative).

        Returns:
            Reaction strength from -1 (strongly negative) to +1 (strongly positive).
        """
        pattern_key = event_type.value
        if pattern_key not in self._patterns:
            return 0.0

        historical_moves = self._patterns[pattern_key]
        avg_move = sum(historical_moves) / len(historical_moves)

        # Sentiment amplifies or dampens the expected reaction
        sentiment_factor = sentiment  # -1 to +1
        reaction = (avg_move / 10.0) * sentiment_factor  # Normalize to -1 to +1

        return max(-1.0, min(1.0, reaction))

    def get_confidence(self, event_type: EventType) -> float:
        """Get confidence in pattern based on historical sample size.

        Args:
            event_type: Type of event.

        Returns:
            Confidence score from 0 to 1.
        """
        pattern_key = event_type.value
        if pattern_key not in self._patterns:
            return 0.3

        # More historical data = higher confidence (capped at 0.9)
        sample_size = len(self._patterns[pattern_key])
        confidence = min(0.9, 0.3 + (sample_size / 100))
        return confidence


class NewsNLPStrategy:
    """News NLP sentiment trading strategy.

    Analyzes financial news using NLP to generate trading signals
    before the market fully reacts to news events.
    """

    def __init__(
        self,
        config: Optional[NewsNLPConfig] = None,
        api_keys: Optional[dict] = None,
    ):
        """Initialize news NLP strategy.

        Args:
            config: Strategy configuration.
            api_keys: Optional API keys for real news sources.
        """
        self._config = config or NewsNLPConfig()
        self._event_detector = EventDetector()
        self._sentiment_scorer = SentimentScorer()
        self._fetcher = NewsFetcher(api_keys=api_keys)
        self._pattern_matcher = HistoricalPatternMatcher(
            lookback_days=self._config.pattern_lookback_days
        )

    @property
    def config(self) -> NewsNLPConfig:
        """Get strategy configuration."""
        return self._config

    def fetch_and_analyze(self, symbol: str) -> tuple[list[NewsArticle], list[NLPSignal]]:
        """Fetch news and generate NLP signals for a symbol.

        Args:
            symbol: Trading symbol.

        Returns:
            Tuple of (raw articles, generated signals).
        """
        articles = self._fetcher.fetch_articles(
            symbol=symbol,
            hours=self._config.max_age_hours,
        )

        signals: list[NLPSignal] = []

        for article in articles:
            # Calculate time decay factor
            age_hours = (datetime.now() - article.timestamp).total_seconds() / 3600
            decay_factor = self._calc_time_decay(age_hours)

            # Get event weight
            event_weight = self._config.event_weights.get(
                article.event_type, 1.0
            )

            # Get historical reaction strength
            reaction_strength = self._pattern_matcher.get_reaction_strength(
                article.event_type,
                article.sentiment_score,
            )

            # Calculate combined score
            raw_score = (
                article.sentiment_score
                * article.confidence
                * article.relevance_score
                * event_weight
                * decay_factor
            )

            # Factor in historical pattern
            pattern_contribution = reaction_strength * 0.3
            combined = raw_score * 0.7 + pattern_contribution

            # Determine direction
            if combined > self._config.buy_threshold:
                direction = SignalType.BUY
            elif combined < self._config.sell_threshold:
                direction = SignalType.SELL
            else:
                direction = SignalType.NEUTRAL

            signal = NLPSignal(
                symbol=symbol,
                article=article,
                direction=direction,
                confidence=article.confidence * event_weight * decay_factor,
                time_decay_factor=decay_factor,
                event_type=article.event_type,
                historical_reaction_strength=reaction_strength,
                combined_score=combined,
            )

            signals.append(signal)

        return articles, signals

    def _calc_time_decay(self, hours_ago: float) -> float:
        """Calculate time decay factor.

        Args:
            hours_ago: How many hours ago the article was published.

        Returns:
            Decay factor from 0 to 1.
        """
        half_life = self._config.decay_half_life_hours
        decay = 0.5 ** (hours_ago / half_life)
        return max(0.1, min(1.0, decay))

    def aggregate_signals(
        self,
        signals: list[NLPSignal],
    ) -> tuple[SignalType, float, float]:
        """Aggregate multiple signals into a single decision.

        Args:
            signals: List of individual NLPSignals.

        Returns:
            Tuple of (aggregated direction, combined score, aggregate confidence).
        """
        if not signals:
            return SignalType.NEUTRAL, 0.0, 0.0

        # Weight by confidence and time decay
        weighted_scores: list[float] = []
        total_weight = 0.0

        for sig in signals:
            weight = sig.confidence * sig.time_decay_factor
            weighted_scores.append(sig.combined_score * weight)
            total_weight += weight

        if total_weight == 0:
            return SignalType.NEUTRAL, 0.0, 0.0

        agg_score = sum(weighted_scores) / total_weight
        agg_confidence = sum(s.confidence for s in signals) / len(signals)

        # Apply thresholds
        if agg_score > self._config.buy_threshold:
            direction = SignalType.BUY
        elif agg_score < self._config.sell_threshold:
            direction = SignalType.SELL
        else:
            direction = SignalType.NEUTRAL

        return direction, agg_score, agg_confidence

    def get_signals_for_symbols(
        self,
        symbols: Optional[list[str]] = None,
    ) -> dict[str, tuple[SignalType, float, float, list[NLPSignal]]]:
        """Get trading signals for multiple symbols.

        Args:
            symbols: List of symbols to analyze. Uses config symbols if None.

        Returns:
            Dict mapping symbol -> (direction, score, confidence, signals).
        """
        target_symbols = symbols or self._config.symbols
        results: dict[str, tuple[SignalType, float, float, list[NLPSignal]]] = {}

        for symbol in target_symbols:
            _, signals = self.fetch_and_analyze(symbol)
            direction, score, confidence = self.aggregate_signals(signals)
            results[symbol] = (direction, score, confidence, signals)

        return results

    def backtest(
        self,
        symbol: str,
        prices: Sequence[float],
        start_date: Optional[datetime] = None,
    ) -> BacktestResult:
        """Backtest strategy on historical data.

        Args:
            symbol: Symbol to backtest.
            prices: Historical price series.
            start_date: Optional start date.

        Returns:
            BacktestResult with performance metrics.
        """
        # Generate mock historical news signals
        historical_signals = self._generate_historical_signals(
            len(prices),
            hash(symbol) % 1000,
        )

        backtester = Backtester(prices, historical_signals)
        return backtester.run()

    def _generate_historical_signals(self, length: int, seed: int) -> list[SignalType]:
        """Generate mock historical signals for backtesting.

        Args:
            length: Number of data points.
            seed: Random seed.

        Returns:
            List of SignalTypes.
        """
        rng = random.Random(seed)
        signals: list[SignalType] = []

        for _ in range(length):
            # Random walk with mean reversion
            score = rng.gauss(0.0, 0.3)
            score = max(-1.0, min(1.0, score))

            if score > self._config.buy_threshold:
                signals.append(SignalType.BUY)
            elif score < self._config.sell_threshold:
                signals.append(SignalType.SELL)
            else:
                signals.append(SignalType.NEUTRAL)

        # Pad to match prices length
        while len(signals) < length:
            signals.append(SignalType.NEUTRAL)

        return signals[:length]
