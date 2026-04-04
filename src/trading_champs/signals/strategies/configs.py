"""Strategy-specific configuration dataclasses."""

from dataclasses import dataclass

from trading_champs.signals.engine import MAPeriodPreset


@dataclass
class MACrossoverConfig:
    """Config for MACrossoverStrategy."""

    fast_period: int = 20
    slow_period: int = 50
    preset: MAPeriodPreset | None = None


@dataclass
class RSIConfig:
    """Config for RSIStrategy."""

    period: int = 14
    overbought: float = 70.0
    oversold: float = 30.0
    use_dynamic: bool = False
    percentile_low: float = 25.0
    percentile_high: float = 75.0


@dataclass
class MACDConfig:
    """Config for MACDStrategy."""

    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    use_trend_filter: bool = False
    trend_ma_period: int = 200


@dataclass
class BollingerConfig:
    """Config for BollingerStrategy."""

    period: int = 20
    num_std: float = 2.0
    use_rsi_filter: bool = False
    rsi_period: int = 14
    rsi_oversold: float = 30.0
