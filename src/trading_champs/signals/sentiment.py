"""Social media sentiment trading strategy.

Analyzes Twitter/X, Reddit (WallStreetBets), and financial news for
sentiment scoring. Generates buy/sell signals when sentiment crosses
configurable thresholds.

Uses VADER (Valence Aware Dictionary and sEntiment Reasoner) for
NLP sentiment scoring on a -1 (bearish) to +1 (bullish) scale.
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
from trading_champs.signals.detectors.crossover import CrossoverDetector


class SentimentSource(Enum):
    """Supported sentiment data sources."""

    TWITTER = "twitter"
    REDDIT = "reddit"
    NEWS = "news"
    ALL = "all"


@dataclass
class SentimentSignal:
    """A single sentiment-based trading signal."""

    symbol: str
    source: SentimentSource
    sentiment_score: float  # -1 to +1
    confidence: float  # 0 to 1
    headline: str
    timestamp: datetime
    side: str  # "long" or "short"


@dataclass
class SentimentConfig:
    """Configuration for sentiment strategy."""

    # Threshold settings
    buy_threshold: float = 0.3  # Sentiment above this → BUY
    sell_threshold: float = -0.3  # Sentiment below this → SELL
    # Sentiment smoothing
    smoothing_window: int = 5  # Rolling average window for sentiment
    # Minimum confidence to act
    min_confidence: float = 0.6
    # Data sources to use
    sources: list[SentimentSource] = field(default_factory=lambda: [SentimentSource.ALL])
    # Symbols to track
    symbols: list[str] = field(default_factory=lambda: ["SPY", "QQQ", "AAPL", "TSLA", "GME"])
    # Lookback window for sentiment history (hours)
    lookback_hours: int = 24


class SentimentScorer:
    """NLP sentiment scoring using VADER.

    VADER is specifically tuned for social media text and returns
    compound scores from -1 (most negative) to +1 (most positive).
    """

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

    def score_batch(self, texts: list[str]) -> list[float]:
        """Score multiple texts.

        Args:
            texts: List of texts to analyze.

        Returns:
            List of compound sentiment scores.
        """
        return [self.score(text) for text in texts]


class SocialMediaFetcher:
    """Fetches social media posts for sentiment analysis.

    In production, this connects to real APIs (Twitter/X, Reddit, news).
    For now, generates realistic mock data based on symbol sentiment profiles.
    """

    # Mock sentiment profiles per symbol
    SYMBOL_PROFILES: dict[str, dict] = {
        "SPY": {
            "base_sentiment": 0.05,
            "volatility": 0.15,
            "keywords": ["S&P 500", "market", "economy", "Fed", "inflation"],
        },
        "QQQ": {
            "base_sentiment": 0.08,
            "volatility": 0.2,
            "keywords": ["tech", "NASDAQ", "AI", "semiconductor", "cloud"],
        },
        "AAPL": {
            "base_sentiment": 0.1,
            "volatility": 0.18,
            "keywords": ["Apple", "iPhone", "WWDC", "Tim Cook", "services"],
        },
        "TSLA": {
            "base_sentiment": 0.0,
            "volatility": 0.4,
            "keywords": ["Tesla", "Elon", "Musk", "EV", "autopilot", "robotaxi"],
        },
        "GME": {
            "base_sentiment": -0.1,
            "volatility": 0.5,
            "keywords": ["GameStop", "Reddit", "short squeeze", "WSB", "diamond hands"],
        },
        "AMC": {
            "base_sentiment": -0.15,
            "volatility": 0.45,
            "keywords": ["AMC", "ape", "short squeeze", "theater", "meme"],
        },
        "BTC": {
            "base_sentiment": 0.05,
            "volatility": 0.35,
            "keywords": ["Bitcoin", "crypto", "bull", "halving", "ETF"],
        },
        "ETH": {
            "base_sentiment": 0.03,
            "volatility": 0.3,
            "keywords": ["Ethereum", "crypto", "defi", "staking", "L2"],
        },
    }

    def __init__(self, api_keys: Optional[dict] = None):
        """Initialize fetcher.

        Args:
            api_keys: Optional dict with twitter_bearer_token, reddit_client_id,
                      reddit_client_secret, news_api_key.
        """
        self._keys = api_keys or {}

    def fetch_sentiment_data(
        self,
        symbol: str,
        hours: int = 24,
        source: SentimentSource = SentimentSource.ALL,
    ) -> list[dict]:
        """Fetch social media posts for a symbol.

        Args:
            symbol: Stock/crypto symbol.
            hours: Lookback window in hours.
            source: Data source to use.

        Returns:
            List of post dicts with 'text', 'timestamp', 'source', 'engagement'.
        """
        # In production: make real API calls based on self._keys
        # For now: generate realistic mock data
        return self._generate_mock_data(symbol, hours)

    def _generate_mock_data(self, symbol: str, hours: int) -> list[dict]:
        """Generate realistic mock social media data.

        Args:
            symbol: Trading symbol.
            hours: Lookback window.

        Returns:
            List of mock post dicts.
        """
        profile = self.SYMBOL_PROFILES.get(
            symbol,
            {
                "base_sentiment": 0.0,
                "volatility": 0.25,
                "keywords": [symbol],
            },
        )

        posts: list[dict] = []
        num_posts = random.randint(20, 80)
        now = datetime.now()

        for i in range(num_posts):
            hours_ago = random.uniform(0, hours)
            timestamp = now - timedelta(hours=hours_ago)

            # Determine source
            source_choice = random.choices(
                ["twitter", "reddit", "news"],
                weights=[0.5, 0.35, 0.15],
            )[0]

            # Generate text based on keywords
            keyword = random.choice(profile["keywords"])
            sentiment = random.gauss(profile["base_sentiment"], profile["volatility"])
            sentiment = max(-1.0, min(1.0, sentiment))

            if source_choice == "twitter":
                text = self._mock_tweet(keyword, sentiment)
            elif source_choice == "reddit":
                text = self._mock_reddit_post(keyword, sentiment)
            else:
                text = self._mock_news_headline(keyword, sentiment)

            posts.append(
                {
                    "text": text,
                    "timestamp": timestamp,
                    "source": source_choice,
                    "engagement": random.randint(10, 10000),
                    "symbol": symbol,
                }
            )

        # Sort by timestamp descending
        posts.sort(key=lambda p: p["timestamp"], reverse=True)
        return posts

    def _mock_tweet(self, keyword: str, sentiment: float) -> str:
        """Generate mock tweet text."""
        if sentiment > 0.3:
            templates = [
                f"$keyword looking strong today! 📈",
                f"Just loaded up on $keyword, this is going to moon! 🚀",
                f"$keyword breaking out! Bullish confirmation incoming",
                f"$keyword holders are winning today 💰",
            ]
        elif sentiment < -0.3:
            templates = [
                f"$keyword getting crushed 😬",
                f"$keyword dump incoming, get out while you can!",
                f"Not looking good for $keyword today",
                f"$keyword losing momentum, time to fold",
            ]
        else:
            templates = [
                f"Watching $keyword closely today",
                f"$keyword consolidating, waiting for a breakout",
                f"Any thoughts on $keyword?",
                f"$keyword at support, let's see what happens",
            ]
        return random.choice(templates)

    def _mock_reddit_post(self, keyword: str, sentiment: float) -> str:
        """Generate mock Reddit post title."""
        if sentiment > 0.3:
            templates = [
                f"[Bullish] DD on $keyword - here's why we're going up",
                f"$keyword YOLO update (+15% this week)",
                f"Why $keyword is the best play right now (DD inside)",
                f"$keyword gang, we made it! To the moon! 🚀🚀🚀",
            ]
        elif sentiment < -0.3:
            templates = [
                f"[Bearish] $keyword DD - why I'm exiting my position",
                f"$keyword is dead money for now (chart included)",
                f"Lost 40% on $keyword, here's what I learned",
                f"$keyword is a trap - avoiding until further notice",
            ]
        else:
            templates = [
                f"$keyword discussion - bull case vs bear case",
                f"New to trading, what do you think of $keyword?",
                f"$keyword technical analysis thread",
                f"Should I add to my $keyword position?",
            ]
        return random.choice(templates)

    def _mock_news_headline(self, keyword: str, sentiment: float) -> str:
        """Generate mock financial news headline."""
        if sentiment > 0.3:
            templates = [
                f"$keyword Surges on Strong Earnings Beat",
                f"Analysts Upgrade $keyword to Buy on Growth Prospects",
                f"$keyword Announces Major Partnership, Stock Jumps 10%",
                f"$keyword CEO Excited About Product Pipeline, Shares Rise",
            ]
        elif sentiment < -0.3:
            templates = [
                f"$keyword Tumbles on Guidance Cut, Revenue Miss",
                f"Regulatory Concerns Weigh on $keyword Outlook",
                f"$keyword Faces Class Action as Stock Drops 20%",
                f"$keyword CFO Steps Down Amid Accounting Review",
            ]
        else:
            templates = [
                f"$keyword Reports In-Line Earnings, Shares Little Changed",
                f"$keyword Acquires Startup, Financial Terms Undisclosed",
                f"Analysts Mixed on $keyword After Investor Day",
                f"$keyword Expands Buyback but Keeps Guidance Unchanged",
            ]
        return random.choice(templates)


class SentimentStrategy:
    """Social media sentiment trading strategy.

    Analyzes social media sentiment and generates trading signals
    when sentiment crosses configured thresholds.
    """

    def __init__(
        self,
        config: Optional[SentimentConfig] = None,
        api_keys: Optional[dict] = None,
    ):
        """Initialize sentiment strategy.

        Args:
            config: Strategy configuration.
            api_keys: Optional API keys for real data sources.
        """
        self._config = config or SentimentConfig()
        self._scorer = SentimentScorer()
        self._fetcher = SocialMediaFetcher(api_keys=api_keys)
        self._sentiment_history: list[float] = []

    @property
    def config(self) -> SentimentConfig:
        """Get strategy configuration."""
        return self._config

    def fetch_and_score(
        self,
        symbol: str,
        source: SentimentSource = SentimentSource.ALL,
    ) -> tuple[list[SentimentSignal], float]:
        """Fetch social media data and score sentiment for a symbol.

        Args:
            symbol: Trading symbol.
            source: Data source to query.

        Returns:
            Tuple of (list of sentiment signals, aggregated sentiment score).
        """
        posts = self._fetcher.fetch_sentiment_data(
            symbol=symbol,
            hours=self._config.lookback_hours,
            source=source,
        )

        signals: list[SentimentSignal] = []
        scores: list[float] = []

        for post in posts:
            score = self._scorer.score(post["text"])
            scores.append(score)

            # Determine side based on score
            if score > self._config.buy_threshold:
                side = "long"
            elif score < self._config.sell_threshold:
                side = "short"
            else:
                side = "neutral"

            signals.append(
                SentimentSignal(
                    symbol=symbol,
                    source=SentimentSource(post["source"]),
                    sentiment_score=score,
                    confidence=abs(score),  # Higher absolute score = higher confidence
                    headline=post["text"],
                    timestamp=post["timestamp"],
                    side=side,
                )
            )

        # Calculate aggregated (averaged) sentiment
        agg_score = float(sum(scores)) / len(scores) if scores else 0.0

        return signals, agg_score

    def calculate_smoothed_sentiment(
        self,
        historical_scores: list[float],
    ) -> float:
        """Calculate smoothed sentiment using rolling average.

        Args:
            historical_scores: List of historical sentiment scores.

        Returns:
            Smoothed sentiment score.
        """
        if not historical_scores:
            return 0.0

        window = min(self._config.smoothing_window, len(historical_scores))
        recent = historical_scores[-window:]
        return sum(recent) / len(recent)

    def generate_signal(
        self,
        current_sentiment: float,
        previous_sentiment: float,
    ) -> SignalType:
        """Generate trading signal from sentiment crossover.

        Args:
            current_sentiment: Most recent sentiment score.
            previous_sentiment: Previous sentiment score.

        Returns:
            SignalType.BUY, SignalType.SELL, or SignalType.NEUTRAL.
        """
        # Detect crossover
        if previous_sentiment <= self._config.buy_threshold < current_sentiment:
            return SignalType.BUY
        if previous_sentiment >= self._config.sell_threshold > current_sentiment:
            return SignalType.SELL
        return SignalType.NEUTRAL

    def get_signals_for_symbols(
        self,
        symbols: Optional[list[str]] = None,
    ) -> dict[str, tuple[SignalType, float, list[SentimentSignal]]]:
        """Get trading signals for multiple symbols.

        Args:
            symbols: List of symbols to analyze. Uses config symbols if None.

        Returns:
            Dict mapping symbol -> (signal, sentiment_score, raw_signals).
        """
        target_symbols = symbols or self._config.symbols
        results: dict[str, tuple[SignalType, float, list[SentimentSignal]]] = {}

        for symbol in target_symbols:
            signals, agg_score = self.fetch_and_score(symbol)

            # Update history
            self._sentiment_history.append(agg_score)
            prev_sentiment = (
                self._sentiment_history[-2] if len(self._sentiment_history) > 1 else 0.0
            )

            # Generate signal
            signal = self.generate_signal(agg_score, prev_sentiment)
            results[symbol] = (signal, agg_score, signals)

        return results

    def backtest(
        self,
        symbol: str,
        prices: Sequence[float],
        start_date: Optional[datetime] = None,
    ) -> BacktestResult:
        """Backtest sentiment strategy on historical data.

        Args:
            symbol: Symbol to backtest.
            prices: Historical price series.
            start_date: Optional start date for the backtest.

        Returns:
            BacktestResult with performance metrics.
        """
        # Generate mock historical sentiment for backtesting
        historical_sentiment = self._generate_historical_sentiment(
            len(prices), self._config.symbols.index(symbol) if symbol in self._config.symbols else 0
        )

        # Detect crossovers
        prev_sentiment = 0.0
        signals: list[SignalType] = []

        for score in historical_sentiment:
            signal = self.generate_signal(score, prev_sentiment)
            signals.append(signal)
            prev_sentiment = score

        # Pad signals to match prices length
        while len(signals) < len(prices):
            signals.append(SignalType.NEUTRAL)

        backtester = Backtester(prices, signals)
        return backtester.run()

    def _generate_historical_sentiment(self, length: int, seed: int = 0) -> list[float]:
        """Generate realistic mock historical sentiment data.

        Args:
            length: Number of data points.
            seed: Random seed offset for reproducibility.

        Returns:
            List of sentiment scores.
        """
        rng = random.Random(seed + 42)
        sentiment = 0.0
        scores: list[float] = []

        for _ in range(length):
            # Random walk with mean reversion
            change = rng.gauss(0.0, 0.1)
            # Mean reversion toward 0
            reversion = -sentiment * 0.1
            sentiment = max(-1.0, min(1.0, sentiment + change + reversion))
            scores.append(sentiment)

        return scores

    def calculate_position_size(
        self,
        sentiment_score: float,
        base_size: float = 1.0,
    ) -> float:
        """Calculate position size based on sentiment strength.

        Args:
            sentiment_score: Current sentiment score (-1 to +1).
            base_size: Base position size.

        Returns:
            Position size multiplier (0.5 to 2.0).
        """
        # Scale position size by confidence (absolute sentiment)
        confidence = abs(sentiment_score)
        # Map to 0.5-2.0 range
        multiplier = 0.5 + (confidence * 1.5)
        return min(2.0, max(0.5, multiplier)) * base_size
