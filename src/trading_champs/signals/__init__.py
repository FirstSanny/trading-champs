"""Trading signal generation and backtesting."""

from trading_champs.signals.engine import SignalEngine
from trading_champs.signals.service import SignalService
from trading_champs.signals.social_trading import SocialTrader, get_follow_signal

__all__ = ["SignalService", "SignalEngine", "SocialTrader", "get_follow_signal"]
