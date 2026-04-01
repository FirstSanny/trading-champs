"""Supabase client for P&L data persistence."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional

from supabase import Client, create_client

from trading_champs.pl.tracker import Trade, TradeSide

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Supabase client wrapper for P&L data storage."""

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
        self._client: Optional[Client] = None

    def connect(self) -> bool:
        """Connect to Supabase.

        Returns:
            True if connected successfully.
        """
        if not self.url or not self.anon_key:
            logger.warning("Supabase credentials not configured")
            return False

        try:
            self._client = create_client(self.url, self.anon_key)
            logger.info("Connected to Supabase")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Supabase: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Supabase."""
        self._client = None

    def is_connected(self) -> bool:
        """Check if connected to Supabase."""
        return self._client is not None

    def _get_table(self, table_name: str):
        """Get a table reference."""
        if not self._client:
            raise ConnectionError("Supabase not connected")
        return self._client.table(table_name)

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
                "side": trade.side.value if hasattr(trade.side, "value") else str(trade.side),
                "quantity": trade.quantity,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "entry_time": trade.entry_time.isoformat() if isinstance(trade.entry_time, datetime) else trade.entry_time,
                "exit_time": trade.exit_time.isoformat() if isinstance(trade.exit_time, datetime) else trade.exit_time,
                "pnl": trade.pnl,
                "pnl_percent": trade.pnl_percent,
                "strategy": getattr(trade, "strategy", None),
                "status": "open" if trade.exit_price is None else "closed",
            }
            self._get_table("trades").upsert(data).execute()
            return True
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
            query = self._get_table("trades").select("*").order("entry_time", desc=True).limit(limit)
            if status:
                query = query.eq("status", status)
            response = query.execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get trades from Supabase: {e}")
            return []

    def get_trade_by_id(self, trade_id: str) -> Optional[dict]:
        """Get a trade by ID."""
        try:
            response = self._get_table("trades").select("*").eq("id", trade_id).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to get trade from Supabase: {e}")
            return None

    def update_trade(self, trade_id: str, updates: dict) -> bool:
        """Update a trade in Supabase.

        Args:
            trade_id: ID of the trade to update.
            updates: Dictionary of fields to update.

        Returns:
            True if updated successfully.
        """
        try:
            self._get_table("trades").update(updates).eq("id", trade_id).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to update trade in Supabase: {e}")
            return False

    def delete_trade(self, trade_id: str) -> bool:
        """Delete a trade from Supabase."""
        try:
            self._get_table("trades").delete().eq("id", trade_id).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to delete trade from Supabase: {e}")
            return False

    # -------------------------------------------------------------------------
    # Daily P&L persistence
    # -------------------------------------------------------------------------

    def save_daily_pnl(self, date: str, realized_pnl: float, unrealized_pnl: float, trade_count: int, win_count: int, loss_count: int) -> bool:
        """Save daily P&L summary.

        Args:
            date: Date string (YYYY-MM-DD).
            realized_pnl: Realized P&L for the day.
            unrealized_pnl: Unrealized P&L for the day.
            trade_count: Number of trades.
            win_count: Number of winning trades.
            loss_count: Number of losing trades.

        Returns:
            True if saved successfully.
        """
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
            self._get_table("daily_pnl").upsert(data).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to save daily P&L to Supabase: {e}")
            return False

    def get_daily_pnl(self, start_date: str, end_date: str) -> list[dict]:
        """Get daily P&L for a date range.

        Args:
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            List of daily P&L dictionaries.
        """
        try:
            response = (
                self._get_table("daily_pnl")
                .select("*")
                .gte("date", start_date)
                .lte("date", end_date)
                .order("date", desc=False)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get daily P&L from Supabase: {e}")
            return []

    # -------------------------------------------------------------------------
    # Account balance persistence
    # -------------------------------------------------------------------------

    def save_account_balance(self, balance: float, equity: float, mode: str = "paper") -> bool:
        """Save account balance snapshot.

        Args:
            balance: Current cash balance.
            equity: Total equity.
            mode: Trading mode ('paper' or 'live').

        Returns:
            True if saved successfully.
        """
        try:
            data = {
                "balance": balance,
                "equity": equity,
                "mode": mode,
                "recorded_at": datetime.utcnow().isoformat(),
            }
            self._get_table("account_balances").insert(data).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to save account balance to Supabase: {e}")
            return False

    def get_latest_balance(self, mode: str = "paper") -> Optional[dict]:
        """Get the latest balance for a mode."""
        try:
            response = (
                self._get_table("account_balances")
                .select("*")
                .eq("mode", mode)
                .order("recorded_at", desc=True)
                .limit(1)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to get latest balance from Supabase: {e}")
            return None


# Singleton instance
_supabase_client: Optional[SupabaseClient] = None


def get_supabase_client() -> SupabaseClient:
    """Get or create the Supabase client singleton."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
        _supabase_client.connect()
    return _supabase_client
