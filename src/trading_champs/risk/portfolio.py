"""Portfolio risk management and drawdown tracking."""

from dataclasses import dataclass


@dataclass
class RiskMetrics:
    """Portfolio risk metrics."""

    total_equity: float
    peak_equity: float
    current_drawdown: float
    max_drawdown: float
    drawdown_percent: float
    max_drawdown_percent: float


@dataclass
class Position:
    """Open position information."""

    symbol: str
    entry_price: float
    current_price: float
    quantity: float
    side: str  # "long" or "short"
    unrealized_pnl: float


class DrawdownTracker:
    """Tracks portfolio drawdown over time."""

    def __init__(self, initial_balance: float):
        """Initialize drawdown tracker.

        Args:
            initial_balance: Starting account balance.
        """
        self.initial_balance = initial_balance
        self.peak_equity = initial_balance
        self.max_drawdown = 0.0
        self.max_drawdown_percent = 0.0
        self.equity_history: list[float] = [initial_balance]

    def update(self, current_equity: float) -> RiskMetrics:
        """Update with current equity and calculate metrics.

        Args:
            current_equity: Current total account value.

        Returns:
            RiskMetrics with current drawdown state.
        """
        self.equity_history.append(current_equity)

        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        current_drawdown = self.peak_equity - current_equity
        current_drawdown_pct = (
            (current_drawdown / self.peak_equity * 100) if self.peak_equity > 0 else 0
        )

        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown
            self.max_drawdown_percent = current_drawdown_pct

        return RiskMetrics(
            total_equity=current_equity,
            peak_equity=self.peak_equity,
            current_drawdown=current_drawdown,
            max_drawdown=self.max_drawdown,
            drawdown_percent=current_drawdown_pct,
            max_drawdown_percent=self.max_drawdown_percent,
        )

    def is_within_risk_limits(
        self,
        current_equity: float,
        max_drawdown_percent: float = 20.0,
    ) -> bool:
        """Check if current drawdown is within acceptable limits.

        Args:
            current_equity: Current total account value.
            max_drawdown_percent: Maximum allowed drawdown percentage.

        Returns:
            True if drawdown is within limits.
        """
        metrics = self.update(current_equity)
        return metrics.drawdown_percent <= max_drawdown_percent


class PortfolioRisk:
    """Manages overall portfolio risk limits."""

    def __init__(
        self,
        max_position_size: float = 0.2,
        max_total_exposure: float = 1.0,
        max_drawdown_percent: float = 20.0,
    ):
        """Initialize portfolio risk manager.

        Args:
            max_position_size: Max size per position as fraction of portfolio (0.2 = 20%).
            max_total_exposure: Max total exposure as fraction of portfolio.
            max_drawdown_percent: Max allowed drawdown before reducing positions.
        """
        self.max_position_size = max_position_size
        self.max_total_exposure = max_total_exposure
        self.max_drawdown_percent = max_drawdown_percent
        self.drawdown_tracker = DrawdownTracker(initial_balance=1.0)  # Will be updated

    def can_open_position(
        self,
        position_value: float,
        total_portfolio_value: float,
        current_equity: float,
    ) -> tuple[bool, str]:
        """Check if a new position can be opened.

        Args:
            position_value: Value of the proposed position.
            total_portfolio_value: Total portfolio value.
            current_equity: Current account equity.

        Returns:
            Tuple of (allowed, reason).
        """
        # Check drawdown limit
        if not self.drawdown_tracker.is_within_risk_limits(
            current_equity, self.max_drawdown_percent
        ):
            return False, f"Max drawdown ({self.max_drawdown_percent}%) exceeded"

        # Check position size limit
        position_fraction = position_value / total_portfolio_value
        if position_fraction > self.max_position_size:
            return (
                False,
                f"Position size ({position_fraction:.1%}) "
                f"exceeds max ({self.max_position_size:.1%})",
            )

        # Check total exposure
        total_fraction = position_value / total_portfolio_value
        if total_fraction > self.max_total_exposure:
            return (
                False,
                f"Total exposure ({total_fraction:.1%}) "
                f"exceeds max ({self.max_total_exposure:.1%})",
            )

        return True, "OK"

    def calculate_position_size(
        self,
        account_balance: float,
        risk_per_trade: float,
        entry_price: float,
        stop_loss_price: float,
    ) -> float:
        """Calculate maximum allowed position size.

        Args:
            account_balance: Current account balance.
            risk_per_trade: Risk amount per trade.
            entry_price: Entry price.
            stop_loss_price: Stop loss price.

        Returns:
            Maximum position size in units.
        """
        price_risk = abs(entry_price - stop_loss_price)
        if price_risk == 0:
            return 0

        max_risk_fraction = risk_per_trade / account_balance
        max_position_fraction = min(
            max_risk_fraction,
            self.max_position_size,
        )

        max_position_value = account_balance * max_position_fraction
        return max_position_value / entry_price

    def get_risk_metrics(
        self,
        positions: list[Position],
        cash: float,
    ) -> RiskMetrics:
        """Calculate overall portfolio risk metrics.

        Args:
            positions: List of open positions.
            cash: Cash balance.

        Returns:
            RiskMetrics for the portfolio.
        """
        total_equity = cash + sum(p.unrealized_pnl for p in positions)
        return self.drawdown_tracker.update(total_equity)
