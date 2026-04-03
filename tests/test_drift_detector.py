"""Critical path tests for DriftDetector and DriftStore."""

import time

from trading_champs.core.drift_detector import DriftDetector
from trading_champs.core.drift_store import DriftStore, DryRunFill


class TestDriftDetector:
    """Critical path tests for DriftDetector.check_drift()."""

    def _make_detector(self, window: int = 3, threshold_pct: float = 0.5) -> DriftDetector:
        """Create a DriftDetector with short window/threshold for testing."""
        store = DriftStore()
        return DriftDetector(store, window_trades=window, threshold_pct=threshold_pct / 100.0)

    def test_normal_no_drift(self):
        """Case 1: Normal — no significant divergence, no alert."""
        detector = self._make_detector(window=3, threshold_pct=0.5)

        # Record dry_run fills at prices 100, 101, 102
        base_time = int(time.time())
        for i, price in enumerate([100.0, 101.0, 102.0]):
            fill = DryRunFill(
                symbol="AAPL",
                bar_timestamp=base_time + i * 60,
                entry_price=price,
                exit_price=None,
                side="long",
                fill_time=time.time(),
            )
            detector.record_dry_run_fill(fill)

        # Paper fills at slightly different prices (within 0.3% = below 0.5% threshold)
        alert = detector.check_drift("AAPL", paper_entry_price=100.3, bar_timestamp=base_time)

        assert alert is None  # No alert — divergence below threshold

    def test_paper_before_dry_run_skipped(self):
        """Case 2: Paper trade arrives before dry_run trade — skip silently."""
        detector = self._make_detector(window=3, threshold_pct=0.5)

        # No dry_run fill recorded yet for this bar
        base_time = int(time.time())

        # Paper fill arrives first
        alert = detector.check_drift("AAPL", paper_entry_price=100.5, bar_timestamp=base_time)

        # Should return None (no dry_run fill to compare yet)
        assert alert is None

    def test_drift_exceeded_fires_alert(self):
        """Case 3: Average divergence exceeds threshold — fires DriftAlert."""
        detector = self._make_detector(window=3, threshold_pct=0.5)
        # threshold_pct=0.5 means 0.5% divergence triggers alert

        base_time = int(time.time())

        # Record 3 dry_run fills at 100.0
        for i in range(3):
            fill = DryRunFill(
                symbol="AAPL",
                bar_timestamp=base_time + i * 60,
                entry_price=100.0,
                exit_price=None,
                side="long",
                fill_time=time.time(),
            )
            detector.record_dry_run_fill(fill)

        # Paper fills at 101.5 (1.5% divergence — above 0.5% threshold)
        # Need 3 fills to meet window=3
        for i in range(3):
            alert = detector.check_drift(
                "AAPL", paper_entry_price=101.5, bar_timestamp=base_time + i * 60
            )
            if i < 2:
                assert alert is None  # Not enough trades yet
            else:
                assert alert is not None
                assert alert.symbol == "AAPL"
                assert alert.avg_divergence_pct > 0.5


class TestDriftStore:
    """Tests for DriftStore.record_fill() and get_fill()."""

    def test_record_and_retrieve(self):
        """Dry_run fills are stored and retrieved by symbol+timestamp."""
        store = DriftStore()

        ts = int(time.time())
        fill = DryRunFill(
            symbol="AAPL",
            bar_timestamp=ts,
            entry_price=150.0,
            exit_price=155.0,
            side="long",
            fill_time=time.time(),
        )
        store.record_fill(fill)

        retrieved = store.get_fill("AAPL", ts)
        assert retrieved is not None
        assert len(retrieved) == 1
        assert retrieved[0].entry_price == 150.0
        assert retrieved[0].exit_price == 155.0

    def test_get_fill_returns_none_for_unknown(self):
        """get_fill returns None when no fills exist for symbol/timestamp."""
        store = DriftStore()
        ts = int(time.time())

        assert store.get_fill("UNKNOWN", ts) is None
        assert store.get_fill("AAPL", ts + 9999) is None

    def test_multiple_fills_same_bar(self):
        """Multiple fills for the same bar are all retained."""
        store = DriftStore()
        ts = int(time.time())

        for price in [100.0, 101.0, 102.0]:
            fill = DryRunFill(
                symbol="AAPL",
                bar_timestamp=ts,
                entry_price=price,
                exit_price=None,
                side="long",
                fill_time=time.time(),
            )
            store.record_fill(fill)

        retrieved = store.get_fill("AAPL", ts)
        assert retrieved is not None
        assert len(retrieved) == 3
