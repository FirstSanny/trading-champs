"""Dry-run trading connector that simulates fills with configurable slippage."""

import logging
import os
from datetime import datetime
from typing import Any, Optional

from trading_champs.data.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

DEFAULT_SLIPPAGE = 0.001  # 0.1%


class DryRunConnector(BaseConnector):
    """Simulates trading connector for dry-run/backtesting.

    - No API credentials required
    - Positions tracked in-memory
    - Orders fill immediately with configurable slippage
    - Buy orders fill at price * (1 + slippage)
      Sell orders fill at price * (1 - slippage)
    """

    def __init__(self, config: Optional[dict] = None, slippage_pct: float = DEFAULT_SLIPPAGE):
        super().__init__(config or {})
        self.mode = "dry_run"

        env_slippage = os.getenv("DRY_RUN_SLIPPAGE_PCT")
        self.slippage_pct = float(env_slippage) if env_slippage else slippage_pct

        self._positions: dict[str, dict] = {}
        self._connected = True
        self._order_counter = 0

    @property
    def name(self) -> str:
        return "dry-run"

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _apply_slippage(self, price: float, side: str) -> float:
        if side == "buy":
            return price * (1 + self.slippage_pct)
        else:
            return price * (1 - self.slippage_pct)

    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> dict[str, Any]:
        self._order_counter += 1
        order_id = f"dr_order_{self._order_counter}"
        created_at = datetime.now().isoformat()

        if not limit_price or limit_price <= 0:
            logger.warning(f"Dry-run order rejected for {symbol}: no valid limit_price")
            return {
                "id": order_id,
                "status": "rejected",
                "symbol": symbol,
                "side": side,
                "qty": str(qty),
                "filled_qty": "0",
                "filled_avg_price": None,
                "created_at": created_at,
                "message": "Dry-run rejected: no limit_price",
            }

        filled_price = self._apply_slippage(limit_price, side)

        result = {
            "id": order_id,
            "status": "filled",
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "filled_qty": str(qty),
            "filled_avg_price": str(filled_price),
            "created_at": created_at,
            "filled_at": created_at,
        }

        logger.info(
            f"Dry-run order filled: {side} {qty} {symbol} @ {filled_price} "
            f"(slippage_pct={self.slippage_pct})"
        )

        self._update_position(symbol, qty, side, filled_price)

        return result

    def _update_position(self, symbol: str, qty: float, side: str, price: float) -> None:
        if symbol not in self._positions:
            self._positions[symbol] = {"qty": 0.0, "avg_price": 0.0}

        pos = self._positions[symbol]
        if side == "buy":
            total_cost = pos["qty"] * pos["avg_price"] + qty * price
            pos["qty"] += qty
            pos["avg_price"] = total_cost / pos["qty"] if pos["qty"] > 0 else 0.0
        else:
            pos["qty"] -= qty
            if pos["qty"] < 0:
                pos["qty"] = 0.0

    def get_position(self, symbol: str) -> Optional[dict[str, Any]]:
        pos = self._positions.get(symbol)
        if pos is None or pos["qty"] == 0:
            return None
        return {
            "symbol": symbol,
            "qty": str(pos["qty"]),
            "avg_entry_price": str(pos["avg_price"]),
            "side": "long",
        }

    def get_positions(self) -> list[dict[str, Any]]:
        return [
            {"symbol": sym, "qty": str(pos["qty"]), "avg_entry_price": str(pos["avg_price"])}
            for sym, pos in self._positions.items()
            if pos["qty"] != 0
        ]

    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1m", since: Optional[int] = None, limit: int = 100
    ) -> list:
        raise NotImplementedError("DryRunConnector does not provide market data")

    def fetch_ticker(self, symbol: str) -> dict:
        raise NotImplementedError("DryRunConnector does not provide market data")

    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict:
        raise NotImplementedError("DryRunConnector does not provide market data")
