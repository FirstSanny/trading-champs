"""Unit tests for WatchlistRepository."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from trading_champs.data.watchlist_repository import (
    VALID_ASSET_CLASSES,
    ValidationError,
    WatchlistEntry,
    WatchlistRepository,
    validate_symbol,
)


class TestValidateSymbol:
    """Symbol format validation per asset class."""

    def test_valid_crypto_symbol(self):
        validate_symbol("BTC/USDT", "crypto")

    def test_valid_eth_crypto(self):
        validate_symbol("ETH/USDT", "crypto")

    def test_valid_sol_crypto(self):
        validate_symbol("SOL/USDT", "crypto")

    def test_invalid_crypto_lowercase(self):
        with pytest.raises(ValidationError, match="Invalid crypto symbol"):
            validate_symbol("btc/usdt", "crypto")

    def test_invalid_crypto_no_slash(self):
        with pytest.raises(ValidationError, match="Invalid crypto symbol"):
            validate_symbol("BTCUSDT", "crypto")

    def test_invalid_crypto_wrong_format(self):
        with pytest.raises(ValidationError, match="Invalid crypto symbol"):
            validate_symbol("BTC-USD", "crypto")

    def test_valid_stock_symbol(self):
        validate_symbol("AAPL", "stock")
        validate_symbol("SPY", "stock")
        validate_symbol("META", "stock")

    def test_valid_etf_symbol(self):
        validate_symbol("QQQ", "etf")
        validate_symbol("IWM", "etf")

    def test_invalid_stock_lowercase(self):
        with pytest.raises(ValidationError, match="Invalid .* symbol"):
            validate_symbol("aapl", "stock")

    def test_invalid_stock_with_slash(self):
        with pytest.raises(ValidationError, match="Invalid .* symbol"):
            validate_symbol("AAPL/USD", "stock")

    def test_invalid_asset_class(self):
        with pytest.raises(ValidationError, match="Invalid asset_class"):
            validate_symbol("FOO", "foobar")

    def test_invalid_asset_class_none(self):
        with pytest.raises(ValidationError, match="Invalid asset_class"):
            validate_symbol("AAPL", "")


class TestWatchlistRepositoryUnit:
    """Unit tests with mocked Supabase client."""

    def _make_repo(self, mock_client: MagicMock) -> WatchlistRepository:
        """Create repo with mocked client and short TTL."""
        repo = WatchlistRepository(supabase_client=mock_client, ttl_seconds=300)
        return repo

    # -------------------------------------------------------------------------
    # get_all_entries cache tests
    # -------------------------------------------------------------------------

    def test_get_all_entries_cache_hit(self):
        """Cache valid — returns cached without DB call."""
        import time

        mock_client = MagicMock()
        repo = self._make_repo(mock_client)

        # Pre-populate _all_entries_cache with WatchlistEntry objects
        repo._all_entries_cache = MagicMock()
        repo._all_entries_cache.entries = [
            WatchlistEntry(
                id="1",
                symbol="BTC/USDT",
                asset_class="crypto",
                enabled=True,
                added_by="manual",
                metadata={},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]
        repo._all_entries_cache.timestamp = time.monotonic() - 10  # 10s ago, within TTL

        result = repo.get_all_entries()

        assert len(result) == 1
        assert result[0].symbol == "BTC/USDT"
        mock_client._request.assert_not_called()

    def test_get_all_entries_cache_miss_fetches_from_db(self):
        """Cache miss — fetches from DB and populates cache."""

        mock_client = MagicMock()
        mock_client._request.return_value = [
            {
                "id": "1",
                "symbol": "ETH/USDT",
                "asset_class": "crypto",
                "enabled": True,
                "added_by": "manual",
                "metadata": {},
                "created_at": None,
                "updated_at": None,
            },
        ]
        repo = self._make_repo(mock_client)
        repo._all_entries_cache = None  # ensure cache miss

        result = repo.get_all_entries()

        assert len(result) == 1
        assert result[0].symbol == "ETH/USDT"
        mock_client._request.assert_called_once()
        assert repo._all_entries_cache is not None
        assert repo._all_entries_cache.entries[0].symbol == "ETH/USDT"

        # Stale cache should be cleared on fresh fetch
        assert repo._all_entries_stale_cache is None

    def test_get_all_entries_db_error_returns_stale_cache(self):
        """DB error — returns stale cache if available."""
        import time

        mock_client = MagicMock()
        mock_client._request.side_effect = Exception("connection refused")
        repo = self._make_repo(mock_client)

        repo._all_entries_stale_cache = MagicMock()
        repo._all_entries_stale_cache.entries = [
            WatchlistEntry(
                id="99",
                symbol="STALE1",
                asset_class="crypto",
                enabled=True,
                added_by="manual",
                metadata={},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
            WatchlistEntry(
                id="100",
                symbol="STALE2",
                asset_class="stock",
                enabled=True,
                added_by="manual",
                metadata={},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]
        repo._all_entries_stale_cache.timestamp = time.monotonic() - 600  # very old

        result = repo.get_all_entries()

        assert result[0].symbol == "STALE1"
        assert result[1].symbol == "STALE2"

    def test_get_all_entries_db_error_no_cache_returns_empty(self):
        """DB error with no stale cache — returns empty list."""
        mock_client = MagicMock()
        mock_client._request.side_effect = Exception("connection refused")
        repo = self._make_repo(mock_client)

        result = repo.get_all_entries()

        assert result == []

    # -------------------------------------------------------------------------
    # get_enabled_symbols tests
    # -------------------------------------------------------------------------

    def test_get_enabled_symbols_cache_hit(self):
        """Cache valid — returns cached without DB call."""
        mock_client = MagicMock()
        repo = self._make_repo(mock_client)

        # Pre-populate cache with WatchlistEntry objects
        repo._cache = MagicMock()
        repo._cache.entries = [
            WatchlistEntry(
                id="1",
                symbol="BTC/USDT",
                asset_class="crypto",
                enabled=True,
                added_by="manual",
                metadata={},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
            WatchlistEntry(
                id="2",
                symbol="ETH/USDT",
                asset_class="crypto",
                enabled=True,
                added_by="manual",
                metadata={},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]

        # Manually override timestamp to be recent
        import time

        repo._cache.timestamp = time.monotonic() - 10  # 10s ago, well within 300s

        result = repo.get_enabled_symbols()

        assert result == ["BTC/USDT", "ETH/USDT"]
        mock_client._request.assert_not_called()

    def test_get_enabled_symbols_cache_miss_fetches_from_db(self):
        """Cache miss — fetches from DB and populates cache."""
        mock_client = MagicMock()
        mock_client._request.return_value = [
            {"id": "1", "symbol": "AAPL"},
            {"id": "2", "symbol": "BTC/USDT"},
        ]
        repo = self._make_repo(mock_client)
        repo._cache = None  # ensure cache miss

        result = repo.get_enabled_symbols()

        assert set(result) == {"AAPL", "BTC/USDT"}
        mock_client._request.assert_called_once()
        assert repo._cache is not None
        assert set(e.symbol for e in repo._cache.entries) == {"AAPL", "BTC/USDT"}

    def test_get_enabled_symbols_db_error_returns_stale_cache(self):
        """DB error — returns stale cache if available."""
        mock_client = MagicMock()
        mock_client._request.side_effect = Exception("connection refused")
        repo = self._make_repo(mock_client)

        import time

        repo._stale_cache = MagicMock()
        repo._stale_cache.entries = [
            WatchlistEntry(
                id="99",
                symbol="STALE",
                asset_class="stock",
                enabled=True,
                added_by="manual",
                metadata={},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]
        repo._stale_cache.timestamp = time.monotonic() - 600  # very old

        result = repo.get_enabled_symbols()

        assert result == ["STALE"]

    def test_get_enabled_symbols_db_error_no_cache_returns_empty(self):
        """DB error with no stale cache — returns empty list."""
        mock_client = MagicMock()
        mock_client._request.side_effect = Exception("connection refused")
        repo = self._make_repo(mock_client)

        result = repo.get_enabled_symbols()

        assert result == []

    def test_get_enabled_symbols_db_returns_non_list(self):
        """DB returns unexpected type — returns empty list."""
        mock_client = MagicMock()
        mock_client._request.return_value = {"error": "bad"}
        repo = self._make_repo(mock_client)
        repo._cache = None

        result = repo.get_enabled_symbols()

        assert result == []

    def test_add_symbol_valid_crypto_invalidates_cache(self):
        """Successful add — invalidates cache."""
        mock_client = MagicMock()
        mock_client._request.return_value = {"id": "123"}
        repo = self._make_repo(mock_client)

        import time

        repo._cache = MagicMock()
        repo._cache.entries = [
            WatchlistEntry(
                id="99",
                symbol="OLD",
                asset_class="stock",
                enabled=True,
                added_by="manual",
                metadata={},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]
        repo._cache.timestamp = time.monotonic()

        ok = repo.add_symbol("BTC/USDT", "crypto", added_by="agent:test")

        assert ok is True
        assert repo._cache is None  # invalidated

    def test_add_symbol_invalid_asset_class_raises(self):
        """Invalid asset_class — raises ValidationError before DB call."""
        mock_client = MagicMock()
        repo = self._make_repo(mock_client)

        with pytest.raises(ValidationError, match="Invalid asset_class"):
            repo.add_symbol("AAPL", "unknown_class")

        mock_client._request.assert_not_called()

    def test_add_symbol_invalid_symbol_format_raises(self):
        """Invalid symbol format for asset class — raises ValidationError."""
        mock_client = MagicMock()
        repo = self._make_repo(mock_client)

        with pytest.raises(ValidationError, match="Invalid crypto symbol"):
            repo.add_symbol("AAPL", "crypto")  # AAPL is stock format, not crypto

        mock_client._request.assert_not_called()

    def test_add_symbol_duplicate_returns_false(self):
        """Duplicate symbol — returns False without raising."""
        mock_client = MagicMock()
        mock_client._request.side_effect = Exception("409 Conflict")
        repo = self._make_repo(mock_client)

        ok = repo.add_symbol("BTC/USDT", "crypto")

        assert ok is False

    def test_add_symbol_db_error_returns_false(self):
        """DB error — returns False."""
        mock_client = MagicMock()
        mock_client._request.side_effect = Exception("server error")
        repo = self._make_repo(mock_client)

        ok = repo.add_symbol("BTC/USDT", "crypto")

        assert ok is False

    def test_soft_delete_symbol_not_found(self):
        """Symbol not found — returns False."""
        mock_client = MagicMock()
        mock_client._request.return_value = []  # get_by_symbol returns empty
        repo = self._make_repo(mock_client)

        ok = repo.soft_delete("NOTEXIST")

        assert ok is False

    def test_soft_delete_success_invalidates_cache(self):
        """Successful soft-delete — invalidates cache."""
        mock_client = MagicMock()
        # get_by_symbol returns entry
        mock_client._request.side_effect = [
            [
                {
                    "id": "abc",
                    "symbol": "BTC/USDT",
                    "asset_class": "crypto",
                    "enabled": True,
                    "added_by": "x",
                    "metadata": {},
                    "created_at": None,
                    "updated_at": None,
                }
            ],  # get_by_symbol
            [{"id": "abc"}],  # PATCH
        ]
        repo = self._make_repo(mock_client)
        repo._cache = MagicMock()

        ok = repo.soft_delete("BTC/USDT")

        assert ok is True
        assert repo._cache is None

    def test_update_symbol_not_found(self):
        """Symbol not found — returns False."""
        mock_client = MagicMock()
        mock_client._request.return_value = []
        repo = self._make_repo(mock_client)

        ok = repo.update_symbol("NOTEXIST", enabled=False)

        assert ok is False

    def test_update_symbol_success_invalidates_cache(self):
        """Successful update — invalidates cache."""
        mock_client = MagicMock()
        mock_client._request.side_effect = [
            [
                {
                    "id": "abc",
                    "symbol": "AAPL",
                    "asset_class": "stock",
                    "enabled": True,
                    "added_by": "x",
                    "metadata": {},
                    "created_at": None,
                    "updated_at": None,
                }
            ],
            [{"id": "abc"}],
        ]
        repo = self._make_repo(mock_client)
        repo._cache = MagicMock()

        ok = repo.update_symbol("AAPL", enabled=False)

        assert ok is True
        assert repo._cache is None

    def test_update_symbol_noop(self):
        """Update with no changes — returns True without DB call."""
        mock_client = MagicMock()
        mock_client._request.return_value = [
            {
                "id": "abc",
                "symbol": "AAPL",
                "asset_class": "stock",
                "enabled": True,
                "added_by": "x",
                "metadata": {},
                "created_at": None,
                "updated_at": None,
            },
        ]
        repo = self._make_repo(mock_client)

        ok = repo.update_symbol("AAPL")  # no changes

        assert ok is True
        # Should not have called PATCH (only called get_by_symbol once)
        assert mock_client._request.call_count == 1

    def test_bulk_add_empty_raises(self):
        """Bulk add with empty list — raises ValidationError."""
        mock_client = MagicMock()
        repo = self._make_repo(mock_client)

        with pytest.raises(ValidationError, match="at least one entry"):
            repo.bulk_add([])

        mock_client._request.assert_not_called()

    def test_bulk_add_all_valid(self):
        """Bulk add with all valid entries — inserts all."""
        mock_client = MagicMock()
        mock_client._request.return_value = {"id": "123"}
        repo = self._make_repo(mock_client)
        repo._cache = MagicMock()

        count, errors = repo.bulk_add(
            [
                {"symbol": "BTC/USDT", "asset_class": "crypto"},
                {"symbol": "ETH/USDT", "asset_class": "crypto"},
            ]
        )

        assert count == 2
        assert errors == []
        assert repo._cache is None  # invalidated

    def test_bulk_add_mixed_invalid_raises(self):
        """Bulk add with one invalid entry — raises ValidationError, no inserts."""
        mock_client = MagicMock()
        repo = self._make_repo(mock_client)

        with pytest.raises(ValidationError, match="validation failed"):
            repo.bulk_add(
                [
                    {"symbol": "BTC/USDT", "asset_class": "crypto"},
                    {"symbol": "AAPL", "asset_class": "crypto"},  # AAPL is not valid crypto
                ]
            )

        mock_client._request.assert_not_called()

    def test_bulk_add_partial_failure(self):
        """One symbol fails to insert — count reflects success, errors listed."""
        mock_client = MagicMock()
        # First insert succeeds, second fails
        mock_client._request.side_effect = [
            {"id": "1"},  # BTC success
            Exception("server error"),  # ETH fails
        ]
        repo = self._make_repo(mock_client)
        repo._cache = MagicMock()

        count, errors = repo.bulk_add(
            [
                {"symbol": "BTC/USDT", "asset_class": "crypto"},
                {"symbol": "ETH/USDT", "asset_class": "crypto"},
            ]
        )

        assert count == 1
        assert "ETH/USDT" in errors[0]

    def test_cache_invalidation_on_add(self):
        """Adding a symbol clears the in-memory cache."""
        mock_client = MagicMock()
        mock_client._request.return_value = {"id": "1"}
        repo = self._make_repo(mock_client)

        import time

        repo._cache = MagicMock()
        repo._cache.entries = [
            WatchlistEntry(
                id="99",
                symbol="OLD",
                asset_class="stock",
                enabled=True,
                added_by="manual",
                metadata={},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]
        repo._cache.timestamp = time.monotonic()

        repo.add_symbol("BTC/USDT", "crypto")

        assert repo._cache is None

    def test_cache_invalidation_on_delete(self):
        """Soft-deleting a symbol clears the in-memory cache."""
        mock_client = MagicMock()
        mock_client._request.side_effect = [
            [
                {
                    "id": "1",
                    "symbol": "BTC/USDT",
                    "asset_class": "crypto",
                    "enabled": True,
                    "added_by": "x",
                    "metadata": {},
                    "created_at": None,
                    "updated_at": None,
                }
            ],
            [{"id": "1"}],
        ]
        repo = self._make_repo(mock_client)

        import time

        repo._cache = MagicMock()
        repo._cache.entries = [
            WatchlistEntry(
                id="99",
                symbol="BTC/USDT",
                asset_class="crypto",
                enabled=True,
                added_by="manual",
                metadata={},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]
        repo._cache.timestamp = time.monotonic()

        repo.soft_delete("BTC/USDT")

        assert repo._cache is None

    def test_cache_invalidation_on_update(self):
        """Updating a symbol clears the in-memory cache."""
        mock_client = MagicMock()
        mock_client._request.side_effect = [
            [
                {
                    "id": "1",
                    "symbol": "AAPL",
                    "asset_class": "stock",
                    "enabled": True,
                    "added_by": "x",
                    "metadata": {},
                    "created_at": None,
                    "updated_at": None,
                }
            ],
            [{"id": "1"}],
        ]
        repo = self._make_repo(mock_client)

        import time

        repo._cache = MagicMock()
        repo._cache.entries = [
            WatchlistEntry(
                id="99",
                symbol="AAPL",
                asset_class="stock",
                enabled=True,
                added_by="manual",
                metadata={},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]
        repo._cache.timestamp = time.monotonic()

        repo.update_symbol("AAPL", enabled=False)

        assert repo._cache is None


class TestWatchlistRepositoryIntegration:
    """Integration-style tests with real validation logic (no DB)."""

    def test_validate_symbol_edge_cases(self):
        """Boundary cases for symbol validation."""
        # Crypto max length
        validate_symbol("ABCDEFGHIJ/USDT", "crypto")  # 10 chars
        with pytest.raises(ValidationError):
            validate_symbol("ABCDEFGHIJK/USDT", "crypto")  # 11 chars

        # Stock max 5 chars
        validate_symbol("ABCDE", "stock")  # 5 chars
        with pytest.raises(ValidationError):
            validate_symbol("ABCDEF", "stock")  # 6 chars

    def test_valid_asset_classes(self):
        """All valid asset classes accepted by validate_symbol."""
        # Each asset class has its own valid format
        validate_symbol("BTC/USDT", "crypto")
        validate_symbol("AAPL", "stock")
        validate_symbol("QQQ", "etf")
        assert VALID_ASSET_CLASSES == {"crypto", "stock", "etf"}

    def test_get_by_symbol_returns_watchlist_entry(self):
        """get_by_symbol returns a proper WatchlistEntry."""
        mock_client = MagicMock()
        mock_client._request.return_value = [
            {
                "id": "uuid-123",
                "symbol": "AAPL",
                "asset_class": "stock",
                "enabled": False,
                "added_by": "agent:momentum",
                "metadata": {"exchange": "NYSE"},
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
            }
        ]
        repo = WatchlistRepository(supabase_client=mock_client, ttl_seconds=300)

        entry = repo.get_by_symbol("AAPL")

        assert entry is not None
        assert entry.id == "uuid-123"
        assert entry.symbol == "AAPL"
        assert entry.asset_class == "stock"
        assert entry.enabled is False
        assert entry.added_by == "agent:momentum"
        assert entry.metadata == {"exchange": "NYSE"}
