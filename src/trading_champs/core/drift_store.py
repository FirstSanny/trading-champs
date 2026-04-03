"""DriftStore caches dry_run fill prices keyed by (symbol, bar_timestamp).

Used by DriftDetector to compare dry_run fills against paper fills.
"""

import threading
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DryRunFill:
    """A dry_run fill record for drift comparison."""

    symbol: str
    bar_timestamp: int  # Unix timestamp of the bar close
    entry_price: float
    exit_price: Optional[float]
    side: str  # "long" or "short"
    fill_time: float  # Unix timestamp when fill was recorded


class DriftStore:
    """Stores recent dry_run fill prices keyed by (symbol, bar_timestamp).

    Thread-safe using a threading lock.
    Maintains a rolling window to avoid unbounded memory growth.
    """

    def __init__(self, max_entries: int = 10000):
        """Initialize DriftStore.

        Args:
            max_entries: Maximum number of fill entries to retain.
        """
        self._entries: dict[tuple[str, int], list[DryRunFill]] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._total_fills: int = 0

    def record_fill(self, fill: DryRunFill) -> None:
        """Record a dry_run fill.

        Args:
            fill: The dry_run fill to record.
        """
        key = (fill.symbol, fill.bar_timestamp)
        with self._lock:
            if key not in self._entries:
                self._entries[key] = []
            self._entries[key].append(fill)
            self._total_fills += 1

            # Trim if over capacity — remove oldest half of fills
            if self._total_fills > self._max_entries:
                sorted_keys = sorted(self._entries.keys(), key=lambda k: self._entries[k][0].fill_time)
                for k in sorted_keys[: len(sorted_keys) // 2]:
                    for f in self._entries[k]:
                        self._total_fills -= 1
                    del self._entries[k]

    def get_fill(
        self, symbol: str, bar_timestamp: int
    ) -> Optional[list[DryRunFill]]:
        """Get dry_run fills for a symbol and bar.

        Args:
            symbol: Trading symbol.
            bar_timestamp: Unix timestamp of the bar close.

        Returns:
            List of fills for the bar, or None if not found.
        """
        key = (symbol, bar_timestamp)
        with self._lock:
            return self._entries.get(key)

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._entries.clear()
            self._total_fills = 0
