"""Integration tests for watchlist API endpoints in api/index.py."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_watchlist_repo():
    """Provides a fresh MagicMock watchlist repository for each test."""
    return MagicMock()


@pytest.fixture
def test_client(mock_watchlist_repo):
    """Creates a TestClient with an isolated api.index module.

    Due to the module-level singleton pattern in api/index.py
    (_watchlist_repo at module level, _get_watchlist_repo closure),
    we must isolate the module for each test to prevent cross-test
    pollution. We reload the module with _watchlist_repo pre-set to
    the mock so the singleton check is bypassed.
    """
    import importlib

    import api.index

    # Reset module state and set mock as the singleton
    api.index._watchlist_repo = mock_watchlist_repo

    def patched_getter():
        return mock_watchlist_repo

    # Patch the getter in the module's namespace and reload to
    # re-define watchlist_api with the patched getter in its closure
    original_getter = api.index._get_watchlist_repo
    api.index._get_watchlist_repo = patched_getter

    importlib.reload(api.index)

    # Restore original after reload
    api.index._get_watchlist_repo = original_getter
    api.index._watchlist_repo = mock_watchlist_repo

    from starlette.testclient import TestClient

    return TestClient(api.index.app)


def auth_headers():
    return {"Authorization": "Bearer test-secret-key"}


class TestWatchlistAPI:
    """Tests for /api/watchlist endpoints."""

    def test_get_watchlist_empty(self, test_client, mock_watchlist_repo):
        """GET /api/watchlist with no symbols returns empty list."""
        mock_watchlist_repo.get_all_entries.return_value = []
        response = test_client.get("/api/watchlist", headers=auth_headers())
        assert response.status_code == 200
        assert response.json()["symbols"] == []

    def test_get_watchlist_with_symbols(self, test_client, mock_watchlist_repo):
        """GET /api/watchlist returns all entries."""
        from datetime import datetime

        from trading_champs.data.watchlist_repository import WatchlistEntry

        mock_watchlist_repo.get_all_entries.return_value = [
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
                symbol="AAPL",
                asset_class="stock",
                enabled=True,
                added_by="agent:momentum",
                metadata={"exchange": "NYSE"},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]
        response = test_client.get("/api/watchlist", headers=auth_headers())
        assert response.status_code == 200
        data = response.json()
        assert len(data["symbols"]) == 2
        assert data["symbols"][0]["symbol"] == "BTC/USDT"
        assert data["symbols"][1]["added_by"] == "agent:momentum"

    def test_get_watchlist_public(self, test_client, mock_watchlist_repo):
        """GET /api/watchlist without auth returns 200 (public endpoint)."""
        mock_watchlist_repo.get_all_entries.return_value = []
        response = test_client.get("/api/watchlist")
        assert response.status_code == 200

    def test_patch_watchlist_requires_auth(self, test_client):
        """PATCH /api/watchlist/{symbol} without auth returns 401."""
        response = test_client.patch(
            "/api/watchlist/AAPL",
            json={"enabled": "false"},
        )
        assert response.status_code == 401

    def test_post_watchlist_valid(self, test_client, mock_watchlist_repo):
        """POST /api/watchlist creates a symbol."""
        mock_watchlist_repo.add_symbol.return_value = True
        mock_watchlist_repo.get_by_symbol.return_value = MagicMock(
            to_dict=lambda: {"symbol": "BTC/USDT"}
        )
        response = test_client.post(
            "/api/watchlist",
            headers=auth_headers(),
            json={"symbol": "BTC/USDT", "asset_class": "crypto"},
        )
        assert response.status_code == 201
        mock_watchlist_repo.add_symbol.assert_called_once_with("BTC/USDT", "crypto")

    def test_post_watchlist_missing_symbol(self, test_client):
        """POST /api/watchlist without symbol returns 400."""
        response = test_client.post(
            "/api/watchlist",
            headers=auth_headers(),
            json={"asset_class": "crypto"},
        )
        assert response.status_code == 400
        assert "required" in response.json()["error"]

    def test_post_watchlist_missing_asset_class(self, test_client):
        """POST /api/watchlist without asset_class returns 400."""
        response = test_client.post(
            "/api/watchlist",
            headers=auth_headers(),
            json={"symbol": "AAPL"},
        )
        assert response.status_code == 400

    def test_post_watchlist_invalid_format(self, test_client, mock_watchlist_repo):
        """POST /api/watchlist with bad format returns 400."""
        from trading_champs.data.watchlist_repository import ValidationError

        mock_watchlist_repo.add_symbol.side_effect = ValidationError("Invalid crypto symbol")
        response = test_client.post(
            "/api/watchlist",
            headers=auth_headers(),
            json={"symbol": "AAPL", "asset_class": "crypto"},
        )
        assert response.status_code == 400
        assert "Invalid crypto" in response.json()["error"]

    def test_post_watchlist_duplicate(self, test_client, mock_watchlist_repo):
        """POST /api/watchlist for existing symbol returns 409."""
        mock_watchlist_repo.add_symbol.return_value = False
        response = test_client.post(
            "/api/watchlist",
            headers=auth_headers(),
            json={"symbol": "BTC/USDT", "asset_class": "crypto"},
        )
        assert response.status_code == 409

    def test_delete_watchlist_symbol_exists(self, test_client, mock_watchlist_repo):
        """DELETE /api/watchlist/{symbol} soft-deletes the symbol."""
        mock_watchlist_repo.soft_delete.return_value = True
        response = test_client.delete(
            "/api/watchlist/BTCUSDT",
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["symbol"] == "BTCUSDT"
        mock_watchlist_repo.soft_delete.assert_called_once_with("BTCUSDT")

    def test_delete_watchlist_symbol_not_found(self, test_client, mock_watchlist_repo):
        """DELETE /api/watchlist/{symbol} for non-existent symbol returns 404."""
        mock_watchlist_repo.soft_delete.return_value = False
        response = test_client.delete(
            "/api/watchlist/NOTEXIST",
            headers=auth_headers(),
        )
        assert response.status_code == 404

    def test_patch_watchlist_update_enabled(self, test_client, mock_watchlist_repo):
        """PATCH /api/watchlist/{symbol} updates enabled state."""
        mock_watchlist_repo.update_symbol.return_value = True
        mock_watchlist_repo.get_by_symbol.return_value = MagicMock(
            to_dict=lambda: {"symbol": "AAPL", "enabled": False}
        )
        response = test_client.patch(
            "/api/watchlist/AAPL",
            headers=auth_headers(),
            json={"enabled": "false"},
        )
        assert response.status_code == 200
        mock_watchlist_repo.update_symbol.assert_called_once_with(
            "AAPL", enabled=False, metadata=None
        )

    def test_patch_watchlist_update_metadata(self, test_client, mock_watchlist_repo):
        """PATCH /api/watchlist/{symbol} updates metadata."""
        mock_watchlist_repo.update_symbol.return_value = True
        mock_watchlist_repo.get_by_symbol.return_value = MagicMock(
            to_dict=lambda: {"symbol": "AAPL", "metadata": {"note": "watched"}}
        )
        response = test_client.patch(
            "/api/watchlist/AAPL",
            headers=auth_headers(),
            json={"metadata": '{"note": "watched"}'},
        )
        assert response.status_code == 200
        mock_watchlist_repo.update_symbol.assert_called_once_with(
            "AAPL", enabled=None, metadata={"note": "watched"}
        )

    def test_patch_watchlist_symbol_not_found(self, test_client, mock_watchlist_repo):
        """PATCH /api/watchlist/{symbol} for non-existent symbol returns 404."""
        mock_watchlist_repo.update_symbol.return_value = False
        response = test_client.patch(
            "/api/watchlist/NOTEXIST",
            headers=auth_headers(),
            json={"enabled": "false"},
        )
        assert response.status_code == 404

    def test_post_watchlist_bulk_valid(self, test_client, mock_watchlist_repo):
        """POST /api/watchlist/bulk adds multiple symbols."""
        mock_watchlist_repo.bulk_add.return_value = (3, [])
        response = test_client.post(
            "/api/watchlist/bulk",
            headers=auth_headers(),
            json={
                "entries": [
                    {"symbol": "BTC/USDT", "asset_class": "crypto"},
                    {"symbol": "ETH/USDT", "asset_class": "crypto"},
                    {"symbol": "SOL/USDT", "asset_class": "crypto"},
                ],
                "added_by": "agent:momentum",
            },
        )
        assert response.status_code == 201
        assert response.json()["added"] == 3
        mock_watchlist_repo.bulk_add.assert_called_once()

    def test_post_watchlist_bulk_empty(self, test_client, mock_watchlist_repo):
        """POST /api/watchlist/bulk with no entries returns 400."""
        from trading_champs.data.watchlist_repository import ValidationError

        mock_watchlist_repo.bulk_add.side_effect = ValidationError(
            "bulk_add requires at least one entry"
        )
        response = test_client.post(
            "/api/watchlist/bulk",
            headers=auth_headers(),
            json={"entries": []},
        )
        assert response.status_code == 400
