"""DriftDetector identifies slippage divergence between dry_run and paper fills.

Compares paper trade entry prices against corresponding dry_run fills for the
same symbol on the same trading bar (1m bar close price). This avoids timestamp
precision issues between simulated and real fills.
"""

import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

import requests

from trading_champs.core.drift_store import DriftStore, DryRunFill

logger = logging.getLogger(__name__)

DRIFT_WINDOW_TRADES = int(os.environ.get("DRIFT_WINDOW_TRADES", "10"))
DRIFT_THRESHOLD_PCT = float(os.environ.get("DRIFT_THRESHOLD_PCT", "0.5")) / 100.0


@dataclass(frozen=True)
class DriftAlert:
    """A drift alert indicating slippage divergence."""

    symbol: str
    avg_divergence_pct: float
    window_trades: int
    threshold_pct: float
    triggered_at: float


class DriftDetector:
    """Detects slippage divergence between dry_run and paper fills.

    For each paper trade entry, finds the corresponding dry_run trade for
    the same symbol on the same trading bar (1m bar close price).
    """

    def __init__(
        self,
        drift_store: DriftStore,
        window_trades: int = DRIFT_WINDOW_TRADES,
        threshold_pct: float = DRIFT_THRESHOLD_PCT,
    ):
        """Initialize DriftDetector.

        Args:
            drift_store: DriftStore instance with dry_run fills.
            window_trades: Number of recent trades to consider for drift calculation.
            threshold_pct: Drift threshold as a fraction (e.g., 0.005 = 0.5%).
        """
        self._store = drift_store
        self._window = window_trades
        self._threshold = threshold_pct
        self._divergences: dict[str, list[float]] = defaultdict(list)

    def check_drift(
        self,
        symbol: str,
        paper_entry_price: float,
        bar_timestamp: int,
    ) -> Optional[DriftAlert]:
        """Check for drift between paper fill and dry_run fill for the same bar.

        Args:
            symbol: Trading symbol.
            paper_entry_price: Entry price from paper trading.
            bar_timestamp: Unix timestamp of the bar close.

        Returns:
            DriftAlert if drift exceeds threshold, None otherwise.
        """
        try:
            dry_run_fills = self._store.get_fill(symbol, bar_timestamp)
            if not dry_run_fills:
                return None

            # Use the most recent dry_run fill for this bar
            dry_run_fill = dry_run_fills[-1]
            dry_run_price = dry_run_fill.entry_price

            if dry_run_price <= 0:
                return None

            divergence = abs(paper_entry_price - dry_run_price) / dry_run_price
            self._divergences[symbol].append(divergence)

            # Keep only the last window trades
            if len(self._divergences[symbol]) > self._window * 2:
                self._divergences[symbol] = self._divergences[symbol][-self._window:]

            # Only check when we have enough trades
            if len(self._divergences[symbol]) < self._window:
                return None

            recent_divergences = self._divergences[symbol][-self._window:]
            avg_divergence = sum(recent_divergences) / len(recent_divergences)

            if avg_divergence > self._threshold:
                alert = DriftAlert(
                    symbol=symbol,
                    avg_divergence_pct=avg_divergence * 100,
                    window_trades=self._window,
                    threshold_pct=self._threshold * 100,
                    triggered_at=time.time(),
                )
                logger.warning(
                    f"Drift alert for {symbol}: avg_divergence={avg_divergence*100:.3f}%, "
                    f"threshold={self._threshold*100:.3f}%, trades={self._window}"
                )
                return alert

            return None

        except requests.exceptions.Timeout:
            logger.warning("Drift check skipped: Alpaca API timeout")
            return None
        except ValueError as e:
            logger.warning(f"Drift check skipped: {e}")
            return None
        except Exception as e:
            logger.error(f"Drift check error for {symbol}: {e}")
            return None

    def record_dry_run_fill(self, fill: DryRunFill) -> None:
        """Record a dry_run fill for future drift comparison.

        Args:
            fill: The dry_run fill to record.
        """
        self._store.record_fill(fill)

    def get_recent_divergences(self, symbol: str) -> list[float]:
        """Get recent divergence values for a symbol.

        Args:
            symbol: Trading symbol.

        Returns:
            List of recent divergence values.
        """
        return self._divergences.get(symbol, [])
