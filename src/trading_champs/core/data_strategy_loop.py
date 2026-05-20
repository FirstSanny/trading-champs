"""Data-driven strategy loop for executing trades from external-data strategies.

Unlike price-based strategies that analyze OHLCV data, data strategies use
external sources (Twitter, news, options flow, social sentiment) to generate
signals. This loop handles their independent execution and stage evaluation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from trading_champs.core.executor import TradeExecutor
from trading_champs.core.loop_state import LoopStateStore
from trading_champs.core.stage_evaluator import DataStrategyMetrics
from trading_champs.pl.tracker import PnLTracker, TradeSide
from trading_champs.risk.position_sizer import PercentRisk
from trading_champs.risk.stop_loss import FixedStopLoss

logger = logging.getLogger(__name__)


class DataStrategyLoop:
    """Automated trading loop for data-driven strategies.

    Runs one iteration of: fetch signal -> evaluate -> execute trades.
    State is persisted across invocations so this works with serverless.
    """

    def __init__(
        self,
        strategy_id: str,
        config: "DataStrategyLoopConfig",
        tracker: PnLTracker,
        data_service: Any,  # DataStrategyService
        state_store: Optional[LoopStateStore] = None,
    ):
        """Initialize data strategy loop.

        Args:
            strategy_id: Strategy identifier (e.g. 'ceo_twitter').
            config: Loop configuration for this data strategy.
            tracker: PnLTracker for trade logging.
            data_service: DataStrategyService for generating signals.
            state_store: Optional state store (creates default if None).
        """
        self.strategy_id = strategy_id
        self.config = config
        self.tracker = tracker
        self.data_service = data_service
        self.state_store = state_store or LoopStateStore()
        self._state_store_path = f".loop_state_{strategy_id}.db"

        # Lazy connectors
        self._alpaca: Optional[Any] = None
        self._executor: Optional[TradeExecutor] = None

    def _ensure_alpaca(self) -> Any:
        """Lazily create and connect the Alpaca trading connector."""
        if self._alpaca is None:
            from trading_champs.data.connectors.alpaca_connector import create_connector

            self._alpaca = create_connector(self.config.mode)
            if self.config.mode != "dry_run":
                self._alpaca.connect()
            self._executor = TradeExecutor(self._alpaca)
            logger.info(
                f"[DataStrategyLoop:{self.strategy_id}] Created connector: "
                f"{self._alpaca.name} (mode={self.config.mode})"
            )
        return self._alpaca

    @property
    def executor(self) -> TradeExecutor:
        """Get the trade executor (creates Alpaca connector if needed)."""
        self._ensure_alpaca()
        assert self._executor is not None
        return self._executor

    def _fetch_entry_price(self, symbol: str) -> float:
        """Fetch current market price for a symbol.

        Args:
            symbol: Trading symbol.

        Returns:
            Current price as a float.
        """
        from trading_champs.data.connectors.alpaca_market_data_connector import (
            AlpacaMarketDataConnector,
        )

        try:
            connector = AlpacaMarketDataConnector()
            connector.connect()
            bars = connector.fetch_ohlcv(symbol, timeframe="1m", limit=1)
            if bars:
                return bars[-1].close
        except Exception as e:
            logger.warning(f"[_fetch_entry_price] Alpaca market data failed for {symbol}: {e}")

        # Fallback to data service's last known price
        try:
            result = self.data_service.get_signal(strategy=self.strategy_id, symbol=symbol)
            confidence = result.metadata.get("price")
            if confidence and isinstance(confidence, (int, float)):
                return float(confidence)
        except Exception:
            pass

        raise ValueError(f"Cannot determine entry price for {symbol}")

    def _get_account_balance(self) -> float:
        """Get current account balance from Alpaca."""
        try:
            connector = self._ensure_alpaca()
            if hasattr(connector, "get_account"):
                account = connector.get_account()
                return float(account.get("cash", 0))
            return self.tracker.current_balance
        except Exception:
            return self.tracker.current_balance

    def _calculate_position_size(self, entry_price: float) -> float:
        """Calculate position size based on risk parameters.

        Args:
            entry_price: Price at which to enter.

        Returns:
            Number of units to buy.
        """
        balance = self._get_account_balance()
        stop_loss = FixedStopLoss(percent=self.config.stop_loss_percent)

        sizer = PercentRisk(risk_percent=self.config.position_size_fraction * 100)
        position = sizer.calculate(
            account_balance=balance,
            entry_price=entry_price,
            stop_loss_price=stop_loss.calculate(entry_price, entry_price, entry_price).price,
        )
        return position.units

    def _should_enter(self, signal: Any, symbol: str) -> bool:
        """Determine if we should open a new position.

        Args:
            signal: Current signal (SignalType or string value).
            symbol: Symbol being analyzed.

        Returns:
            True if we should enter a trade.
        """
        # Must be BUY signal
        signal_str = signal.value if hasattr(signal, "value") else str(signal)
        if signal_str.upper() != "BUY":
            return False

        # No existing position
        if self.executor.has_position(symbol):
            return False

        # Check max positions
        open_trades = self.tracker.trade_log.get_open_trades()
        if len(open_trades) >= self.config.max_positions:
            return False

        return True

    def _should_exit(self, signal: Any, symbol: str, latest_price: float) -> tuple[bool, str]:
        """Determine if we should close an existing position.

        Args:
            signal: Current signal.
            symbol: Symbol being analyzed.
            latest_price: Current market price.

        Returns:
            Tuple of (should_exit, reason).
        """
        if not self.executor.has_position(symbol):
            return False, ""

        signal_str = signal.value if hasattr(signal, "value") else str(signal)

        # Exit on SELL signal
        if signal_str.upper() == "SELL":
            return True, "sell_signal"

        # Check stop loss on open trades
        open_trades = [t for t in self.tracker.trade_log.get_open_trades() if t.symbol == symbol]
        if open_trades:
            trade = open_trades[0]

            # Skip closing positions opened by conviction executor
            # Data strategies only close their own positions
            if getattr(trade, "opened_by", None) == "conviction":
                return False, ""

            stop_loss = FixedStopLoss(percent=self.config.stop_loss_percent)
            stop = stop_loss.calculate(trade.entry_price, latest_price, latest_price)
            if trade.side == TradeSide.LONG and latest_price <= stop.price:
                return True, f"stop_loss_{stop.reason}"
            elif trade.side == TradeSide.SHORT and latest_price >= stop.price:
                return True, f"stop_loss_{stop.reason}"

        return False, ""

    def _find_open_trade_for_symbol(self, symbol: str) -> Optional[str]:
        """Find the trade ID for an open position of a symbol."""
        for t in self.tracker.trade_log.get_open_trades():
            if t.symbol == symbol:
                return t.id
        return None

    def iterate(self) -> dict[str, Any]:
        """Run one iteration of the data strategy loop.

        Returns:
            Dict describing what happened this iteration.
        """
        result: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "strategy_id": self.strategy_id,
            "actions": [],
            "signals": [],
            "errors": [],
        }

        # Load state to check stage
        state = self.state_store.load()
        getattr(state, "stage_entered_at", datetime.utcnow())

        for symbol in self.config.symbols:
            try:
                # Get signal from data service
                signal_result = self.data_service.get_signal(
                    strategy=self.strategy_id, symbol=symbol
                )
                signal = signal_result.signal
                signal_str = signal.value if hasattr(signal, "value") else str(signal)

                logger.info(f"[DataStrategyLoop:{self.strategy_id}] {symbol}: signal={signal_str}")
                result["signals"].append(
                    {
                        "symbol": symbol,
                        "signal": signal_str,
                        "reason": signal_result.reason,
                    }
                )

                # Try to get latest price for exit logic
                latest_price = signal_result.metadata.get("price")
                if latest_price is None:
                    try:
                        latest_price = self._fetch_entry_price(symbol)
                    except Exception:
                        latest_price = 0.0

                # Check if we should exit
                should_exit, exit_reason = self._should_exit(signal, symbol, latest_price)
                if should_exit:
                    trade_id = self._find_open_trade_for_symbol(symbol)
                    exec_result = self.executor.close_long(
                        symbol=symbol,
                        qty=None,
                        tracker=self.tracker,
                        tracker_trade_id=trade_id,
                        order_type="market",
                        limit_price=None,
                    )
                    result["actions"].append(
                        {
                            "type": "exit",
                            "symbol": symbol,
                            "reason": exit_reason,
                            "status": exec_result.status.value,
                            "price": latest_price,
                        }
                    )
                    continue

                # Check if we should enter
                if self._should_enter(signal, symbol):
                    entry_price = self._fetch_entry_price(symbol)
                    position_size = self._calculate_position_size(entry_price)

                    if position_size <= 0:
                        result["actions"].append(
                            {
                                "type": "skip",
                                "symbol": symbol,
                                "reason": "position_size_zero",
                                "price": entry_price,
                            }
                        )
                        continue

                    exec_result = self.executor.open_long(
                        symbol=symbol,
                        qty=position_size,
                        tracker=self.tracker,
                        strategy=self.strategy_id,
                        order_type="market",
                        limit_price=entry_price,
                    )
                    result["actions"].append(
                        {
                            "type": "enter",
                            "symbol": symbol,
                            "signal": signal_str,
                            "qty": position_size,
                            "price": entry_price,
                            "status": exec_result.status.value,
                        }
                    )

            except Exception as e:
                logger.error(f"Iteration error for {symbol}: {e}")
                result["errors"].append({"symbol": symbol, "error": str(e)})

        return result

    def get_signal_metrics(self, stage_entered_at: datetime) -> DataStrategyMetrics:
        """Compute signal-quality metrics for stage evaluation.

        Args:
            stage_entered_at: When the strategy entered the current stage.

        Returns:
            DataStrategyMetrics with signal counts and rates.
        """
        # Load current state to get metrics
        from trading_champs.core.loop_state import LoopStateStore

        state_store = LoopStateStore(path=f".loop_state_{self.strategy_id}.db")
        state = state_store.load()
        current_metrics = getattr(state, "current_metrics", {})

        total_signals = current_metrics.get("total_signals", 0)
        buy_rate = current_metrics.get("buy_rate", 0.0)
        neutral_rate = current_metrics.get("neutral_rate", 0.0)
        consecutive_neutral = min(current_metrics.get("consecutive_neutral", 0), 15)

        return DataStrategyMetrics(
            total_signals=total_signals,
            buy_rate=buy_rate,
            neutral_rate=neutral_rate,
            consecutive_neutral=consecutive_neutral,
            days_in_stage=(datetime.utcnow() - stage_entered_at).days,
        )


@dataclass
class DataStrategyLoopConfig:
    """Configuration for a data strategy loop."""

    strategy_id: str
    symbols: list[str] = field(default_factory=lambda: ["BTC/USDT"])
    position_size_fraction: float = 0.1
    max_positions: int = 3
    stop_loss_percent: float = 2.0
    mode: str = "dry_run"
