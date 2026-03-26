"""Tests for risk management module."""

import pytest

from trading_champs.risk.portfolio import (
    DrawdownTracker,
    PortfolioRisk,
    Position,
    RiskMetrics,
)
from trading_champs.risk.position_sizer import FixedSize, KellyCriterion, PercentRisk
from trading_champs.risk.stop_loss import (
    ATRStopLoss,
    FixedStopLoss,
    FixedTakeProfit,
    TrailingStopLoss,
)


class TestPositionSizers:
    """Tests for position sizing strategies."""

    def test_fixed_size(self):
        sizer = FixedSize(units=100)
        result = sizer.calculate(account_balance=10000, entry_price=50)

        assert result.units == 100
        assert result.dollar_risk == 0.0

    def test_percent_risk_basic(self):
        sizer = PercentRisk(risk_percent=2.0)
        result = sizer.calculate(
            account_balance=10000,
            entry_price=50,
            stop_loss_price=49,
        )

        # $200 risk (2% of 10000) / $1 price risk = 200 units
        assert result.units == 200
        assert result.dollar_risk == 200.0
        assert result.risk_percent == 2.0

    def test_percent_risk_requires_stop_loss(self):
        sizer = PercentRisk(risk_percent=2.0)
        with pytest.raises(ValueError):
            sizer.calculate(account_balance=10000, entry_price=50)

    def test_kelly_criterion_basic(self):
        sizer = KellyCriterion(win_rate=0.6, avg_win=100, avg_loss=50)
        result = sizer.calculate(
            account_balance=10000,
            entry_price=50,
            stop_loss_price=48,
        )

        assert result.units >= 0
        assert result.risk_percent >= 0


class TestStopLoss:
    """Tests for stop loss strategies."""

    def test_fixed_stop_loss(self):
        stop = FixedStopLoss(percent=2.0)
        result = stop.calculate(entry_price=100, high=102, low=98)

        assert result.price == 98.0
        assert "2.0%" in result.reason

    def test_fixed_take_profit(self):
        tp = FixedTakeProfit(percent=4.0)
        result = tp.calculate(entry_price=100)

        assert result.price == 104.0
        assert "4.0%" in result.reason

    def test_atr_stop_loss(self):
        stop = ATRStopLoss(atr_periods=14, multiplier=2.0)
        result = stop.calculate(
            entry_price=100,
            high=102,
            low=98,
            atr=2.0,
        )

        assert result.price == 96.0
        assert "atr" in result.reason

    def test_trailing_stop_loss(self):
        stop = TrailingStopLoss(percent=2.0)
        result = stop.calculate(
            entry_price=100,
            high=105,
            low=100,
            highest_since_entry=108,
        )

        # 108 * 0.98 = 105.84
        assert result.price == 105.84
        assert "trailing" in result.reason

    def test_trailing_stop_doesnt_go_below_entry(self):
        stop = TrailingStopLoss(percent=2.0)
        result = stop.calculate(
            entry_price=100,
            high=100,
            low=95,
            highest_since_entry=100,
        )

        # Entry - 2% = 98, but trailing stop should not go below this
        assert result.price >= 98.0


class TestDrawdownTracker:
    """Tests for drawdown tracking."""

    def test_initial_state(self):
        tracker = DrawdownTracker(initial_balance=10000)

        assert tracker.peak_equity == 10000
        assert tracker.max_drawdown == 0.0

    def test_drawdown_calculation(self):
        tracker = DrawdownTracker(initial_balance=10000)

        # Equity drops to 9000
        metrics = tracker.update(9000)

        assert metrics.current_drawdown == 1000
        assert metrics.drawdown_percent == 10.0
        assert metrics.max_drawdown_percent == 10.0

    def test_peak_equity_tracking(self):
        tracker = DrawdownTracker(initial_balance=10000)

        tracker.update(11000)
        tracker.update(10500)
        tracker.update(10800)

        assert tracker.peak_equity == 11000

    def test_max_drawdown_tracking(self):
        tracker = DrawdownTracker(initial_balance=10000)

        tracker.update(9000)  # DD = 10%
        tracker.update(9500)  # DD = 5%
        tracker.update(8500)  # DD = 15%

        assert tracker.max_drawdown_percent == 15.0

    def test_is_within_risk_limits(self):
        tracker = DrawdownTracker(initial_balance=10000)

        tracker.update(9000)  # 10% DD

        assert tracker.is_within_risk_limits(9000, max_drawdown_percent=15.0) is True
        assert tracker.is_within_risk_limits(9000, max_drawdown_percent=5.0) is False


class TestPortfolioRisk:
    """Tests for portfolio risk management."""

    def test_can_open_position_allowed(self):
        risk = PortfolioRisk(
            max_position_size=0.2,
            max_total_exposure=1.0,
            max_drawdown_percent=20.0,
        )
        risk.drawdown_tracker = DrawdownTracker(initial_balance=10000)

        allowed, reason = risk.can_open_position(
            position_value=1000,
            total_portfolio_value=10000,
            current_equity=10000,
        )

        assert allowed is True
        assert reason == "OK"

    def test_can_open_position_exceeds_size(self):
        risk = PortfolioRisk(
            max_position_size=0.1,
            max_total_exposure=1.0,
            max_drawdown_percent=20.0,
        )
        risk.drawdown_tracker = DrawdownTracker(initial_balance=10000)

        allowed, reason = risk.can_open_position(
            position_value=2000,
            total_portfolio_value=10000,
            current_equity=10000,
        )

        assert allowed is False
        assert "exceeds max" in reason

    def test_can_open_position_exceeds_drawdown(self):
        risk = PortfolioRisk(
            max_position_size=0.2,
            max_total_exposure=1.0,
            max_drawdown_percent=10.0,
        )
        risk.drawdown_tracker = DrawdownTracker(initial_balance=10000)
        risk.drawdown_tracker.update(8500)  # 15% DD

        allowed, reason = risk.can_open_position(
            position_value=1000,
            total_portfolio_value=10000,
            current_equity=8500,
        )

        assert allowed is False
        assert "drawdown" in reason.lower()

    def test_calculate_position_size(self):
        risk = PortfolioRisk(max_position_size=0.2)

        size = risk.calculate_position_size(
            account_balance=10000,
            risk_per_trade=100,
            entry_price=50,
            stop_loss_price=49,
        )

        assert size > 0
        # $100 risk / $1 price risk = 100 units max
        # But limited to 20% of $10000 = $2000 / $50 = 40 units
        assert size <= 40

    def test_get_risk_metrics(self):
        risk = PortfolioRisk()
        risk.drawdown_tracker = DrawdownTracker(initial_balance=10000)

        positions = [
            Position(
                symbol="AAPL",
                entry_price=150,
                current_price=155,
                quantity=10,
                side="long",
                unrealized_pnl=50,
            )
        ]

        metrics = risk.get_risk_metrics(positions=positions, cash=9950)

        assert metrics.total_equity == 10000
        assert isinstance(metrics, RiskMetrics)
