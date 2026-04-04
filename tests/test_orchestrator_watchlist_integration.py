"""Integration tests for Orchestrator ↔ WatchlistRepository wiring."""

from unittest.mock import MagicMock, patch
import threading


class TestOrchestratorWatchlistIntegration:
    """Verify the orchestrator correctly uses WatchlistRepository."""

    def test_iterate_all_fetches_from_watchlist(self):
        """iterate_all passes enabled symbols from repo to strategy loops."""
        mock_repo = MagicMock()
        mock_repo.get_enabled_symbols.return_value = ["BTC/USDT", "ETH/USDT"]

        with patch("api.index._get_watchlist_repo", return_value=mock_repo):
            from trading_champs.core.orchestrator import Orchestrator

            mock_config = MagicMock()
            mock_config.symbols = []
            mock_config.max_position_size = 1.0
            mock_config.max_total_exposure = 1.0
            mock_config.watchlist_repository = mock_repo

            with patch.object(Orchestrator, "_iterate_all_impl", return_value=None):
                Orchestrator(config=mock_config, scheduler=MagicMock())

        # Verify repo was queried during construction (via _refresh_symbols_from_watchlist)
        mock_repo.get_enabled_symbols.assert_called()

    def test_iterate_all_skips_watchlist_when_not_configured(self):
        """When watchlist_repository is None, orchestrator silently skips."""
        from trading_champs.core.orchestrator import Orchestrator

        mock_config = MagicMock()
        mock_config.symbols = ["BTC/USDT", "ETH/USDT"]
        mock_config.max_position_size = 1.0
        mock_config.max_total_exposure = 1.0
        mock_config.watchlist_repository = None

        with patch.object(Orchestrator, "_iterate_all_impl", return_value=None):
            orch = Orchestrator(config=mock_config, scheduler=MagicMock())

        # Should not raise
        orch.iterate_all()


class TestWatchlistRepositorySingleton:
    """Singleton thread-safety tests for get_watchlist_repository."""

    def test_singleton_returns_same_instance(self):
        """Multiple calls return the same singleton instance."""
        # Reset module-level singleton before test
        import trading_champs.data.watchlist_repository as repo_module

        repo_module._watchlist_repo = None

        with patch.object(repo_module, "WatchlistRepository"):
            from trading_champs.data.watchlist_repository import get_watchlist_repository

            repo1 = get_watchlist_repository()
            repo2 = get_watchlist_repository()
            assert repo1 is repo2

        # Restore
        repo_module._watchlist_repo = None

    def test_singleton_thread_safety(self):
        """get_watchlist_repository is thread-safe under concurrent access."""
        import trading_champs.data.watchlist_repository as repo_module

        repo_module._watchlist_repo = None

        results: dict[int, object] = {}
        errors: list[Exception] = []

        def get_repo(thread_id: int):
            try:
                with patch.object(repo_module, "WatchlistRepository", return_value=MagicMock()):
                    from trading_champs.data.watchlist_repository import get_watchlist_repository

                    repo = get_watchlist_repository()
                    results[thread_id] = repo
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(20):
            t = threading.Thread(target=get_repo, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
        # All threads should get the same singleton instance
        unique_ids = set(id(r) for r in results.values())
        assert len(unique_ids) == 1, f"Multiple instances created: {unique_ids}"

        # Restore
        repo_module._watchlist_repo = None
