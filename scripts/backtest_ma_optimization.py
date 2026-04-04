#!/usr/bin/env python3
"""MA Crossover Parameter Optimization Script.

Fetches historical OHLCV data and runs backtests to find optimal
MA Crossover parameters for the trading strategy.
"""

import sys
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

sys.path.insert(0, "src")

from trading_champs.data.connectors.ccxt_connector import CCXTConnector
from trading_champs.signals.backtester import Backtester, BacktestResult
from trading_champs.signals.detectors.crossover import SignalType
from trading_champs.signals.engine import SignalEngine, SignalConfig, MAPeriodPreset
from trading_champs.signals.indicators.moving_averages import SMA


# Parameter sets to test
PARAM_SETS = [
    ("10/20 (current)", 10, 20),
    ("5/20", 5, 20),
    ("12/26", 12, 26),
    ("20/50", 20, 50),
]

# Trading symbol
SYMBOL = "BTC/USDT"
EXCHANGE = "binance"
TIMEFRAME = "1m"
DAYS_OF_DATA = 30


@dataclass
class OptimizedResult:
    """Enhanced backtest result with additional metrics."""

    name: str
    fast_period: int
    slow_period: int
    trades: list
    total_pnl: float
    total_pnl_pct: float
    win_rate: float
    avg_pnl_per_trade: float
    false_signal_rate: float
    sharpe_ratio: float
    num_trades: int
    num_wins: int
    num_losses: int


def calculate_false_signal_rate(
    prices: Sequence[float], signals: Sequence[SignalType]
) -> float:
    """Calculate the false signal rate.

    A false signal is one where a BUY/SELL signal immediately reverses
    (within 3 bars) without producing a profitable trade.
    """
    if len(signals) < 4:
        return 0.0

    false_count = 0
    total_signals = 0

    for i in range(1, len(signals) - 3):
        current = signals[i]
        if current == SignalType.NEUTRAL:
            continue

        total_signals += 1

        # Check if signal reverses within 3 bars
        reversed_ = False
        for j in range(i + 1, min(i + 4, len(signals))):
            if signals[j] != SignalType.NEUTRAL and signals[j] != current:
                reversed_ = True
                break

        if reversed_:
            # Check if price didn't move favorably
            price_at_signal = prices[i]
            price_after_3 = prices[min(i + 3, len(prices) - 1)]
            pnl_pct = ((price_after_3 - price_at_signal) / price_at_signal) * 100

            # If it's a BUY and price dropped, or SELL and price rose, it's false
            if (current == SignalType.BUY and pnl_pct < 0) or (
                current == SignalType.SELL and pnl_pct > 0
            ):
                false_count += 1

    return false_count / total_signals if total_signals > 0 else 0.0


def calculate_sharpe_ratio(
    prices: Sequence[float], signals: Sequence[SignalType]
) -> float:
    """Calculate Sharpe ratio of strategy returns.

    Returns are calculated as price changes when in position.
    """
    returns: list[float] = []
    in_position = False
    entry_price = 0.0

    for i in range(1, len(prices)):
        signal = signals[i]
        price_change = (prices[i] - prices[i - 1]) / prices[i - 1]

        if signal == SignalType.BUY and not in_position:
            in_position = True
            entry_price = prices[i]
        elif signal == SignalType.SELL and in_position:
            trade_return = (prices[i] - entry_price) / entry_price
            returns.append(trade_return)
            in_position = False

    # Add final return if still in position
    if in_position:
        trade_return = (prices[-1] - entry_price) / entry_price
        returns.append(trade_return)

    if not returns or len(returns) < 2:
        return 0.0

    mean_return = sum(returns) / len(returns)
    std_dev = math.sqrt(
        sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    )

    if std_dev == 0:
        return 0.0

    # Sharpe ratio (not annualized, just for comparison)
    return mean_return / std_dev


def fetch_historical_data(
    connector: CCXTConnector,
    symbol: str,
    timeframe: str,
    days: int,
    max_bars: int = 100000,
) -> list:
    """Fetch historical OHLCV data in chunks to bypass exchange limits.

    Args:
        connector: CCXT connector instance.
        symbol: Trading symbol.
        timeframe: Timeframe (e.g., '1m', '5m').
        days: Number of days of data to fetch.
        max_bars: Maximum number of bars to fetch.

    Returns:
        List of PriceBar objects.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 10)  # Extra buffer for MAs
    current_since = int(start_date.timestamp() * 1000)
    all_bars = []

    print(f"Fetching {days}+ days of {timeframe} data from {EXCHANGE}...")
    print(f"Date range: {start_date.date()} to {end_date.date()}")

    # Fetch in chunks of 1000 (Binance limit)
    chunk_count = 0
    while len(all_bars) < max_bars:
        bars = connector.fetch_ohlcv(
            symbol, timeframe=timeframe, since=current_since, limit=1000
        )
        if not bars:
            break

        all_bars.extend(bars)
        chunk_count += 1

        # Move the since time forward to just after the last bar
        last_ts = bars[-1].timestamp
        current_since = int(last_ts.timestamp() * 1000) + 60000  # Add 1 minute

        # If we've reached recent data, stop
        if last_ts >= end_date - timedelta(hours=1):
            break

        if chunk_count % 10 == 0:
            print(f"  Fetched {len(all_bars)} bars so far...")

    print(f"Fetched {len(all_bars)} bars in {chunk_count} chunks")

    # Filter to last 'days' days
    cutoff = end_date - timedelta(days=days)
    filtered_bars = [bar for bar in all_bars if bar.timestamp >= cutoff]

    print(f"Using {len(filtered_bars)} bars for backtesting (last {days} days)")

    return filtered_bars


def run_optimization() -> list[OptimizedResult]:
    """Fetch data and run backtests for all parameter sets."""

    # Initialize connector and fetch data
    connector = CCXTConnector({"exchange": EXCHANGE})
    connector.connect()

    try:
        bars = fetch_historical_data(connector, SYMBOL, TIMEFRAME, DAYS_OF_DATA)
    finally:
        connector.disconnect()

    if not bars:
        raise ValueError(f"No data fetched for {SYMBOL}")

    # Extract close prices
    prices = [bar.close for bar in bars]
    timestamps = [bar.timestamp for bar in bars]

    print(f"Data span: {timestamps[0]} to {timestamps[-1]}")

    results: list[OptimizedResult] = []

    for name, fast, slow in PARAM_SETS:
        print(f"\n--- Testing {name} (fast={fast}, slow={slow}) ---")

        # Generate signals
        config = SignalConfig(fast_ma_period=fast, slow_ma_period=slow)
        engine = SignalEngine(prices, config)
        signals = engine.generate_ma_crossover_signals()

        # Run backtest
        backtester = Backtester(prices, signals)
        bt_result = backtester.run()

        # Calculate additional metrics
        false_signal_rate = calculate_false_signal_rate(prices, signals)
        sharpe_ratio = calculate_sharpe_ratio(prices, signals)
        avg_pnl = (
            bt_result.total_pnl / bt_result.num_trades
            if bt_result.num_trades > 0
            else 0.0
        )

        result = OptimizedResult(
            name=name,
            fast_period=fast,
            slow_period=slow,
            trades=bt_result.trades,
            total_pnl=bt_result.total_pnl,
            total_pnl_pct=bt_result.total_pnl_pct,
            win_rate=bt_result.win_rate,
            avg_pnl_per_trade=avg_pnl,
            false_signal_rate=false_signal_rate,
            sharpe_ratio=sharpe_ratio,
            num_trades=bt_result.num_trades,
            num_wins=bt_result.num_wins,
            num_losses=bt_result.num_losses,
        )

        results.append(result)

        print(f"  Trades: {bt_result.num_trades}")
        print(f"  Win Rate: {bt_result.win_rate:.1%}")
        avg_pct = bt_result.total_pnl_pct / bt_result.num_trades if bt_result.num_trades > 0 else 0
        print(f"  Avg P&L/trade: ${avg_pnl:.2f} ({avg_pct:.2f}%)" if bt_result.num_trades > 0 else "  Avg P&L/trade: N/A")
        print(f"  Total P&L: ${bt_result.total_pnl:.2f} ({bt_result.total_pnl_pct:.2f}%)")
        print(f"  False Signal Rate: {false_signal_rate:.1%}")
        print(f"  Sharpe Ratio: {sharpe_ratio:.3f}")

    return results


def recommend_parameters(results: list[OptimizedResult]) -> OptimizedResult:
    """Recommend optimal parameters based on backtest results.

    Scoring criteria:
    - Higher Sharpe ratio (risk-adjusted returns) - weight: 40%
    - Higher win rate - weight: 20%
    - Lower false signal rate - weight: 20%
    - Higher total return - weight: 20%
    """

    def normalize(values: list[float], higher_is_better: bool = True) -> list[float]:
        """Normalize values to 0-1 range."""
        if not values:
            return []
        min_v, max_v = min(values), max(values)
        if max_v == min_v:
            return [1.0] * len(values)
        if higher_is_better:
            return [(v - min_v) / (max_v - min_v) for v in values]
        else:
            return [(max_v - v) / (max_v - min_v) for v in values]

    sharpes = [r.sharpe_ratio for r in results]
    win_rates = [r.win_rate for r in results]
    false_rates = [r.false_signal_rate for r in results]
    total_pnls = [r.total_pnl_pct for r in results]

    norm_sharpes = normalize(sharpes, higher_is_better=True)
    norm_wins = normalize(win_rates, higher_is_better=True)
    norm_false = normalize(false_rates, higher_is_better=False)
    norm_pnl = normalize(total_pnls, higher_is_better=True)

    print("\nComposite Scores:")
    scores = []
    for i, r in enumerate(results):
        score = (
            0.40 * norm_sharpes[i]
            + 0.20 * norm_wins[i]
            + 0.20 * norm_false[i]
            + 0.20 * norm_pnl[i]
        )
        scores.append(score)
        print(f"  {r.name}: score={score:.3f} (sharpe={norm_sharpes[i]:.2f}, win={norm_wins[i]:.2f}, false={norm_false[i]:.2f}, pnl={norm_pnl[i]:.2f})")

    best_idx = scores.index(max(scores))
    return results[best_idx]


def print_summary(results: list[OptimizedResult], recommended: OptimizedResult) -> None:
    """Print a summary table of all results."""

    print("\n" + "=" * 95)
    print("MA CROSSOVER PARAMETER OPTIMIZATION SUMMARY")
    print("=" * 95)

    header = f"{'Parameter Set':<15} {'Trades':>7} {'Win Rate':>9} {'Avg P&L':>12} {'Total P&L':>12} {'False Rate':>10} {'Sharpe':>8}"
    print(header)
    print("-" * 95)

    for r in results:
        avg_pct = r.total_pnl_pct / r.num_trades if r.num_trades > 0 else 0
        marker = " <-- RECOMMENDED" if r.name == recommended.name else ""
        print(
            f"{r.name:<15} {r.num_trades:>7} {r.win_rate:>8.1%} "
            f"${r.avg_pnl_per_trade:>11.2f} {r.total_pnl_pct:>11.2f}% "
            f"{r.false_signal_rate:>9.1%} {r.sharpe_ratio:>7.3f}{marker}"
        )

    print("-" * 95)
    print(f"\nRECOMMENDED: {recommended.name}")
    print(f"  Parameters: fast_ma_period={recommended.fast_period}, slow_ma_period={recommended.slow_period}")
    print(f"  Metrics: Sharpe={recommended.sharpe_ratio:.3f}, Win Rate={recommended.win_rate:.1%}, False Rate={recommended.false_signal_rate:.1%}")
    print()


def update_loop_config(recommended: OptimizedResult) -> None:
    """Update loop.py with recommended parameters."""

    loop_file = "src/trading_champs/core/loop.py"

    with open(loop_file, "r") as f:
        content = f.read()

    # Replace the hardcoded values in _generate_signal
    old_config = """signal_config = SignalConfig(
            fast_ma_period=10,
            slow_ma_period=20,"""

    new_config = f"""signal_config = SignalConfig(
            fast_ma_period={recommended.fast_period},
            slow_ma_period={recommended.slow_period},"""

    if old_config in content:
        content = content.replace(old_config, new_config)

        with open(loop_file, "w") as f:
            f.write(content)

        print(f"Updated {loop_file} with recommended parameters:")
        print(f"  fast_ma_period={recommended.fast_period}")
        print(f"  slow_ma_period={recommended.slow_period}")
    else:
        print(f"\nWARNING: Could not find expected config in {loop_file}")
        print("Manual update required:")
        print(f"  fast_ma_period={recommended.fast_period}")
        print(f"  slow_ma_period={recommended.slow_period}")


if __name__ == "__main__":
    print("MA Crossover Parameter Optimization")
    print("=" * 50)

    try:
        results = run_optimization()
        recommended = recommend_parameters(results)
        print_summary(results, recommended)
        update_loop_config(recommended)

    except Exception as e:
        print(f"\nError during optimization: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)