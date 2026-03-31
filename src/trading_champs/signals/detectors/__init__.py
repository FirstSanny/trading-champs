"""Signal detection algorithms."""

from trading_champs.signals.detectors.bollinger import BollingerBandsDetector
from trading_champs.signals.detectors.crossover import CrossoverDetector, SignalType
from trading_champs.signals.detectors.threshold import ThresholdDetector

__all__ = ["CrossoverDetector", "ThresholdDetector", "SignalType", "BollingerBandsDetector"]
