"""Adapters that wrap old-format strategies into the DataDrivenStrategy protocol.

Each adapter normalizes the strategy's native interface into:
  generate_signal(symbol) -> (SignalType, StrategyMetadata, reason)
"""

from typing import Any

from trading_champs.signals.backtester import SignalType
from trading_champs.signals.ceo_twitter_strategy import CEOTwitterConfig, CEOTwitterStrategy
from trading_champs.signals.news_nlp_strategy import NewsNLPConfig, NewsNLPStrategy
from trading_champs.signals.options_flow_strategy import OptionsFlowConfig, OptionsFlowStrategy
from trading_champs.signals.short_squeeze_strategy import ShortSqueezeConfig, ShortSqueezeStrategy
from trading_champs.signals.social_trading import SocialTrader
from trading_champs.signals.strategies.data_protocol import DataDrivenStrategy, StrategyMetadata


class CEOTwitterAdapter(DataDrivenStrategy):
    """Adapter for CEOTwitterStrategy.

    Wraps generate_signal(handle, symbol) -> (AggregatedSignal, bool, reason)
    into generate_signal(symbol) -> (SignalType, Metadata, reason).
    Uses the first tracked handle for simplicity.
    """

    def __init__(
        self,
        config: CEOTwitterConfig | None = None,
        api_key: str | None = None,
    ) -> None:
        self._strategy = CEOTwitterStrategy(config=config, api_key=api_key)

    @property
    def name(self) -> str:
        return "ceo_twitter"

    def generate_signal(self, symbol: str) -> tuple[SignalType, StrategyMetadata, str]:
        handle = self._strategy._config.tracked_handles[0]
        aggregated, should_trade, reason = self._strategy.generate_signal(
            handle=handle, symbol=symbol
        )
        side_map = {"long": SignalType.BUY, "short": SignalType.SELL}
        signal = side_map.get(aggregated.side, SignalType.NEUTRAL)
        metadata: StrategyMetadata = {
            "confidence": aggregated.total_confidence,
            "sentiment": aggregated.aggregated_sentiment,
            "signal_count": aggregated.signal_count,
            "strength": aggregated.strength,
        }
        return signal, metadata, reason


class NewsNLPAdapter(DataDrivenStrategy):
    """Adapter for NewsNLPStrategy.

    Wraps fetch_and_analyze + aggregate_signals -> (SignalType, float, float)
    into generate_signal(symbol) -> (SignalType, Metadata, reason).
    """

    def __init__(
        self,
        config: NewsNLPConfig | None = None,
        api_keys: dict | None = None,
    ) -> None:
        self._strategy = NewsNLPStrategy(config=config, api_keys=api_keys)

    @property
    def name(self) -> str:
        return "news_nlp"

    def generate_signal(self, symbol: str) -> tuple[SignalType, StrategyMetadata, str]:
        _, signals = self._strategy.fetch_and_analyze(symbol=symbol)
        direction, score, confidence = self._strategy.aggregate_signals(signals)
        metadata: StrategyMetadata = {
            "confidence": confidence,
            "sentiment": score,
            "signal_count": len(signals),
        }
        reason = f"news_nlp:{symbol} score={score:.2f} confidence={confidence:.2f}"
        return direction, metadata, reason


class OptionsFlowAdapter(DataDrivenStrategy):
    """Adapter for OptionsFlowStrategy.

    Wraps generate_signal(symbol) -> (InstitutionalSignal, bool, reason)
    into generate_signal(symbol) -> (SignalType, Metadata, reason).
    """

    def __init__(
        self,
        config: OptionsFlowConfig | None = None,
        api_keys: dict | None = None,
    ) -> None:
        self._strategy = OptionsFlowStrategy(config=config, api_keys=api_keys)

    @property
    def name(self) -> str:
        return "options_flow"

    def generate_signal(self, symbol: str) -> tuple[SignalType, StrategyMetadata, str]:
        signal, should_trade, reason = self._strategy.generate_signal(symbol=symbol)
        side_map = {"long": SignalType.BUY, "short": SignalType.SELL}
        direction = side_map.get(signal.side, SignalType.NEUTRAL)
        metadata: StrategyMetadata = {
            "confidence": signal.confidence,
            "sentiment": signal.combined_sentiment,
            "signal_count": signal.flow_count,
            "strength": signal.strength,
        }
        return direction, metadata, reason


class ShortSqueezeAdapter(DataDrivenStrategy):
    """Adapter for ShortSqueezeStrategy.

    Wraps generate_signal(symbol) -> (SqueezeSignal, bool, reason)
    into generate_signal(symbol) -> (SignalType, Metadata, reason).
    """

    def __init__(
        self,
        config: ShortSqueezeConfig | None = None,
        api_keys: dict | None = None,
    ) -> None:
        self._strategy = ShortSqueezeStrategy(config=config, api_keys=api_keys)

    @property
    def name(self) -> str:
        return "short_squeeze"

    def generate_signal(self, symbol: str) -> tuple[SignalType, StrategyMetadata, str]:
        signal, should_trade, reason = self._strategy.generate_signal(symbol)
        side_map = {"long": SignalType.BUY, "short": SignalType.SELL}
        direction = side_map.get(signal.phase.name, SignalType.NEUTRAL)
        # Map squeeze phases to directions: BUILDUP/SQUEEZE = BUY, PEAK/COOLDOWN = SELL
        phase_direction = {
            "ACCUMULATION": SignalType.NEUTRAL,
            "BUILDUP": SignalType.BUY,
            "SQUEEZE": SignalType.BUY,
            "PEAK": SignalType.SELL,
            "COOLDOWN": SignalType.NEUTRAL,
        }
        direction = phase_direction.get(signal.phase.name, SignalType.NEUTRAL)
        metadata: StrategyMetadata = {
            "confidence": signal.confidence,
            "squeeze_probability": signal.squeeze_probability,
            "urgency": signal.urgency,
            "phase": signal.phase.value,
            "sentiment": signal.short_interest.short_interest_percent,
        }
        return direction, metadata, reason


class SentimentAdapter(DataDrivenStrategy):
    """Adapter for SentimentStrategy.

    Wraps fetch_and_score + generate_signal(crossing detection)
    into generate_signal(symbol) -> (SignalType, Metadata, reason).
    Maintains a rolling previous sentiment for crossover detection.
    """

    def __init__(
        self,
        config: Any | None = None,
        api_keys: dict | None = None,
    ) -> None:
        # Avoid circular import
        from trading_champs.signals.sentiment import SentimentConfig, SentimentStrategy

        cfg = config or SentimentConfig()
        self._strategy = SentimentStrategy(config=cfg, api_keys=api_keys)
        self._prev_sentiment: float = 0.0

    @property
    def name(self) -> str:
        return "sentiment"

    def generate_signal(self, symbol: str) -> tuple[SignalType, StrategyMetadata, str]:
        signals, agg_score = self._strategy.fetch_and_score(symbol)
        self._prev_sentiment = agg_score
        # Get direction from aggregate score
        direction = SignalType.NEUTRAL
        if agg_score > 0.3:
            direction = SignalType.BUY
        elif agg_score < -0.3:
            direction = SignalType.SELL
        metadata: StrategyMetadata = {
            "confidence": abs(agg_score),
            "sentiment": agg_score,
            "signal_count": len(signals),
        }
        reason = f"sentiment:{symbol} score={agg_score:.2f}"
        return direction, metadata, reason


class SocialTradingAdapter(DataDrivenStrategy):
    """Adapter for SocialTrader.

    Wraps SocialTrader.get_signal() -> dict
    into generate_signal(symbol) -> (SignalType, Metadata, reason).
    Uses the first tracked symbol for simplicity.
    """

    def __init__(
        self,
        config: str | None = None,
        api_keys: dict | None = None,
    ) -> None:
        # config is the persona name string
        persona = config or "trumps_son"
        self._trader = SocialTrader(persona=persona)

    @property
    def name(self) -> str:
        return "social_trading"

    def generate_signal(self, symbol: str) -> tuple[SignalType, StrategyMetadata, str]:
        signal_data = self._trader.get_signal(symbol=symbol)
        if signal_data is None:
            return SignalType.NEUTRAL, {}, "no social signal"
        side_map = {"long": SignalType.BUY, "short": SignalType.SELL}
        direction = side_map.get(signal_data["side"].value, SignalType.NEUTRAL)
        metadata: StrategyMetadata = {
            "confidence": signal_data["confidence"],
            "trader": signal_data["trader"],
            "persona": signal_data["persona"],
            "reason": signal_data["reason"],
        }
        reason = f"social:{signal_data['persona']} {signal_data['reason']}"
        return direction, metadata, reason
