"""Supabase client for P&L data persistence using direct HTTP REST API."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional, cast

from trading_champs.pl.tracker import Trade

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Supabase client wrapper for P&L data storage using REST API."""

    def __init__(self, config: dict | None = None):
        """Initialize Supabase client.

        Args:
            config: Optional config dict. If not provided, reads from env vars.
        """
        if config is None:
            config = {}
        self.url = config.get("url") or os.environ.get("SUPABASE_URL", "")
        self.anon_key = config.get("anon_key") or os.environ.get("SUPABASE_ANON_KEY", "")
        self.service_key = config.get("service_key") or os.environ.get("SUPABASE_SERVICE_KEY", "")
        self._connected = False

    def connect(self) -> bool:
        """Connect to Supabase.

        Returns:
            True if connected successfully.
        """
        if not self.url or not self.anon_key:
            logger.warning("Supabase credentials not configured")
            return False

        try:
            import requests

            # Test the connection with a lightweight request
            resp = requests.get(
                f"{self.url}/rest/v1/",
                headers={"apikey": self.anon_key, "Authorization": f"Bearer {self.anon_key}"},
                timeout=10,
            )
            if resp.status_code < 500:
                self._connected = True
                logger.info("Connected to Supabase")
                return True
            else:
                logger.error(f"Supabase connection test failed: {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to Supabase: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Supabase."""
        self._connected = False

    def is_connected(self) -> bool:
        """Check if connected to Supabase."""
        return self._connected

    def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
        prefer_service_key: bool = False,
    ) -> dict | list | None:
        """Make a request to Supabase REST API.

        Args:
            method: HTTP method
            path: API path (e.g., "/trades")
            json: JSON body for POST/PATCH/DELETE
            params: Query parameters
            prefer_service_key: Use service key for auth (for write operations)

        Returns:
            Response data or None
        """
        import requests

        if not self._connected:
            raise ConnectionError("Supabase not connected")

        url = f"{self.url}/rest/v1{path}"
        use_key = self.service_key if prefer_service_key else self.anon_key
        headers = {
            "apikey": use_key,
            "Authorization": f"Bearer {use_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

        try:
            resp = requests.request(
                method, url, json=json, params=params, headers=headers, timeout=15
            )
            if resp.status_code >= 400:
                logger.error(
                    "Supabase request failed: %s %s -> %s %s",
                    method,
                    path,
                    resp.status_code,
                    resp.text[:200],
                )
                return None
            if resp.text:
                return cast("dict[Any, Any] | list[Any]", resp.json())
            return None
        except Exception as e:
            logger.error(f"Supabase request error: {e}")
            return None

    # -------------------------------------------------------------------------
    # Trade persistence
    # -------------------------------------------------------------------------

    def save_trade(self, trade: Trade) -> bool:
        """Save a trade to Supabase.

        Args:
            trade: Trade object to save.

        Returns:
            True if saved successfully.
        """
        try:
            data = {
                "id": trade.id,
                "symbol": trade.symbol,
                "side": (trade.side.value if hasattr(trade.side, "value") else str(trade.side)),
                "quantity": trade.quantity,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "entry_time": (
                    trade.entry_time.isoformat()
                    if isinstance(trade.entry_time, datetime)
                    else trade.entry_time
                ),
                "exit_time": (
                    trade.exit_time.isoformat()
                    if isinstance(trade.exit_time, datetime)
                    else trade.exit_time
                ),
                "pnl": trade.pnl,
                "pnl_percent": trade.pnl_percent,
                "strategy": getattr(trade, "strategy", None),
                "status": "open" if trade.exit_price is None else "closed",
            }
            result = self._request("POST", "/trades", json=data)
            return result is not None
        except Exception as e:
            logger.error(f"Failed to save trade to Supabase: {e}")
            return False

    def get_trades(self, status: str | None = None, limit: int = 100) -> list[dict]:
        """Get trades from Supabase.

        Args:
            status: Optional status filter ('open' or 'closed').
            limit: Maximum number of trades to return.

        Returns:
            List of trade dictionaries.
        """
        try:
            params: dict[str, str] = {
                "select": "*",
                "limit": str(limit),
                "order": "entry_time.desc",
            }
            if status:
                params["status"] = f"eq.{status}"
            result = self._request("GET", "/trades", params=params)
            if isinstance(result, list):
                return result
            return []
        except Exception as e:
            logger.error(f"Failed to get trades from Supabase: {e}")
            return []

    def get_trade_by_id(self, trade_id: str) -> Optional[dict]:
        """Get a trade by ID."""
        try:
            result = self._request("GET", "/trades", params={"id": f"eq.{trade_id}", "limit": "1"})
            if isinstance(result, list) and len(result) > 0:
                return cast("dict[Any, Any]", result[0])
            return None
        except Exception as e:
            logger.error(f"Failed to get trade from Supabase: {e}")
            return None

    def update_trade(self, trade_id: str, updates: dict) -> bool:
        """Update a trade in Supabase."""
        try:
            result = self._request(
                "PATCH", "/trades", json=updates, params={"id": f"eq.{trade_id}"}
            )
            return result is not None
        except Exception as e:
            logger.error("Failed to update trade in Supabase: %s", e)
            return False

    def delete_trade(self, trade_id: str) -> bool:
        """Delete a trade from Supabase."""
        try:
            result = self._request("DELETE", "/trades", params={"id": f"eq.{trade_id}"})
            return result is not None
        except Exception as e:
            logger.error("Failed to delete trade from Supabase: %s", e)
            return False

    # -------------------------------------------------------------------------
    # Daily P&L persistence
    # -------------------------------------------------------------------------

    def save_daily_pnl(
        self,
        date: str,
        realized_pnl: float,
        unrealized_pnl: float,
        trade_count: int,
        win_count: int,
        loss_count: int,
    ) -> bool:
        """Save daily P&L summary."""
        try:
            data = {
                "date": date,
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                "total_pnl": realized_pnl + unrealized_pnl,
                "trade_count": trade_count,
                "win_count": win_count,
                "loss_count": loss_count,
            }
            result = self._request("POST", "/daily_pnl", json=data)
            return result is not None
        except Exception as e:
            logger.error(f"Failed to save daily P&L to Supabase: {e}")
            return False

    def get_daily_pnl(self, start_date: str, end_date: str) -> list[dict]:
        """Get daily P&L for a date range."""
        try:
            params = {
                "select": "*",
                "and": f"(date.gte.{start_date},date.lte.{end_date})",
                "order": "date.asc",
            }
            result = self._request(
                "GET",
                "/daily_pnl",
                params=params,
            )
            if isinstance(result, list):
                return result
            return []
        except Exception as e:
            logger.error(f"Failed to get daily P&L from Supabase: {e}")
            return []

    # -------------------------------------------------------------------------
    # Account balance persistence
    # -------------------------------------------------------------------------

    def save_account_balance(self, balance: float, equity: float, mode: str = "paper") -> bool:
        """Save account balance snapshot."""
        try:
            data = {
                "balance": balance,
                "equity": equity,
                "mode": mode,
                "recorded_at": datetime.utcnow().isoformat(),
            }
            result = self._request("POST", "/account_balances", json=data)
            return result is not None
        except Exception as e:
            logger.error(f"Failed to save account balance to Supabase: {e}")
            return False

    def get_latest_balance(self, mode: str = "paper") -> Optional[dict]:
        """Get the latest balance for a mode."""
        try:
            params = {
                "select": "*",
                "mode": f"eq.{mode}",
                "order": "recorded_at.desc",
                "limit": "1",
            }
            result = self._request("GET", "/account_balances", params=params)
            if isinstance(result, list) and len(result) > 0:
                return cast("dict[Any, Any]", result[0])
            return None
        except Exception as e:
            logger.error(f"Failed to get latest balance from Supabase: {e}")
            return None

    # -------------------------------------------------------------------------
    # Loop state persistence
    # -------------------------------------------------------------------------

    def save_loop_state(
        self,
        strategy_id: str | None,
        running: bool,
        last_run: str | None,
        last_symbol: str | None,
        last_signal: str | None,
        last_action: str | None,
        consecutive_buy_signals: int,
        consecutive_sell_signals: int,
        last_error: str | None,
        iterations: int,
    ) -> bool:
        """Upsert a loop state row."""
        data = {
            "id": 1,
            "strategy_id": strategy_id,
            "running": running,
            "last_run": last_run,
            "last_symbol": last_symbol,
            "last_signal": last_signal,
            "last_action": last_action,
            "consecutive_buy_signals": consecutive_buy_signals,
            "consecutive_sell_signals": consecutive_sell_signals,
            "last_error": last_error,
            "iterations": iterations,
        }
        result = self._request(
            "POST",
            "/loop_state",
            json=data,
            params={"strategy_id": f"eq.{strategy_id}"},
            prefer_service_key=True,
        )
        if result is None:
            result = self._request(
                "PATCH",
                "/loop_state",
                json=data,
                params={"strategy_id": f"eq.{strategy_id}"},
                prefer_service_key=True,
            )
        return result is not None

    def get_loop_state(self, strategy_id: str | None) -> dict | None:
        """Get loop state row by strategy_id (null for global loop state)."""
        try:
            params: dict[str, str] = {"limit": "1", "order": "updated_at.desc"}
            if strategy_id is not None:
                params["strategy_id"] = f"eq.{strategy_id}"
            result = self._request("GET", "/loop_state", params=params)
            if isinstance(result, list) and len(result) > 0:
                return cast("dict[Any, Any]", result[0])
            return None
        except Exception as e:
            logger.error(f"Failed to get loop state from Supabase: {e}")
            return None

    # -------------------------------------------------------------------------
    # Strategy state persistence
    # -------------------------------------------------------------------------

    def save_strategy_state(
        self,
        strategy_id: str,
        stage: str,
        stage_entered_at: str,
        current_metrics: dict,
    ) -> bool:
        """Upsert a strategy state row."""
        data = {
            "strategy_id": strategy_id,
            "stage": stage,
            "stage_entered_at": stage_entered_at,
            "current_metrics": current_metrics,
        }
        result = self._request(
            "POST",
            "/strategy_state",
            json=data,
            params={"strategy_id": f"eq.{strategy_id}"},
            prefer_service_key=True,
        )
        if result is None:
            result = self._request(
                "PATCH",
                "/strategy_state",
                json=data,
                params={"strategy_id": f"eq.{strategy_id}"},
                prefer_service_key=True,
            )
        return result is not None

    def get_strategy_state(self, strategy_id: str) -> dict | None:
        """Get strategy state by strategy_id."""
        try:
            result = self._request(
                "GET",
                "/strategy_state",
                params={"strategy_id": f"eq.{strategy_id}", "limit": "1"},
            )
            if isinstance(result, list) and len(result) > 0:
                return cast("dict[Any, Any]", result[0])
            return None
        except Exception as e:
            logger.error(f"Failed to get strategy state from Supabase: {e}")
            return None

    # -------------------------------------------------------------------------
    # Stage history persistence
    # -------------------------------------------------------------------------

    def append_stage_history(
        self,
        strategy_id: str,
        from_stage: str,
        to_stage: str,
        trigger: str,
        metrics_snapshot: dict,
        timestamp: str,
        actor: str,
        override_reason: str | None = None,
    ) -> bool:
        """Append a stage transition record."""
        data = {
            "strategy_id": strategy_id,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "trigger": trigger,
            "metrics_snapshot": metrics_snapshot,
            "timestamp": timestamp,
            "actor": actor,
            "override_reason": override_reason,
        }
        result = self._request("POST", "/stage_history", json=data, prefer_service_key=True)
        return result is not None

    def get_stage_history(self, strategy_id: str, limit: int = 50) -> list[dict]:
        """Get stage history for a strategy ordered by timestamp ASC."""
        try:
            result = self._request(
                "GET",
                "/stage_history",
                params={
                    "strategy_id": f"eq.{strategy_id}",
                    "order": "timestamp.asc",
                    "limit": str(limit),
                },
            )
            if isinstance(result, list):
                return result
            return []
        except Exception as e:
            logger.error(f"Failed to get stage history from Supabase: {e}")
            return []


# Singleton instance
_supabase_client: Optional[SupabaseClient] = None


def get_supabase_client() -> SupabaseClient:
    """Get or create the Supabase client singleton."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
        _supabase_client.connect()
    return _supabase_client
