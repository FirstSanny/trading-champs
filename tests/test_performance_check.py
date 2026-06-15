"""Tests for the trading performance check workflow (TRA-163).

Covers:
- Boundary cases for each classifier threshold.
- Metrics derived from a known trade sequence.
- Append-only JSONL ledger behavior.
- HTTP endpoint auth and empty-state shape.
- End-to-end: populate tracker → run checker → fetch summary.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

# Set test env before importing the app
os.environ["API_SECRET"] = "test-secret-key"
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_ANON_KEY"] = ""

# Ensure src/ is importable when tests are run from repo root.
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_champs.performance.classifier import (  # noqa: E402
    Classification,
    StrategyMetrics,
    Thresholds,
    classify_strategy,
)
from trading_champs.performance.ledger import (  # noqa: E402
    PerformanceLedger,
    append_report,
)
from trading_champs.pl.tracker import (  # noqa: E402
    PnLTracker,
    Trade,
    TradeLog,
    TradeSide,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_trade(
    *,
    pnl: float | None,
    pnl_percent: float | None = 1.0,
    exit_time: datetime | None = None,
    entry_time: datetime | None = None,
    strategy: str = "bollinger",
    closed: bool = True,
) -> Trade:
    return Trade(
        id="t1",
        symbol="AAPL",
        side=TradeSide.LONG,
        entry_price=100.0,
        exit_price=110.0 if closed else None,
        quantity=1.0,
        entry_time=entry_time or datetime(2026, 1, 1),
        exit_time=exit_time,
        pnl=pnl,
        pnl_percent=pnl_percent,
        strategy=strategy,
    )


def _metrics(
    *,
    total_pnl: float = 0.0,
    num_trades: int = 0,
    num_wins: int = 0,
    num_losses: int = 0,
    win_rate: float = 0.0,
    profit_factor: float = 0.0,
    max_drawdown_pct: float = 0.0,
    sharpe_ratio: float = 0.0,
    days_since_last_trade: float | None = None,
    open_position_count: int = 0,
) -> StrategyMetrics:
    return StrategyMetrics(
        total_pnl=total_pnl,
        num_trades=num_trades,
        num_wins=num_wins,
        num_losses=num_losses,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe_ratio,
        days_since_last_trade=days_since_last_trade,
        open_position_count=open_position_count,
    )


# ---------------------------------------------------------------------------
# Classifier: boundary cases
# ---------------------------------------------------------------------------


class TestClassifyStrategy:
    """Boundary cases for the classifier's thresholds."""

    def test_zero_trades_is_inactive(self):
        m = _metrics(num_trades=0)
        assert classify_strategy(m) == Classification.INACTIVE

    def test_exactly_at_drawdown_threshold_is_watch(self):
        """25.0% drawdown is the watch-band ceiling — not poor (strict >)."""
        m = _metrics(num_trades=20, num_wins=15, num_losses=5, win_rate=0.75,
                     profit_factor=2.0, max_drawdown_pct=25.0)
        assert classify_strategy(m) == Classification.WATCH

    def test_just_over_drawdown_threshold_is_poor(self):
        m = _metrics(num_trades=20, num_wins=15, num_losses=5, win_rate=0.75,
                     profit_factor=2.0, max_drawdown_pct=25.01)
        assert classify_strategy(m) == Classification.POOR

    def test_drawdown_watch_band(self):
        """15% < dd <= 25% is watch."""
        m = _metrics(num_trades=20, num_wins=15, num_losses=5, win_rate=0.75,
                     profit_factor=2.0, max_drawdown_pct=20.0)
        assert classify_strategy(m) == Classification.WATCH

    def test_low_drawdown_is_ok(self):
        """Below the watch band, healthy strategies are ok."""
        m = _metrics(num_trades=20, num_wins=15, num_losses=5, win_rate=0.75,
                     profit_factor=2.0, max_drawdown_pct=10.0)
        assert classify_strategy(m) == Classification.OK

    def test_win_rate_floor_with_sufficient_sample(self):
        """40% win rate is OK; 39.9% with 10+ trades is poor."""
        ok = _metrics(num_trades=10, num_wins=4, win_rate=0.40,
                      profit_factor=1.5)
        assert classify_strategy(ok) == Classification.OK
        poor = _metrics(num_trades=10, num_wins=3, win_rate=0.30,
                        profit_factor=1.5)
        assert classify_strategy(poor) == Classification.POOR

    def test_win_rate_below_floor_with_insufficient_sample_is_watch(self):
        """< 10 trades: bad win rate is watch, not poor."""
        m = _metrics(num_trades=5, num_wins=1, win_rate=0.20,
                     profit_factor=0.5)
        assert classify_strategy(m) == Classification.WATCH

    def test_profit_factor_floor(self):
        ok = _metrics(num_trades=10, win_rate=0.5, profit_factor=1.0)
        assert classify_strategy(ok) == Classification.OK
        poor = _metrics(num_trades=10, win_rate=0.5, profit_factor=0.99)
        assert classify_strategy(poor) == Classification.POOR

    def test_staleness_flags_poor(self):
        m = _metrics(num_trades=5, days_since_last_trade=20.0)
        assert classify_strategy(m) == Classification.POOR

    def test_staleness_just_under_is_not_poor(self):
        m = _metrics(num_trades=5, days_since_last_trade=14.0)
        # 14.0 not > 14; not poor on staleness. But small sample → watch.
        assert classify_strategy(m) == Classification.WATCH

    def test_custom_thresholds(self):
        """Thresholds arg overrides defaults."""
        t = Thresholds(max_drawdown_pct=10.0)
        m = _metrics(num_trades=5, max_drawdown_pct=12.0)
        assert classify_strategy(m, t) == Classification.POOR
        # At default threshold (25%) this would be watch, not poor.
        m2 = _metrics(num_trades=5, max_drawdown_pct=12.0)
        assert classify_strategy(m2) == Classification.WATCH


# ---------------------------------------------------------------------------
# Metrics computation from a real trade sequence
# ---------------------------------------------------------------------------


class TestMetricsFromTrades:
    """End-to-end metrics computation via PerformanceChecker."""

    def _build_tracker(self) -> PnLTracker:
        tracker = PnLTracker()
        log: TradeLog = tracker.trade_log
        # 4 winning trades then 1 losing trade — well above sample floor.
        now = datetime(2026, 6, 1, 12, 0, 0)
        for i, pnl in enumerate([100.0, 200.0, 150.0, 50.0, -120.0]):
            t = Trade(
                id=f"t{i}",
                symbol="AAPL",
                side=TradeSide.LONG,
                entry_price=100.0,
                exit_price=110.0 if pnl > 0 else 95.0,
                quantity=1.0,
                entry_time=now + timedelta(hours=i),
                exit_time=now + timedelta(hours=i, minutes=30),
                pnl=pnl,
                pnl_percent=pnl / 100.0 * 100.0,
                strategy="bollinger",
            )
            log.trades.append(t)
        return tracker

    def test_known_sequence_produces_expected_counts(self):
        from trading_champs.performance.checker import PerformanceChecker

        tracker = self._build_tracker()
        checker = PerformanceChecker(
            tracker=tracker,
            strategy_stages={"bollinger": "dry_run"},
            known_strategies=["bollinger"],
            now=datetime(2026, 6, 10, 12, 0, 0),
        )
        report = checker.run()
        snap = report.strategies["bollinger"]
        assert snap.metrics.num_trades == 5
        assert snap.metrics.num_wins == 4
        assert snap.metrics.num_losses == 1
        assert snap.metrics.win_rate == 0.8
        # total_pnl = 100 + 200 + 150 + 50 - 120 = 380
        assert abs(snap.metrics.total_pnl - 380.0) < 1e-6
        # profit_factor = 500 / 120 ≈ 4.1667
        assert abs(snap.metrics.profit_factor - (500.0 / 120.0)) < 1e-3

    def test_insufficient_sample_classifies_watch(self):
        from trading_champs.performance.checker import PerformanceChecker

        tracker = PnLTracker()
        for i in range(3):
            tracker.trade_log.trades.append(
                Trade(
                    id=f"t{i}",
                    symbol="AAPL",
                    side=TradeSide.LONG,
                    entry_price=100.0,
                    exit_price=110.0,
                    quantity=1.0,
                    entry_time=datetime(2026, 1, 1),
                    exit_time=datetime(2026, 1, 2),
                    pnl=100.0,
                    pnl_percent=10.0,
                    strategy="rsi",
                )
            )
        checker = PerformanceChecker(
            tracker=tracker,
            strategy_stages={"rsi": "dry_run"},
            known_strategies=["rsi"],
            now=datetime(2026, 1, 5),
        )
        report = checker.run()
        assert report.strategies["rsi"].classification == Classification.WATCH

    def test_unknown_strategy_flagged_in_notes(self):
        from trading_champs.performance.checker import PerformanceChecker

        tracker = PnLTracker()
        tracker.trade_log.trades.append(
            _make_trade(pnl=50.0, pnl_percent=5.0, strategy="legacy_xyz")
        )
        checker = PerformanceChecker(
            tracker=tracker,
            known_strategies=["bollinger"],  # legacy_xyz not in set
        )
        report = checker.run()
        assert "legacy_xyz" in report.strategies
        assert any("unknown_strategy_trades" in n for n in report.notes)

    def test_open_position_count(self):
        from trading_champs.performance.checker import PerformanceChecker

        tracker = PnLTracker()
        # 1 closed + 1 open
        tracker.trade_log.trades.append(
            _make_trade(pnl=100.0, pnl_percent=10.0, closed=True)
        )
        tracker.trade_log.trades.append(
            _make_trade(pnl=None, pnl_percent=None, closed=False)
        )
        checker = PerformanceChecker(
            tracker=tracker, known_strategies=["bollinger"]
        )
        report = checker.run()
        assert report.strategies["bollinger"].metrics.open_position_count == 1


# ---------------------------------------------------------------------------
# Ledger behavior
# ---------------------------------------------------------------------------


class TestLedgerAppend:
    """Append-only JSONL ledger."""

    def test_creates_parent_dir_and_appends(self, tmp_path: Path):
        from trading_champs.performance.checker import (
            PerformanceChecker,
            PerformanceReport,
        )

        target = tmp_path / "subdir" / "perf.jsonl"
        ledger = PerformanceLedger(target)
        # First, fabricate a small report by running an empty checker.
        tracker = PnLTracker()
        report = PerformanceChecker(tracker=tracker).run()
        ledger.append(report)
        ledger.append(report)
        lines = target.read_text().splitlines()
        assert len(lines) == 2
        for line in lines:
            assert json.loads(line)["run_at"]  # parseable JSON

    def test_does_not_clobber_existing(self, tmp_path: Path):
        from trading_champs.performance.checker import PerformanceChecker

        target = tmp_path / "perf.jsonl"
        target.write_text('{"run_at":"preset","strategies":{},"summary":{},'
                          '"thresholds":{},"notes":[]}\n')
        ledger = PerformanceLedger(target)
        tracker = PnLTracker()
        ledger.append(PerformanceChecker(tracker=tracker).run())
        rows = ledger.read_all()
        assert rows[0]["run_at"] == "preset"
        assert len(rows) == 2

    def test_read_last_n(self, tmp_path: Path):
        from trading_champs.performance.checker import PerformanceChecker

        target = tmp_path / "perf.jsonl"
        ledger = PerformanceLedger(target)
        tracker = PnLTracker()
        for _ in range(5):
            ledger.append(PerformanceChecker(tracker=tracker).run())
        last2 = ledger.read_last(2)
        assert len(last2) == 2

    def test_read_all_missing_file_is_empty(self, tmp_path: Path):
        ledger = PerformanceLedger(tmp_path / "absent.jsonl")
        assert ledger.read_all() == []

    def test_env_var_override(self, tmp_path: Path, monkeypatch):
        from trading_champs.performance.checker import PerformanceChecker

        target = tmp_path / "custom.jsonl"
        monkeypatch.setenv("PERF_LOG_PATH", str(target))
        ledger = PerformanceLedger()
        ledger.append(PerformanceChecker(tracker=PnLTracker()).run())
        assert target.exists()


# ---------------------------------------------------------------------------
# HTTP endpoint integration
# ---------------------------------------------------------------------------


class TestEndpointAuth:
    """Performance endpoints sit behind the same auth_guard as the rest."""

    def _make_client(self):
        from starlette.testclient import TestClient

        from api.index import app

        return TestClient(app)

    def test_performance_run_requires_auth(self):
        with patch("api.index._ensure_trader_state"):
            client = self._make_client()
            r = client.post("/api/debug/performance-run")
            assert r.status_code == 401

    def test_performance_summary_requires_auth(self):
        with patch("api.index._ensure_trader_state"):
            client = self._make_client()
            r = client.get("/api/debug/performance-summary")
            assert r.status_code == 401

    def test_performance_history_requires_auth(self):
        with patch("api.index._ensure_trader_state"):
            client = self._make_client()
            r = client.get("/api/debug/performance")
            assert r.status_code == 401


class TestEndpointEmpty:
    """Empty state returns 200 with zero counts."""

    def test_summary_with_no_reports(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("PERF_LOG_PATH", str(tmp_path / "empty.jsonl"))
        with patch("api.index._ensure_trader_state"), \
             patch("api.index._get_performance_ledger") as mock_ledger:
            mock_ledger.return_value.read_last.return_value = []
            from starlette.testclient import TestClient
            from api.index import app

            client = TestClient(app)
            r = client.get(
                "/api/debug/performance-summary",
                headers={"Authorization": "Bearer test-secret-key"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["run_at"] is None
            assert body["summary"]["poor"] == 0
            assert "no performance reports recorded yet" in body["notes"]

    def test_history_default_30_capped_at_365(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("PERF_LOG_PATH", str(tmp_path / "h.jsonl"))
        with patch("api.index._ensure_trader_state"), \
             patch("api.index._get_performance_ledger") as mock_ledger:
            mock_ledger.return_value.read_last.return_value = []
            from starlette.testclient import TestClient
            from api.index import app

            client = TestClient(app)
            r = client.get(
                "/api/debug/performance?n=99999",
                headers={"Authorization": "Bearer test-secret-key"},
            )
            assert r.status_code == 200
            # read_last should have been called with 365 (cap)
            mock_ledger.return_value.read_last.assert_called_with(365)


class TestEndToEnd:
    """Populate the tracker, run the checker via the endpoint, read summary."""

    def test_full_loop(self, tmp_path: Path, monkeypatch):
        # Redirect ledger to tmp.
        ledger_file = tmp_path / "e2e.jsonl"
        monkeypatch.setenv("PERF_LOG_PATH", str(ledger_file))

        # Seed the in-process tracker with a couple of trades.
        from api import index as api_index

        api_index.tracker.trade_log.trades.clear()
        for i, pnl in enumerate([100.0, 50.0]):
            api_index.tracker.trade_log.trades.append(
                Trade(
                    id=f"e2e_{i}",
                    symbol="MSFT",
                    side=TradeSide.LONG,
                    entry_price=100.0,
                    exit_price=110.0 if pnl > 0 else 95.0,
                    quantity=1.0,
                    entry_time=datetime(2026, 6, 1) + timedelta(hours=i),
                    exit_time=datetime(2026, 6, 1) + timedelta(hours=i, minutes=30),
                    pnl=pnl,
                    pnl_percent=pnl,
                    strategy="bollinger",
                )
            )

        # Reset the singleton ledger so it picks up the new env path.
        import api.index as api_index_mod
        api_index_mod._performance_ledger = None

        with patch("api.index._ensure_trader_state"):
            from starlette.testclient import TestClient
            from api.index import app

            client = TestClient(app)
            # Run the checker.
            r1 = client.post(
                "/api/debug/performance-run",
                headers={"Authorization": "Bearer test-secret-key"},
            )
            assert r1.status_code == 200
            body1 = r1.json()
            assert "bollinger" in body1["strategies"]
            assert body1["strategies"]["bollinger"]["metrics"]["num_trades"] == 2

            # Summary endpoint should return the same report.
            r2 = client.get(
                "/api/debug/performance-summary",
                headers={"Authorization": "Bearer test-secret-key"},
            )
            assert r2.status_code == 200
            body2 = r2.json()
            assert body2["run_at"] == body1["run_at"]

            # Ledger file should have one line.
            assert len(ledger_file.read_text().splitlines()) == 1
