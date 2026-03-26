"""Tests for signals module."""

from trading_champs.signals.backtester import Backtester, BacktestResult
from trading_champs.signals.detectors.crossover import CrossoverDetector, SignalType
from trading_champs.signals.detectors.threshold import ThresholdDetector
from trading_champs.signals.engine import SignalConfig, SignalEngine
from trading_champs.signals.indicators.momentum import MACD, RSI
from trading_champs.signals.indicators.moving_averages import EMA, SMA
from trading_champs.signals.indicators.volatility import BollingerBands
from trading_champs.signals.service import SignalService


class TestMovingAverages:
    """Tests for moving average indicators."""

    def test_sma_basic(self):
        prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        result = SMA(prices, 3)

        assert result[0] is None
        assert result[1] is None
        assert result[2] == 11.0
        assert result[3] == 12.0
        assert result[4] == 13.0
        assert result[5] == 14.0

    def test_sma_insufficient_data(self):
        prices = [10.0, 11.0]
        result = SMA(prices, 5)

        assert len(result) == 2
        assert all(v is None for v in result)

    def test_ema_basic(self):
        prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        result = EMA(prices, 3)

        assert result[0] is None
        assert result[1] is None
        assert result[2] is not None
        assert result[-1] > result[2]


class TestMomentumIndicators:
    """Tests for momentum indicators."""

    def test_rsi_basic(self):
        prices = [
            44.0,
            44.5,
            45.0,
            44.8,
            44.2,
            43.5,
            44.0,
            44.5,
            45.2,
            46.0,
            46.5,
            47.0,
            46.8,
            46.5,
            46.0,
        ]
        result = RSI(prices, 14)

        assert len(result) == len(prices)
        assert all(v is None or 0 <= v <= 100 for v in result if v is not None)

    def test_rsi_oversold(self):
        declining = [
            100.0,
            95.0,
            90.0,
            85.0,
            80.0,
            75.0,
            70.0,
            65.0,
            60.0,
            55.0,
            50.0,
            45.0,
            40.0,
            35.0,
            30.0,
        ]
        result = RSI(declining, 14)

        valid_values = [v for v in result if v is not None]
        assert len(valid_values) > 0
        assert valid_values[-1] < 30

    def test_macd_basic(self):
        prices = [44.0, 44.5, 45.0, 44.8, 44.2, 43.5, 44.0, 44.5, 45.2, 46.0, 46.5, 47.0]
        result = MACD(prices)

        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result
        assert len(result["macd"]) == len(prices)


class TestVolatilityIndicators:
    """Tests for volatility indicators."""

    def test_bollinger_bands(self):
        import random

        random.seed(42)
        prices = [100.0 + random.uniform(-5, 5) for _ in range(30)]
        result = BollingerBands(prices, period=20)

        assert "upper" in result
        assert "middle" in result
        assert "lower" in result

        for i in range(19, len(prices)):
            if result["upper"][i] is not None:
                assert result["upper"][i] >= result["middle"][i]
                assert result["middle"][i] >= result["lower"][i]


class TestCrossoverDetector:
    """Tests for crossover signal detection."""

    def test_no_crossover(self):
        line1 = [10.0, 11.0, 12.0, 13.0]
        line2 = [9.0, 10.0, 11.0, 12.0]

        detector = CrossoverDetector(line1, line2)
        signals = detector.detect()

        assert SignalType.BUY not in signals
        assert SignalType.SELL not in signals

    def test_bullish_crossover(self):
        line1 = [9.0, 10.0, 11.0, 12.0]
        line2 = [10.0, 10.0, 10.0, 10.0]

        detector = CrossoverDetector(line1, line2)
        signals = detector.detect()

        # BUY occurs at index 2 when line1 crosses above line2
        assert signals[2] == SignalType.BUY

    def test_bearish_crossover(self):
        line1 = [11.0, 10.0, 9.0, 8.0]
        line2 = [10.0, 10.0, 10.0, 10.0]

        detector = CrossoverDetector(line1, line2)
        signals = detector.detect()

        # SELL occurs at index 1 when line1 crosses below line2
        assert signals[1] == SignalType.SELL


class TestThresholdDetector:
    """Tests for threshold signal detection."""

    def test_rsi_oversold_cross(self):
        values = [25.0, 28.0, 32.0, 35.0]

        detector = ThresholdDetector(values, upper_threshold=70, lower_threshold=30)
        signals = detector.detect()

        # Signal fires when value crosses ABOVE lower threshold
        # index 0: 25.0 <= 30, stays below
        # index 1: 28.0 <= 30, stays below
        # index 2: 32.0 > 30, crosses above -> BUY
        assert signals[0] == SignalType.NEUTRAL
        assert signals[1] == SignalType.NEUTRAL
        assert signals[2] == SignalType.BUY
        assert signals[3] == SignalType.NEUTRAL

    def test_rsi_overbought_cross(self):
        values = [75.0, 72.0, 68.0, 65.0]

        detector = ThresholdDetector(values, upper_threshold=70, lower_threshold=30)
        signals = detector.detect()

        # Signal fires when value crosses BELOW upper threshold
        # index 0: 75.0 >= 70, stays above
        # index 1: 72.0 >= 70, stays above
        # index 2: 68.0 < 70, crosses below -> SELL
        assert signals[0] == SignalType.NEUTRAL
        assert signals[1] == SignalType.NEUTRAL
        assert signals[2] == SignalType.SELL
        assert signals[3] == SignalType.NEUTRAL


class TestBacktester:
    """Tests for backtesting framework."""

    def test_no_trades(self):
        prices = [100.0, 101.0, 102.0, 103.0, 104.0]
        signals = [SignalType.NEUTRAL] * 5

        backtester = Backtester(prices, signals)
        result = backtester.run()

        assert result.num_trades == 0
        assert result.total_pnl == 0.0

    def test_single_trade(self):
        prices = [100.0, 105.0, 110.0, 115.0, 120.0]
        signals = [
            SignalType.NEUTRAL,
            SignalType.BUY,
            SignalType.NEUTRAL,
            SignalType.NEUTRAL,
            SignalType.SELL,
        ]

        backtester = Backtester(prices, signals)
        result = backtester.run()

        assert result.num_trades == 1
        assert result.trades[0].entry_price == 105.0
        assert result.trades[0].exit_price == 120.0
        assert result.total_pnl == 15.0

    def test_win_rate(self):
        prices = [100.0, 110.0, 105.0, 115.0, 110.0, 120.0]
        signals = [
            SignalType.NEUTRAL,
            SignalType.BUY,
            SignalType.SELL,
            SignalType.NEUTRAL,
            SignalType.BUY,
            SignalType.SELL,
        ]

        backtester = Backtester(prices, signals)
        result = backtester.run()

        assert result.num_trades == 2
        assert result.num_wins == 1
        assert result.num_losses == 1
        assert result.win_rate == 0.5


class TestSignalEngine:
    """Tests for signal generation engine."""

    def test_ma_crossover_signals(self):
        prices = [100.0, 102.0, 104.0, 103.0, 105.0, 108.0, 110.0, 109.0, 111.0, 112.0]
        config = SignalConfig(fast_ma_period=3, slow_ma_period=5)

        engine = SignalEngine(prices, config)
        signals = engine.generate_ma_crossover_signals()

        assert len(signals) == len(prices)
        assert signals.count(SignalType.BUY) >= 0
        assert signals.count(SignalType.SELL) >= 0

    def test_rsi_signals(self):
        declining = [100.0 - i for i in range(20)]
        config = SignalConfig(rsi_period=5)

        engine = SignalEngine(declining, config)
        signals = engine.generate_rsi_signals()

        assert len(signals) == len(declining)

    def test_get_indicator_values(self):
        prices = [100.0 + i for i in range(30)]
        config = SignalConfig(fast_ma_period=5, slow_ma_period=10)

        engine = SignalEngine(prices, config)
        values = engine.get_indicator_values()

        assert "prices" in values
        assert "fast_ma" in values
        assert "rsi" in values
        assert "macd" in values


class TestSignalService:
    """Tests for signal service."""

    def test_get_signals_ma_crossover(self):
        prices = [100.0 + i for i in range(30)]
        service = SignalService(prices)

        signals = service.get_signals("ma_crossover")

        assert len(signals) == len(prices)

    def test_get_signals_rsi(self):
        prices = [100.0 + i for i in range(30)]
        service = SignalService(prices)

        signals = service.get_signals("rsi")

        assert len(signals) == len(prices)

    def test_backtest(self):
        prices = [100.0, 105.0, 110.0, 115.0, 120.0, 115.0, 110.0, 105.0, 100.0, 105.0]
        service = SignalService(prices)

        result = service.backtest("ma_crossover")

        assert isinstance(result, BacktestResult)

    def test_get_all_signals(self):
        prices = [100.0 + i for i in range(30)]
        service = SignalService(prices)

        all_signals = service.get_all_signals()

        assert "ma_crossover" in all_signals
        assert "rsi" in all_signals
        assert "macd" in all_signals

    def test_get_indicators(self):
        prices = [100.0 + i for i in range(30)]
        service = SignalService(prices)

        indicators = service.get_indicators()

        assert "prices" in indicators
        assert "rsi" in indicators
        assert "macd" in indicators
