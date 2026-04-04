"""Trading signal generation and backtesting."""

from trading_champs.signals.ceo_twitter_strategy import (
    CEOTwitterConfig,
    CEOTwitterFetcher,
    CEOTwitterScorer,
    CEOTwitterStrategy,
    ExecutiveAccount,
    ExecutiveType,
)
from trading_champs.signals.engine import SignalEngine
from trading_champs.signals.options_flow_strategy import (
    DarkPoolIndicator,
    DarkPoolPrint,
    DeltaImbalance,
    FlowType,
    InstitutionalSignal,
    OptionsFlow,
    OptionsFlowConfig,
    OptionsFlowFetcher,
    OptionsFlowStrategy,
)
from trading_champs.signals.short_squeeze_strategy import (
    CatalyticEvent,
    MomentumFetcher,
    PriceMomentum,
    ShortInterestData,
    ShortInterestFetcher,
    ShortSqueezeConfig,
    ShortSqueezeStrategy,
    SqueezeDetector,
    SqueezePhase,
    SqueezeSignal,
)
from trading_champs.signals.news_nlp_strategy import (
    EventDetector,
    EventType,
    NLPSignal,
    NewsArticle,
    NewsNLPConfig,
    NewsFetcher,
    NewsNLPStrategy,
    SentimentScorer as NLPSentimentScorer,
)
from trading_champs.signals.sentiment import (
    SentimentConfig,
    SentimentScorer,
    SentimentSignal,
    SentimentSource,
    SentimentStrategy,
)
from trading_champs.signals.service import SignalService
from trading_champs.signals.social_trading import SocialTrader, get_follow_signal

__all__ = [
    "SignalService",
    "SignalEngine",
    "SocialTrader",
    "get_follow_signal",
    "SentimentConfig",
    "SentimentScorer",
    "SentimentSignal",
    "SentimentSource",
    "SentimentStrategy",
    "CEOTwitterConfig",
    "CEOTwitterFetcher",
    "CEOTwitterScorer",
    "CEOTwitterStrategy",
    "ExecutiveAccount",
    "ExecutiveType",
    "OptionsFlowConfig",
    "OptionsFlowFetcher",
    "OptionsFlowStrategy",
    "OptionsFlow",
    "DarkPoolPrint",
    "DeltaImbalance",
    "InstitutionalSignal",
    "FlowType",
    "DarkPoolIndicator",
    # Short Squeeze Strategy
    "ShortSqueezeConfig",
    "ShortSqueezeStrategy",
    "ShortInterestFetcher",
    "ShortInterestData",
    "SqueezeDetector",
    "SqueezeSignal",
    "SqueezePhase",
    "CatalyticEvent",
    "MomentumFetcher",
    "PriceMomentum",
    # News NLP Strategy
    "NewsNLPConfig",
    "NewsNLPStrategy",
    "NewsFetcher",
    "NewsArticle",
    "NLPSignal",
    "EventType",
    "EventDetector",
    "NLPSentimentScorer",
]
