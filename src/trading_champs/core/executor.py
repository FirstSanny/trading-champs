"""Trade executor that wraps Alpaca paper trading connector."""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from trading_champs.data.connectors.alpaca_connector import AlpacaPaperConnector
from trading_champs.pl.tracker import Trade, TradeSide

logger = logging.getLogger(__name__)


class ExecStatus(Enum):
    """Execution result status."""

    FILLED = "filled"
    REJECTED = "rejected"
    ERROR = "error"
    NO_ACTION = "no_action"


@dataclass
class ExecResult:
    """Result of a trade execution attempt."""

    status: ExecStatus
    order_id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    qty: Optional[float] = None
    filled_price: Optional[float] = None
    message: Optional[str] = None
    trade: Optional[Trade] = None


class TradeExecutor:
    """Executes trades via Alpaca paper trading API.

    Wraps AlpacaPaperConnector and translates between signal-engine
    concepts (symbol, side, quantity) and Alpaca order semantics.
    """

    def __init__(self, connector: AlpacaPaperConnector):
        """Initialize executor with an Alpaca connector.

        Args:
            connector: Connected AlpacaPaperConnector instance.
        """
        self._connector = connector

    @property
    def connector(self) -> AlpacaPaperConnector:
        return self._connector

    def open_long(
        self,
        symbol: str,
        qty: float,
        tracker: Any,  # PnLTracker - avoid circular import
        order_type: str = "market",
        limit_price: Optional[float] = None,
        strategy: str = "default",
    ) -> ExecResult:
        """Open a long position.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSD' for crypto, 'AAPL' for stocks).
            qty: Number of units to buy.
            tracker: PnLTracker instance to log the trade.
            order_type: 'market' or 'limit'.
            limit_price: Required for limit orders.
            strategy: Strategy name for trade tagging.

        Returns:
            ExecResult describing what happened.
        """
        try:
            order = self._connector.submit_order(
                symbol=symbol,
                qty=qty,
                side="buy",
                order_type=order_type,
                limit_price=limit_price,
            )

            # Alpaca returns filled status in response
            filled_price = None
            if order.get("status") == "filled":
                filled_price = float(order.get("filled_avg_price", 0))

            # Log trade in tracker
            trade = tracker.open_trade(
                symbol=symbol,
                side=TradeSide.LONG,
                entry_price=filled_price,
                quantity=qty,
                entry_time=datetime.now(),
                tags=["auto", "loop"],
                strategy=strategy,
            )

            logger.info(
                f"Opened long: {qty} {symbol} @ {filled_price}, "
                f"trade_id={trade.id}, strategy={strategy}"
            )
            return ExecResult(
                status=ExecStatus.FILLED,
                order_id=order.get("id"),
                symbol=symbol,
                side="buy",
                qty=qty,
                filled_price=filled_price,
                message=f"Opened long {symbol}",
                trade=trade,
            )

        except Exception as e:
            logger.error(f"Failed to open long {symbol}: {e}")
            return ExecResult(status=ExecStatus.ERROR, symbol=symbol, message=str(e))

    def close_long(
        self,
        symbol: str,
        qty: Optional[float] = None,
        tracker: Optional[Any] = None,
        tracker_trade_id: Optional[str] = None,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> ExecResult:
        """Close a long position (sell).

        Args:
            symbol: Trading symbol.
            qty: Number of units to sell (None = close full position).
            tracker: PnLTracker for trade logging.
            tracker_trade_id: Specific trade ID to close in tracker.
            order_type: 'market' or 'limit'.
            limit_price: Required for limit orders.

        Returns:
            ExecResult describing what happened.
        """
        try:
            # Get current position qty if not specified
            if qty is None:
                position = self._connector.get_position(symbol)
                if position is None:
                    return ExecResult(
                        status=ExecStatus.NO_ACTION,
                        symbol=symbol,
                        message=f"No open position for {symbol}",
                    )
                qty = float(position.get("qty", 0))

            if qty <= 0:
                return ExecResult(
                    status=ExecStatus.NO_ACTION,
                    symbol=symbol,
                    message=f"Position qty is {qty}",
                )

            order = self._connector.submit_order(
                symbol=symbol,
                qty=qty,
                side="sell",
                order_type=order_type,
                limit_price=limit_price,
            )

            filled_price = None
            if order.get("status") == "filled":
                filled_price = float(order.get("filled_avg_price", 0))

            # Close trade in tracker
            if tracker is not None and tracker_trade_id is not None:
                trade = tracker.close_trade(
                    tracker_trade_id,
                    exit_price=filled_price or 0,
                    exit_time=datetime.now(),
                )
            else:
                trade = None

            logger.info(f"Closed long: {qty} {symbol} @ {filled_price}")
            return ExecResult(
                status=ExecStatus.FILLED,
                order_id=order.get("id"),
                symbol=symbol,
                side="sell",
                qty=qty,
                filled_price=filled_price,
                message=f"Closed long {symbol}",
                trade=trade,
            )

        except Exception as e:
            logger.error(f"Failed to close long {symbol}: {e}")
            return ExecResult(status=ExecStatus.ERROR, symbol=symbol, message=str(e))

    def get_position_qty(self, symbol: str) -> float:
        """Get current position quantity for a symbol."""
        try:
            position = self._connector.get_position(symbol)
            if position is None:
                return 0.0
            return float(position.get("qty", 0))
        except Exception:
            return 0.0

    def has_position(self, symbol: str) -> bool:
        """Check if there is an open position for a symbol."""
        return self.get_position_qty(symbol) != 0
