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
from trading_champs.data.connectors.alpaca_connector import (
    AlpacaConnector,
    AlpacaPaperConnector,
    create_connector,
)
from trading_champs.data.connectors.alpaca_market_data_connector import AlpacaMarketDataConnector
from trading_champs.data.connectors.ccxt_connector import CCXTConnector
from trading_champs.data.connectors.dry_run_connector import DryRunConnector
from trading_champs.data.connectors.yahoo_finance_connector import YahooFinanceConnector
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
    qty: Optional[float]
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
        self._alpaca_market: Optional[AlpacaMarketDataConnector] = None
        self._yahoo: Optional[YahooFinanceConnector] = None
        self._alpaca: Optional["AlpacaConnector | DryRunConnector"] = None
        self._executor: Optional[TradeExecutor] = None

    @property
    def state(self) -> LoopState:
        """Lazily load or create state."""
        if self._state is None:
            self._state = self.state_store.load()
        return self._state

    def _ensure_data_connector(
        self,
    ) -> "CCXTConnector | AlpacaMarketDataConnector | YahooFinanceConnector":
        """Lazily create and connect the data connector based on config.data_connector.

        Fallback chain when primary connector fails:
          alpaca_market → yahoo_finance → ccxt (Binance, crypto only)

        Yahoo Finance is the free fallback for stocks. CCXT/Binance only works
        for crypto symbols.
        """
        if self.config.data_connector == "alpaca_market":
            if self._alpaca_market is None:
                self._alpaca_market = AlpacaMarketDataConnector()
            if not self._alpaca_market.is_connected():
                try:
                    self._alpaca_market.connect()
                except ConnectionError as e:
                    logger.warning(
                        "Alpaca Market Data failed (%s), "
                        "falling back to Yahoo Finance for equity data",
                        e,
                    )
                    self.config.data_connector = "yahoo_finance"
                    self._alpaca_market = None
            if self._alpaca_market is not None and self._alpaca_market.is_connected():
                logger.info("[_ensure_data_connector] Using AlpacaMarketDataConnector")
                return self._alpaca_market
            # Fall through to Yahoo Finance

        if self.config.data_connector == "yahoo_finance":
            if self._yahoo is None:
                self._yahoo = YahooFinanceConnector()
            if not self._yahoo.is_connected():
                try:
                    self._yahoo.connect()
                except ConnectionError as e:
                    logger.warning(
                        "Yahoo Finance failed (%s), falling back to CCXT/%s",
                        e,
                        self.config.exchange,
                    )
                    self.config.data_connector = "ccxt"
                    self._yahoo = None
            if self._yahoo is not None and self._yahoo.is_connected():
                logger.info("[_ensure_data_connector] Using YahooFinanceConnector")
                return self._yahoo
            # Fall through to CCXT

        if self._ccxt is None:
            self._ccxt = CCXTConnector({"exchange": self.config.exchange})
            self._ccxt.connect()
        logger.info(f"[_ensure_data_connector] Using CCXTConnector/{self.config.exchange}")
        return self._ccxt

    def _ensure_alpaca(self) -> "AlpacaPaperConnector | DryRunConnector":
        """Lazily create and connect the trading connector based on mode."""
        if self._alpaca is None:
            self._alpaca = create_connector(self.config.mode)
            logger.info(
                f"[_ensure_alpaca] Created connector: {self._alpaca.name} (mode={self.config.mode})"
            )
            if self.config.mode != "dry_run":
                self._alpaca.connect()
            self._executor = TradeExecutor(self._alpaca)
        return self._alpaca

    @property
    def executor(self) -> TradeExecutor:
        """Get the trade executor (creates Alpaca connector if needed)."""
        self._ensure_alpaca()
        assert self._executor is not None
        return self._executor

    def _fetch_prices(self, symbol: str) -> tuple[list[float], float, datetime]:
        """Fetch recent close prices for a symbol.

        Returns:
            Tuple of (prices list, latest close price, latest bar timestamp).
        """
        last_connector_name: str | None = None
        for attempt in range(3):
            connector = self._ensure_data_connector()
            last_connector_name = connector.name
            try:
                bars = connector.fetch_ohlcv(
                    symbol,
                    timeframe=self.config.timeframe,
                    limit=self.config.lookback_bars,
                )
                if bars:
                    closes = [bar.close for bar in bars]
                    # Alpaca returns very few bars for US stocks (market hours only).
                    # Treat < 10 bars as insufficient — force fallback to next connector
                    # so stocks get full history from Yahoo Finance.
                    if len(closes) >= 10:
                        return closes, closes[-1], bars[-1].timestamp
                    logger.warning(
                        "[_fetch_prices] %s returned only %d bars for %s, "
                        "forcing fallback (need >= 10 for reliable signals)",
                        connector.name,
                        len(closes),
                        symbol,
                    )
                # No bars or insufficient — try next connector
            except ConnectionError as e:
                logger.warning(
                    "[_fetch_prices] %s failed for %s (%s), trying next connector",
                    connector.name,
                    symbol,
                    e,
                )
            except Exception as e:
                logger.error(
                    "[_fetch_prices] %s error for %s: %s",
                    connector.name,
                    symbol,
                    e,
                )
                break  # Non-connection errors shouldn't retry same connector

            # Force connector change for next attempt
            self._force_connector_fallback()

        raise ValueError(f"No price data for {symbol} (tried {last_connector_name})")

    def _force_connector_fallback(self) -> None:
        """Force the data connector to fall to the next option in the chain.

        Called when the current connector fails so the next _ensure_data_connector
        call creates a fresh connector instead of reusing the cached one.
        """
        current = self.config.data_connector
        if current == "alpaca_market":
            self.config.data_connector = "yahoo_finance"
            self._alpaca_market = None
        elif current == "yahoo_finance":
            self.config.data_connector = "ccxt"
            self._yahoo = None
        else:
            self._ccxt = None  # Force recreate on next call

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

    def iterate(
        self,
        idempotency_key: str | None = None,
        drift_detector: Any = None,
        skip_execution: bool = False,
    ) -> dict[str, Any]:
        """Run one iteration of the trading loop.

        Args:
            idempotency_key: Optional idempotency key to prevent duplicate
                             executions. If provided, concurrent calls with the
                             same key will return 409.
            drift_detector: Optional DriftDetector to record dry_run fills for
                            drift detection (used in dry_run mode only).
            skip_execution: If True, generate signals but do NOT execute any
                            trades. Used for conviction aggregation where we
                            collect signals from all strategies before trading.

        Returns:
            Dict describing what happened this iteration.
        """
        import os

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        lock_ttl = int(os.environ.get("ITERATE_LOCK_TTL_SECONDS", "60"))

        from trading_champs.core.loop_state import RedisDistributedLock

        lock = RedisDistributedLock(redis_url=redis_url, lock_ttl_seconds=lock_ttl)

        if not lock.acquire(idempotency_key):
            logger.warning(
                f"Iterate SKIPPED — another instance running. idempotency_key={idempotency_key}"
            )
            _metrics.iterate_cycle_total.labels(status="skipped").inc()
            return {
                "status": "skipped",
                "reason": "another_instance_running",
                "idempotency_key": idempotency_key,
                "timestamp": datetime.now().isoformat(),
            }

        try:
            return self._iterate_impl(drift_detector=drift_detector, skip_execution=skip_execution)
        finally:
            lock.release(idempotency_key)

    def _iterate_impl(
        self, drift_detector: Any = None, skip_execution: bool = False
    ) -> dict[str, Any]:
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
                prices, latest_price, latest_bar_timestamp = self._fetch_prices(symbol)
                logger.info(
                    f"[_iterate_impl] {self.config.strategy}: fetched {len(prices)} bars "
                    f"for {symbol} @ {latest_price}"
                )
                result["signals"].append(
                    {
                        "symbol": symbol,
                        "price": latest_price,
                        "bar_timestamp": latest_bar_timestamp.isoformat(),
                    }
                )

                # 2. Generate signal
                signal = self._generate_signal(prices)
                signal_str = signal.value if isinstance(signal, SignalType) else str(signal)
                logger.info(f"[_iterate_impl] {self.config.strategy}/{symbol}: signal={signal_str}")
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
                            limit_price=latest_price,
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
                    if skip_execution:
                        result["actions"].append(
                            {
                                "type": "enter_candidate",
                                "symbol": symbol,
                                "signal": signal_str,
                                "price": latest_price,
                                "reason": "skipping_execution_for_conviction",
                            }
                        )
                        self.state.record_iteration(symbol, signal_str, "candidate:conviction")
                    else:
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
                                limit_price=latest_price,
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
                    if action.qty is None:
                        raise ValueError(f"open action requires qty for {action.symbol}")
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
