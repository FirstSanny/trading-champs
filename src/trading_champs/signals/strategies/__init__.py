"""Strategy registry and exports."""

from trading_champs.signals.strategies.base import AbstractStrategy
from trading_champs.signals.strategies.bollinger import BollingerRSIStrategy, BollingerStrategy
from trading_champs.signals.strategies.data_adapters import (
    CEOTwitterAdapter,
    NewsNLPAdapter,
    OptionsFlowAdapter,
    SentimentAdapter,
    ShortSqueezeAdapter,
    SocialTradingAdapter,
)
from trading_champs.signals.strategies.data_protocol import DataDrivenStrategy, StrategyMetadata
from trading_champs.signals.strategies.data_registry import DATA_STRATEGY_REGISTRY
from trading_champs.signals.strategies.data_service import DataSignalResult, DataStrategyService
from trading_champs.signals.strategies.ma_crossover import (
    MACrossoverPresetStrategy,
    MACrossoverStrategy,
)
from trading_champs.signals.strategies.macd import MACDStrategy, MACDTrendFilterStrategy
from trading_champs.signals.strategies.protocol import Strategy
from trading_champs.signals.strategies.rsi import RSIDynamicThresholdStrategy, RSIStrategy

# Canonical string-based registry for SignalService.get_signals(str)
STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "ma_crossover": MACrossoverStrategy,
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "ma_crossover_preset": MACrossoverPresetStrategy,
    "macd_trend": MACDTrendFilterStrategy,
    "rsi_dynamic": RSIDynamicThresholdStrategy,
    "bollinger": BollingerStrategy,
    "bollinger_rsi": BollingerRSIStrategy,
}


def create_orchestrator_configs(
    strategy_loop_config_cls,
    defaults: dict | list[dict] | None = None,
) -> list:
    """Create one StrategyLoopConfig per registered strategy, all starting at dry_run.

    Args:
        strategy_loop_config_cls: The StrategyLoopConfig dataclass from core.orchestrator.
        defaults: Optional field overrides. Can be:
            - A single dict: applied to every config (e.g. {'timeframe': '4h'}).
            - A list of dicts: one per registry key, in order (e.g. for per-strategy symbols).

    Returns:
        List of StrategyLoopConfig instances, one per STRATEGY_REGISTRY entry.
    """
    registry_keys = list(STRATEGY_REGISTRY.keys())

    # Normalize defaults to list form
    if defaults is None:
        per_strategy: list[dict] = [{} for _ in registry_keys]
    elif isinstance(defaults, dict):
        per_strategy = [defaults for _ in registry_keys]
    else:
        per_strategy = list(defaults)

    # Pad with empty dicts if list is shorter than registry keys
    while len(per_strategy) < len(registry_keys):
        per_strategy.append({})

    return [
        strategy_loop_config_cls(
            strategy_id=key,
            strategy_name=key.replace("_", " ").title(),
            strategy=key,
            stage="dry_run",
            **per_strategy[i],
        )
        for i, key in enumerate(registry_keys)
    ]


__all__ = [
    # Price-series strategy protocol and registry
    "AbstractStrategy",
    "Strategy",
    "STRATEGY_REGISTRY",
    "create_orchestrator_configs",
    # Price-series strategies
    "MACrossoverStrategy",
    "MACrossoverPresetStrategy",
    "RSIStrategy",
    "RSIDynamicThresholdStrategy",
    "MACDStrategy",
    "MACDTrendFilterStrategy",
    "BollingerStrategy",
    "BollingerRSIStrategy",
    # Data-driven strategy protocol and registry
    "DataDrivenStrategy",
    "StrategyMetadata",
    "DATA_STRATEGY_REGISTRY",
    "DataSignalResult",
    "DataStrategyService",
    # Data-driven strategy adapters
    "CEOTwitterAdapter",
    "NewsNLPAdapter",
    "OptionsFlowAdapter",
    "ShortSqueezeAdapter",
    "SentimentAdapter",
    "SocialTradingAdapter",
]
