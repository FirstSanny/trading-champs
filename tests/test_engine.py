"""Tests for trading engine"""

from trading_champs.core.engine import TradingEngine


class TestTradingEngine:
    """Test suite for TradingEngine"""

    def test_engine_initialization(self):
        """Test engine can be initialized"""
        engine = TradingEngine()
        assert engine is not None
        assert engine.running is False

    def test_engine_start(self):
        """Test engine can be started"""
        engine = TradingEngine()
        engine.start()
        assert engine.running is True

    def test_engine_stop(self):
        """Test engine can be stopped"""
        engine = TradingEngine()
        engine.start()
        engine.stop()
        assert engine.running is False

    def test_execute_order(self):
        """Test order execution"""
        engine = TradingEngine()
        result = engine.execute_order("BTC/USD", "buy", 0.1)
        assert result["symbol"] == "BTC/USD"
        assert result["side"] == "buy"
        assert result["quantity"] == 0.1
        assert result["status"] == "filled"
