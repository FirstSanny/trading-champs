"""Tests for P&L tracking module."""

from datetime import datetime, timedelta

from trading_champs.pl.dashboard import DashboardData, DashboardProvider
from trading_champs.pl.metrics import MetricsCalculator
from trading_champs.pl.tracker import PnLTracker, Trade, TradeLog, TradeSide


class TestTradeLog:
    """Tests for trade logging."""

    def test_add_trade(self):
        log = TradeLog()
        trade = Trade(
            id="test_1",
            symbol="AAPL",
            side=TradeSide.LONG,
            entry_price=150.0,
            exit_price=None,
            quantity=10,
            entry_time=datetime.now(),
            exit_time=None,
            pnl=None,
            pnl_percent=None,
        )
        log.add_trade(trade)

        assert len(log.trades) == 1
        assert log.get_open_trades() == [trade]
        assert log.get_closed_trades() == []

    def test_get_closed_trades(self):
        log = TradeLog()
        trade = Trade(
            id="test_1",
            symbol="AAPL",
            side=TradeSide.LONG,
            entry_price=150.0,
            exit_price=155.0,
            quantity=10,
            entry_time=datetime.now(),
            exit_time=datetime.now(),
            pnl=50.0,
            pnl_percent=3.33,
        )
        log.add_trade(trade)

        assert len(log.get_closed_trades()) == 1
        assert len(log.get_open_trades()) == 0

    def test_get_trades_by_symbol(self):
        log = TradeLog()
        for i, symbol in enumerate(["AAPL", "GOOG", "AAPL", "MSFT"]):
            trade = Trade(
                id=f"test_{i}",
                symbol=symbol,
                side=TradeSide.LONG,
                entry_price=150.0,
                exit_price=None,
                quantity=10,
                entry_time=datetime.now(),
                exit_time=None,
                pnl=None,
                pnl_percent=None,
            )
            log.add_trade(trade)

        aapl_trades = log.get_trades_by_symbol("AAPL")
        assert len(aapl_trades) == 2


class TestPnLTracker:
    """Tests for P&L tracking."""

    def test_open_trade(self):
        tracker = PnLTracker(initial_balance=10000)
        trade = tracker.open_trade(
            symbol="AAPL",
            side=TradeSide.LONG,
            entry_price=150.0,
            quantity=10,
        )

        assert trade.symbol == "AAPL"
        assert trade.side == TradeSide.LONG
        assert trade.entry_price == 150.0
        assert trade.quantity == 10
        assert trade.exit_price is None

    def test_close_trade(self):
        tracker = PnLTracker(initial_balance=10000)
        trade = tracker.open_trade(
            symbol="AAPL",
            side=TradeSide.LONG,
            entry_price=150.0,
            quantity=10,
        )

        closed = tracker.close_trade(trade.id, exit_price=155.0)

        assert closed is not None
        assert closed.exit_price == 155.0
        assert closed.pnl is not None
        assert closed.pnl == 50.0  # (155 - 150) * 10

    def test_short_trade_pnl(self):
        tracker = PnLTracker(initial_balance=10000)
        trade = tracker.open_trade(
            symbol="AAPL",
            side=TradeSide.SHORT,
            entry_price=150.0,
            quantity=10,
        )

        closed = tracker.close_trade(trade.id, exit_price=145.0)

        assert closed.pnl == 50.0  # (150 - 145) * 10

    def test_win_rate(self):
        tracker = PnLTracker(initial_balance=10000)

        # Open and close a winning trade
        t1 = tracker.open_trade("AAPL", TradeSide.LONG, 100.0, 10)
        tracker.close_trade(t1.id, 110.0)

        # Open and close a losing trade
        t2 = tracker.open_trade("GOOG", TradeSide.LONG, 100.0, 10)
        tracker.close_trade(t2.id, 90.0)

        assert tracker.get_win_rate() == 0.5

    def test_get_current_balance(self):
        tracker = PnLTracker(initial_balance=10000)

        t1 = tracker.open_trade("AAPL", TradeSide.LONG, 100.0, 10)
        tracker.close_trade(t1.id, 110.0)

        # Balance should be 10000 + 100 (profit)
        assert tracker.get_current_balance() == 10100

    def test_get_daily_pnl(self):
        tracker = PnLTracker(initial_balance=10000)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        trade = tracker.open_trade("AAPL", TradeSide.LONG, 100.0, 10, entry_time=today)
        tracker.close_trade(trade.id, 110.0, exit_time=today + timedelta(hours=2))

        daily = tracker.get_daily_pnl(today)

        assert daily.trade_count == 1
        assert daily.win_count == 1
        assert daily.realized_pnl == 100.0


class TestMetricsCalculator:
    """Tests for performance metrics."""

    def test_calculate_metrics(self):
        tracker = PnLTracker(initial_balance=10000)

        t1 = tracker.open_trade("AAPL", TradeSide.LONG, 100.0, 10)
        tracker.close_trade(t1.id, 110.0)

        t2 = tracker.open_trade("GOOG", TradeSide.LONG, 100.0, 10)
        tracker.close_trade(t2.id, 90.0)

        calc = MetricsCalculator(tracker)
        metrics = calc.calculate()

        assert metrics.num_trades == 2
        assert metrics.num_wins == 1
        assert metrics.num_losses == 1
        assert metrics.win_rate == 0.5
        assert metrics.total_return == 0.0  # 100 - 100

    def test_sharpe_ratio_with_no_trades(self):
        tracker = PnLTracker(initial_balance=10000)
        calc = MetricsCalculator(tracker)
        metrics = calc.calculate()

        assert metrics.sharpe_ratio == 0.0


class TestDashboardProvider:
    """Tests for dashboard data provider."""

    def test_get_dashboard_data(self):
        tracker = PnLTracker(initial_balance=10000)

        t1 = tracker.open_trade("AAPL", TradeSide.LONG, 100.0, 10)
        tracker.close_trade(t1.id, 110.0)

        provider = DashboardProvider(tracker)
        data = provider.get_dashboard_data(days=7)

        assert isinstance(data, DashboardData)
        assert data.initial_balance == 10000
        assert data.total_realized_pnl == 100.0
        assert len(data.recent_trades) == 1

    def test_get_equity_curve(self):
        tracker = PnLTracker(initial_balance=10000)

        t1 = tracker.open_trade("AAPL", TradeSide.LONG, 100.0, 10)
        tracker.close_trade(t1.id, 110.0)

        provider = DashboardProvider(tracker)
        curve = provider.get_equity_curve(days=7)

        assert len(curve) == 7
        assert curve[0]["equity"] == 10000  # Day 1

    def test_open_positions_in_dashboard(self):
        tracker = PnLTracker(initial_balance=10000)

        tracker.open_trade("AAPL", TradeSide.LONG, 100.0, 10)

        provider = DashboardProvider(tracker)
        data = provider.get_dashboard_data()

        assert len(data.open_positions) == 1
        assert data.open_positions[0]["symbol"] == "AAPL"
