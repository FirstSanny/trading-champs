"""Integration tests for watchlist API endpoints in api/index.py."""

import os
from unittest.mock import MagicMock, patch

os.environ["API_SECRET"] = "test-secret-key"
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_ANON_KEY"] = ""

from starlette.testclient import TestClient


class TestWatchlistAPI:
    """Tests for /api/watchlist endpoints."""

    def _make_client(self, mock_repo: MagicMock):
        with patch("api.index._watchlist_repo", mock_repo):
            from api.index import app
            return TestClient(app)

    def _auth_headers(self):
        return {"Authorization": "Bearer test-secret-key"}

    # GET /api/watchlist

    def test_get_watchlist_empty(self):
        """GET /api/watchlist with no symbols returns empty list."""
        mock_repo = MagicMock()
        mock_repo.get_all_entries.return_value = []

        client = self._make_client(mock_repo)
        response = client.get("/api/watchlist", headers=self._auth_headers())

        assert response.status_code == 200
        assert response.json()["symbols"] == []

    def test_get_watchlist_with_symbols(self):
        """GET /api/watchlist returns all entries."""
        from datetime import datetime
        from trading_champs.data.watchlist_repository import WatchlistEntry

        mock_repo = MagicMock()
        mock_repo.get_all_entries.return_value = [
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

        client = self._make_client(mock_repo)
        response = client.get("/api/watchlist", headers=self._auth_headers())

        assert response.status_code == 200
        data = response.json()
        assert len(data["symbols"]) == 2
        assert data["symbols"][0]["symbol"] == "BTC/USDT"
        assert data["symbols"][1]["added_by"] == "agent:momentum"

    def test_get_watchlist_requires_auth(self):
        """GET /api/watchlist without auth returns 401."""
        mock_repo = MagicMock()
        client = self._make_client(mock_repo)
        response = client.get("/api/watchlist")
        assert response.status_code == 401

    # POST /api/watchlist

    def test_post_watchlist_valid(self):
        """POST /api/watchlist creates a symbol."""
        mock_repo = MagicMock()
        mock_repo.add_symbol.return_value = True
        mock_repo.get_by_symbol.return_value = MagicMock(to_dict=lambda: {"symbol": "BTC/USDT"})

        client = self._make_client(mock_repo)
        response = client.post(
            "/api/watchlist",
            headers=self._auth_headers(),
            json={"symbol": "BTC/USDT", "asset_class": "crypto"},
        )

        assert response.status_code == 201
        mock_repo.add_symbol.assert_called_once_with(
            "BTC/USDT", "crypto", added_by="manual", metadata={}
        )

    def test_post_watchlist_missing_symbol(self):
        """POST /api/watchlist without symbol returns 400."""
        mock_repo = MagicMock()
        client = self._make_client(mock_repo)
        response = client.post(
            "/api/watchlist",
            headers=self._auth_headers(),
            json={"asset_class": "crypto"},
        )
        assert response.status_code == 400
        assert "required" in response.json()["error"]

    def test_post_watchlist_missing_asset_class(self):
        """POST /api/watchlist without asset_class returns 400."""
        mock_repo = MagicMock()
        client = self._make_client(mock_repo)
        response = client.post(
            "/api/watchlist",
            headers=self._auth_headers(),
            json={"symbol": "AAPL"},
        )
        assert response.status_code == 400

    def test_post_watchlist_invalid_format(self):
        """POST /api/watchlist with bad format returns 400."""
        from trading_champs.data.watchlist_repository import ValidationError

        mock_repo = MagicMock()
        mock_repo.add_symbol.side_effect = ValidationError("Invalid crypto symbol")

        client = self._make_client(mock_repo)
        response = client.post(
            "/api/watchlist",
            headers=self._auth_headers(),
            json={"symbol": "AAPL", "asset_class": "crypto"},
        )
        assert response.status_code == 400
        assert "Invalid crypto" in response.json()["error"]

    def test_post_watchlist_duplicate(self):
        """POST /api/watchlist for existing symbol returns 409."""
        mock_repo = MagicMock()
        mock_repo.add_symbol.return_value = False  # duplicate

        client = self._make_client(mock_repo)
        response = client.post(
            "/api/watchlist",
            headers=self._auth_headers(),
            json={"symbol": "BTC/USDT", "asset_class": "crypto"},
        )
        assert response.status_code == 409

    # DELETE /api/watchlist/{symbol}

    def test_delete_watchlist_symbol_exists(self):
        """DELETE /api/watchlist/{symbol} soft-deletes the symbol."""
        mock_repo = MagicMock()
        mock_repo.soft_delete.return_value = True

        client = self._make_client(mock_repo)
        response = client.delete(
            "/api/watchlist/BTCUSDT",
            headers=self._auth_headers(),
        )

        assert response.status_code == 200
        assert response.json()["symbol"] == "BTCUSDT"
        mock_repo.soft_delete.assert_called_once_with("BTCUSDT")

    def test_delete_watchlist_symbol_not_found(self):
        """DELETE /api/watchlist/{symbol} for non-existent symbol returns 404."""
        mock_repo = MagicMock()
        mock_repo.soft_delete.return_value = False

        client = self._make_client(mock_repo)
        response = client.delete(
            "/api/watchlist/NOTEXIST",
            headers=self._auth_headers(),
        )
        assert response.status_code == 404

    # PATCH /api/watchlist/{symbol}

    def test_patch_watchlist_update_enabled(self):
        """PATCH /api/watchlist/{symbol} updates enabled state."""
        mock_repo = MagicMock()
        mock_repo.update_symbol.return_value = True
        mock_repo.get_by_symbol.return_value = MagicMock(
            to_dict=lambda: {"symbol": "AAPL", "enabled": False}
        )

        client = self._make_client(mock_repo)
        response = client.patch(
            "/api/watchlist/AAPL",
            headers=self._auth_headers(),
            json={"enabled": "false"},
        )

        assert response.status_code == 200
        mock_repo.update_symbol.assert_called_once_with("AAPL", enabled=False, metadata=None)

    def test_patch_watchlist_update_metadata(self):
        """PATCH /api/watchlist/{symbol} updates metadata."""
        mock_repo = MagicMock()
        mock_repo.update_symbol.return_value = True
        mock_repo.get_by_symbol.return_value = MagicMock(
            to_dict=lambda: {"symbol": "AAPL", "metadata": {"note": "watched"}}
        )

        client = self._make_client(mock_repo)
        response = client.patch(
            "/api/watchlist/AAPL",
            headers=self._auth_headers(),
            json={"metadata": {"note": "watched"}},
        )

        assert response.status_code == 200
        mock_repo.update_symbol.assert_called_once_with(
            "AAPL", enabled=None, metadata={"note": "watched"}
        )

    def test_patch_watchlist_symbol_not_found(self):
        """PATCH /api/watchlist/{symbol} for non-existent symbol returns 404."""
        mock_repo = MagicMock()
        mock_repo.update_symbol.return_value = False

        client = self._make_client(mock_repo)
        response = client.patch(
            "/api/watchlist/NOTEXIST",
            headers=self._auth_headers(),
            json={"enabled": "false"},
        )
        assert response.status_code == 404

    # POST /api/watchlist/bulk

    def test_post_watchlist_bulk_valid(self):
        """POST /api/watchlist/bulk adds multiple symbols."""
        mock_repo = MagicMock()
        mock_repo.bulk_add.return_value = (3, [])

        client = self._make_client(mock_repo)
        response = client.post(
            "/api/watchlist/bulk",
            headers=self._auth_headers(),
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
        mock_repo.bulk_add.assert_called_once()

    def test_post_watchlist_bulk_empty(self):
        """POST /api/watchlist/bulk with no entries returns 400."""
        mock_repo = MagicMock()
        from trading_champs.data.watchlist_repository import ValidationError
        mock_repo.bulk_add.side_effect = ValidationError("bulk_add requires at least one entry")

        client = self._make_client(mock_repo)
        response = client.post(
            "/api/watchlist/bulk",
            headers=self._auth_headers(),
            json={"entries": []},
        )

        assert response.status_code == 400
