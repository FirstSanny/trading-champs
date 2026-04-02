"""Automated trading loop that orchestrates signals, risk management, and execution."""

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Optional

from trading_champs.core import metrics as _metrics
from trading_champs.core.executor import ExecResult, ExecStatus, TradeExecutor
from trading_champs.core.loop_state import LoopConfig, LoopState, LoopStateStore
from trading_champs.data.connectors.alpaca_connector import AlpacaPaperConnector
from trading_champs.data.connectors.ccxt_connector import CCXTConnector
from trading_champs.pl.tracker import PnLTracker
from trading_champs.risk.position_sizer import PercentRisk
from trading_champs.risk.stop_loss import FixedStopLoss
from trading_champs.signals.detectors.crossover import SignalType
from trading_champs.signals.engine import SignalConfig, SignalEngine

logger = logging.getLogger(__name__)


@dataclass
class _Action:
    """Action to be executed with retry support."""

    action_type: Literal["open", "close"]
    symbol: str
    qty: float
    tracker_trade_id: Optional[str] = None
    strategy: str = "default"
    order_type: str = "market"
    limit_price: Optional[float] = None


class TradingLoop:
    """Automated trading loop.

    Runs one iteration of: fetch data → generate signals → evaluate risk →
    execute trades → log results. State is persisted across invocations
    so this works with serverless (Vercel Cron) polling.
    """

    def __init__(
        self,
        config: LoopConfig,
        tracker: PnLTracker,
        state_store: Optional[LoopStateStore] = None,
    ):
        """Initialize trading loop.

        Args:
            config: Loop configuration (symbols, strategy, etc.).
            tracker: PnLTracker for trade logging.
            state_store: Optional state store (creates default if None).
        """
        self.config = config
        self.tracker = tracker
        self.state_store = state_store or LoopStateStore()
        self._state: Optional[LoopState] = None

        # Initialize connectors lazily
        self._ccxt: Optional[CCXTConnector] = None
        self._alpaca: Optional[AlpacaPaperConnector] = None
        self._executor: Optional[TradeExecutor] = None

    @property
    def state(self) -> LoopState:
        """Lazily load or create state."""
        if self._state is None:
            self._state = self.state_store.load()
        return self._state

    def _ensure_data_connector(self) -> CCXTConnector:
        """Lazily create and connect CCXT data connector."""
        if self._ccxt is None:
            self._ccxt = CCXTConnector({"exchange": self.config.exchange})
            self._ccxt.connect()
        return self._ccxt

    def _ensure_alpaca(self) -> AlpacaPaperConnector:
        """Lazily create and connect Alpaca trading connector."""
        if self._alpaca is None:
            self._alpaca = AlpacaPaperConnector(mode=self.config.mode)
            self._alpaca.connect()
            self._executor = TradeExecutor(self._alpaca)
        return self._alpaca

    @property
    def executor(self) -> TradeExecutor:
        """Get the trade executor (creates Alpaca connector if needed)."""
        self._ensure_alpaca()
        assert self._executor is not None
        return self._executor

    def _fetch_prices(self, symbol: str) -> tuple[list[float], float]:
        """Fetch recent close prices for a symbol.

        Returns:
            Tuple of (prices list, latest close price).
        """
        ccxt = self._ensure_data_connector()
        bars = ccxt.fetch_ohlcv(
            symbol,
            timeframe=self.config.timeframe,
            limit=self.config.lookback_bars,
        )
        if not bars:
            raise ValueError(f"No price data for {symbol}")

        closes = [bar.close for bar in bars]
        latest_close = closes[-1]
        return closes, latest_close

    def _generate_signal(self, prices: list[float]) -> SignalType:
        """Generate trading signal from price data.

        Args:
            prices: List of historical close prices.

        Returns:
            SignalType: BUY, SELL, or NEUTRAL.
        """
        signal_config = SignalConfig(
            fast_ma_period=self.config.fast_ma_period,
            slow_ma_period=self.config.slow_ma_period,
            rsi_period=14,
            rsi_oversold=30.0,
            rsi_overbought=70.0,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
        )
        engine = SignalEngine(prices, signal_config)

        strategy = self.config.strategy
        if strategy == "rsi":
            signals = engine.generate_rsi_signals()
        elif strategy == "macd":
            signals = engine.generate_macd_signals()
        elif strategy == "bollinger":
            signals = engine.generate_bollinger_signals()
        elif strategy == "bollinger_rsi":
            signals = engine.generate_bollinger_signals_with_rsi()
        else:  # ma_crossover
            signals = engine.generate_ma_crossover_signals()

        if not signals:
            return SignalType.NEUTRAL

        return signals[-1]

    def _get_account_balance(self) -> float:
        """Get current account balance from Alpaca."""
        try:
            account = self._ensure_alpaca().get_account()
            return float(account.get("cash", 0))
        except Exception:
            return self.tracker.current_balance

    def _calculate_position_size(self, entry_price: float) -> float:
        """Calculate position size based on risk parameters.

        Args:
            entry_price: Price at which to enter.

        Returns:
            Number of units to buy/sell.
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

    def _should_enter(self, signal: SignalType, symbol: str) -> bool:
        """Determine if we should open a new position.

        Args:
            signal: Current trading signal.
            symbol: Symbol being analyzed.

        Returns:
            True if we should enter a trade.
        """
        if signal != SignalType.BUY:
            return False
        if self.executor.has_position(symbol):
            return False
        # Check max positions
        open_trades = self.tracker.trade_log.get_open_trades()
        if len(open_trades) >= self.config.max_positions:
            return False
        return True

    def _should_exit(
        self, signal: SignalType, symbol: str, latest_price: float
    ) -> tuple[bool, str]:
        """Determine if we should close an existing position.

        Args:
            signal: Current trading signal.
            symbol: Symbol being analyzed.
            latest_price: Current market price.

        Returns:
            Tuple of (should_exit, reason).
        """
        if not self.executor.has_position(symbol):
            return False, ""

        # Exit on sell signal
        if signal == SignalType.SELL:
            return True, "sell_signal"

        # Check stop loss on open trades
        open_trades = [t for t in self.tracker.trade_log.get_open_trades() if t.symbol == symbol]
        if open_trades:
            trade = open_trades[0]
            stop_loss = FixedStopLoss(percent=self.config.stop_loss_percent)
            stop = stop_loss.calculate(trade.entry_price, latest_price, latest_price)
            if trade.side.value == "long" and latest_price <= stop.price:
                return True, f"stop_loss_{stop.reason}"
            elif trade.side.value == "short" and latest_price >= stop.price:
                return True, f"stop_loss_{stop.reason}"

        return False, ""

    def _find_open_trade_for_symbol(self, symbol: str) -> Optional[str]:
        """Find the trade ID for an open position of a symbol."""
        for t in self.tracker.trade_log.get_open_trades():
            if t.symbol == symbol:
                return t.id
        return None

    def iterate(self, idempotency_key: str | None = None) -> dict[str, Any]:
        """Run one iteration of the trading loop.

        Args:
            idempotency_key: Optional idempotency key to prevent duplicate
                             executions. If provided, concurrent calls with the
                             same key will return 409.

        Returns:
            Dict describing what happened this iteration.
        """
        import os

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        lock_ttl = int(os.environ.get("ITERATE_LOCK_TTL_SECONDS", "60"))

        from trading_champs.core.loop_state import RedisDistributedLock

        lock = RedisDistributedLock(redis_url=redis_url, lock_ttl_seconds=lock_ttl)

        if not lock.acquire(idempotency_key):
            _metrics.iterate_cycle_total.labels(status="skipped").inc()
            return {
                "status": "skipped",
                "reason": "another_instance_running",
                "idempotency_key": idempotency_key,
                "timestamp": datetime.now().isoformat(),
            }

        try:
            return self._iterate_impl()
        finally:
            lock.release(idempotency_key)

    def _iterate_impl(self) -> dict[str, Any]:
        """Internal iterate implementation (called after lock acquired)."""
        result: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "iterations": self.state.iterations + 1,
            "actions": [],
            "signals": [],
            "errors": [],
        }

        for symbol in self.config.symbols:
            try:
                # 1. Fetch price data
                prices, latest_price = self._fetch_prices(symbol)
                result["signals"].append({"symbol": symbol, "price": latest_price})

                # 2. Generate signal
                signal = self._generate_signal(prices)
                signal_str = signal.value if isinstance(signal, SignalType) else str(signal)
                result["signals"][-1]["signal"] = signal_str

                # 3. Check if we should exit
                should_exit, exit_reason = self._should_exit(signal, symbol, latest_price)
                if should_exit:
                    trade_id = self._find_open_trade_for_symbol(symbol)
                    exec_result = self._execute_with_retry(
                        _Action(
                            action_type="close",
                            symbol=symbol,
                            qty=None,
                            tracker_trade_id=trade_id,
                        )
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
                    self.state.record_iteration(symbol, signal_str, f"exited:{exit_reason}")
                    continue

                # 4. Check if we should enter
                if self._should_enter(signal, symbol):
                    position_size = self._calculate_position_size(latest_price)
                    if position_size <= 0:
                        result["actions"].append(
                            {
                                "type": "skip",
                                "symbol": symbol,
                                "reason": "position_size_zero",
                                "price": latest_price,
                            }
                        )
                        self.state.record_iteration(symbol, signal_str, "skipped:zero_size")
                        continue

                    exec_result = self._execute_with_retry(
                        _Action(
                            action_type="open",
                            symbol=symbol,
                            qty=position_size,
                            strategy=self.config.strategy,
                        )
                    )
                    result["actions"].append(
                        {
                            "type": "enter",
                            "symbol": symbol,
                            "signal": signal_str,
                            "qty": position_size,
                            "price": latest_price,
                            "status": exec_result.status.value,
                        }
                    )
                    self.state.record_iteration(
                        symbol, signal_str, f"entered:{exec_result.status.value}"
                    )
                else:
                    self.state.record_iteration(symbol, signal_str, "no_action")

            except Exception as e:
                logger.error(f"Iteration error for {symbol}: {e}")
                result["errors"].append({"symbol": symbol, "error": str(e)})
                self.state.record_error(f"{symbol}: {e}")

        # Persist state after iteration
        self.state_store.save(self.state)
        result["state"] = self.state.to_dict()

        # Record metrics
        cycle_status = "error" if result.get("errors") else "success"
        _metrics.iterate_cycle_total.labels(status=cycle_status).inc()

        return result

    def start(self) -> None:
        """Mark the loop as started."""
        self.state.running = True
        self.state_store.save(self.state)
        logger.info("Trading loop started")

    def stop(self) -> None:
        """Mark the loop as stopped."""
        self.state.running = False
        self.state_store.save(self.state)
        logger.info("Trading loop stopped")

    def get_status(self) -> dict:
        """Get current loop status."""
        return {
            "config": {
                "symbols": self.config.symbols,
                "strategy": self.config.strategy,
                "interval_seconds": self.config.interval_seconds,
                "position_size_fraction": self.config.position_size_fraction,
                "max_positions": self.config.max_positions,
                "stop_loss_percent": self.config.stop_loss_percent,
                "take_profit_percent": self.config.take_profit_percent,
                "exchange": self.config.exchange,
                "timeframe": self.config.timeframe,
            },
            "state": self.state.to_dict(),
        }

    def _execute_with_retry(self, action: _Action) -> ExecResult:
        """Execute a trade action with exponential backoff retry on rate limits.

        Args:
            action: The action to execute (open or close).

        Returns:
            ExecResult from the final attempt (after all retries exhausted).
        """
        max_retries = 3
        initial_delay = 1.0
        multiplier = 2.0
        max_delay = 10.0

        for attempt in range(max_retries + 1):
            with _metrics.alpaca_api_duration_seconds.time():
                if action.action_type == "open":
                    result = self.executor.open_long(
                        symbol=action.symbol,
                        qty=action.qty,
                        tracker=self.tracker,
                        strategy=action.strategy,
                        order_type=action.order_type,
                        limit_price=action.limit_price,
                    )
                else:
                    result = self.executor.close_long(
                        symbol=action.symbol,
                        qty=action.qty if action.qty else None,
                        tracker=self.tracker,
                        tracker_trade_id=action.tracker_trade_id,
                        order_type=action.order_type,
                        limit_price=action.limit_price,
                    )

            if result.status != ExecStatus.RETRYABLE:
                return result

            if attempt == max_retries:
                logger.warning(
                    f"Max retries ({max_retries}) exhausted for {action.action_type} "
                    f"{action.symbol}, giving up"
                )
                return result

            # Calculate delay with jitter
            delay = min(initial_delay * (multiplier**attempt), max_delay)
            jitter = random.uniform(-0.5, 0.5)
            sleep_time = max(0, delay + jitter)
            logger.info(
                f"Rate limited on attempt {attempt + 1}, retrying {action.action_type} "
                f"{action.symbol} in {sleep_time:.2f}s"
            )
            time.sleep(sleep_time)

        # Should not reach here, but return last result if we do
        return result
