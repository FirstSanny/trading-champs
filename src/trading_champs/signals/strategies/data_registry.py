"""Data-driven strategy registry and service."""

from trading_champs.signals.strategies.data_adapters import (
    CEOTwitterAdapter,
    NewsNLPAdapter,
    OptionsFlowAdapter,
    SentimentAdapter,
    ShortSqueezeAdapter,
    SocialTradingAdapter,
)
from trading_champs.signals.strategies.data_protocol import DataDrivenStrategy

# Canonical string-based registry for DataDrivenStrategy instances
DATA_STRATEGY_REGISTRY: dict[str, type[DataDrivenStrategy]] = {
    "ceo_twitter": CEOTwitterAdapter,
    "news_nlp": NewsNLPAdapter,
    "options_flow": OptionsFlowAdapter,
    "short_squeeze": ShortSqueezeAdapter,
    "sentiment": SentimentAdapter,
    "social_trading": SocialTradingAdapter,
}
