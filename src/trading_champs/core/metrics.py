"""Prometheus metrics for the trading loop."""

from prometheus_client import Counter, Gauge, Histogram

# Iterate cycle counter — tracks success/skip/error outcomes
iterate_cycle_total = Counter(
    "iterate_cycle_total",
    "Total number of iterate cycles",
    ["status"],  # success, skipped, error
)

# Alpaca API latency histogram
alpaca_api_duration_seconds = Histogram(
    "alpaca_api_duration_seconds",
    "Duration of Alpaca API calls in seconds",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Open positions gauge — updated on open/close
open_positions = Gauge(
    "open_positions",
    "Number of currently open positions",
)

# Order submission counter — tracks filled/rejected/retryable
order_submission_total = Counter(
    "order_submission_total",
    "Total order submissions to Alpaca",
    ["status", "side"],  # filled, rejected, retryable, error | buy, sell
)
