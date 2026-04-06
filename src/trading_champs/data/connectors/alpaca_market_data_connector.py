"""Alpaca Market Data API connector for fetching 4H equity OHLCV bars."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import List, Optional

import requests

from trading_champs.data.connectors.base import BaseConnector, PriceBar

logger = logging.getLogger(__name__)

ALPACA_DATA_API = os.getenv("ALPACA_DATA_API", "https://data.alpaca.markets/v2")
DRIFT_WINDOW_BARS = 10  # bars for drift comparison window


def _get_alpaca_data_headers() -> dict:
    """Get headers for Alpaca Data API.

    Alpaca trading API keys work for both trading and market data APIs.
    Supports both the dedicated data key env vars and the trading key env vars.
    """
    api_key = (
        os.getenv("ALPACA_DATA_API_KEY")
        or os.getenv("ALPACA_PAPER_API_KEY")
        or os.getenv("ALPACA_LIVE_API_KEY")
        or ""
    )
    api_secret = (
        os.getenv("ALPACA_DATA_API_SECRET")
        or os.getenv("ALPACA_PAPER_API_SECRET")
        or os.getenv("ALPACA_LIVE_API_SECRET")
        or ""
    )
    return {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }


def _timeframe_to_alpaca(timeframe: str) -> str:
    """Convert generic timeframe to Alpaca Data API timeframe string.

    Args:
        timeframe: Generic timeframe (e.g., '4h', '1h', '1d')

    Returns:
        Alpaca API timeframe string (e.g., '4Hour', '1Min', '1Day')
    """
    mapping = {
        "1m": "1Min",
        "5m": "5Min",
        "15m": "15Min",
        "1h": "1Hour",
        "4h": "4Hour",
        "1d": "1Day",
    }
    return mapping.get(timeframe.lower(), timeframe)


class AlpacaMarketDataConnector(BaseConnector):
    """Connector for Alpaca Market Data API ( equities OHLCV).

    Fetches 4H bar data for US equities (AAPL, MSFT, SPY, TSLA, etc.)
    from the Alpaca Data API v2. This is separate from the Alpaca Trading API.
    """

    def __init__(self, config: Optional[dict] = None):
        """Initialize Alpaca Market Data connector.

        Args:
            config: Optional configuration dict.
        """
        super().__init__(config or {})
        self._headers = _get_alpaca_data_headers()
        self._connected = False

    @property
    def name(self) -> str:
        return "alpaca-market-data"

    def connect(self) -> None:
        """Verify API credentials with a lightweight request."""
        if not self._headers.get("APCA-API-KEY-ID"):
            raise ConnectionError("Alpaca Data API key not configured (ALPACA_DATA_API_KEY)")
        if not self._headers.get("APCA-API-SECRET-KEY"):
            raise ConnectionError("Alpaca Data API secret not configured (ALPACA_DATA_API_SECRET)")

        # Test with a simple request
        test_params: dict[str, str | int] = {"symbols": "AAPL", "limit": 1}
        try:
            resp = requests.get(
                f"{ALPACA_DATA_API}/bars",
                params=test_params,
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            self._connected = True
            logger.info("Connected to Alpaca Market Data API")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 403:
                raise ConnectionError("Alpaca Data API key invalid or no data subscription")
            logger.error(
                "Alpaca Data API HTTPError during connect: status=%s body=%s",
                e.response.status_code if e.response is not None else "unknown",
                e.response.text[:200] if e.response is not None else "no response",
            )
            raise ConnectionError(f"Alpaca Data API connection failed: {e}")
        except requests.exceptions.Timeout:
            logger.error("Alpaca Data API connection timed out to %s", ALPACA_DATA_API)
            raise ConnectionError(f"Alpaca Data API connection timed out to {ALPACA_DATA_API}")
        except requests.exceptions.ConnectionError as e:
            logger.error("Alpaca Data API connection error (network reachability): %s", e)
            raise ConnectionError(f"Alpaca Data API unreachable: {e}")
        except Exception as e:
            logger.error("Alpaca Data API unexpected connect error: %s", e)
            raise ConnectionError(f"Alpaca Data API connection failed: {e}")

    def disconnect(self) -> None:
        """Close connection."""
        self._connected = False
        logger.info("Disconnected from Alpaca Market Data API")

    def is_connected(self) -> bool:
        return self._connected

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "4h",
        since: Optional[int] = None,
        limit: int = 100,
    ) -> List[PriceBar]:
        """Fetch OHLCV bars for a symbol from Alpaca Market Data API.

        Args:
            symbol: Equity symbol (e.g., 'AAPL', 'MSFT').
            timeframe: Timeframe string ('4h', '1h', '1d', etc.). Defaults to '4h'.
            since: Unix timestamp to fetch bars since (optional).
            limit: Max number of bars to return (1-1000, default 100).

        Returns:
            List of PriceBar objects, oldest first.
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to Alpaca Market Data API")

        params: dict[str, str | int | None] = {
            "symbols": symbol.upper(),
            "timeframe": _timeframe_to_alpaca(timeframe),
            "limit": min(limit, 1000),
        }

        if since is not None:
            start = datetime.fromtimestamp(since, tz=timezone.utc)
            params["start"] = start.isoformat()

        for attempt in range(3):
            try:
                resp = requests.get(
                    f"{ALPACA_DATA_API}/bars",
                    params=params,
                    headers=self._headers,
                    timeout=15,
                )

                if resp.status_code == 429:
                    # Rate limited — retry with backoff
                    wait_time = 2**attempt
                    logger.warning(f"Alpaca Data API rate limited, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue

                resp.raise_for_status()
                data = resp.json()

                bars = data.get("bars", {}).get(symbol.upper(), [])
                return self._parse_bars(symbol, bars)

            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    wait_time = 2**attempt
                    logger.warning(f"Alpaca Data API rate limited, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                logger.error(f"HTTP error fetching bars for {symbol}: {e}")
                raise
            except Exception as e:
                logger.error(f"Error fetching bars for {symbol}: {e}")
                raise

        raise ConnectionError(f"Alpaca Data API rate limited after 3 retries for {symbol}")

    def _parse_bars(self, symbol: str, raw_bars: list) -> List[PriceBar]:
        """Parse raw Alpaca bars into PriceBar objects.

        Args:
            symbol: Symbol name.
            raw_bars: List of raw bar dicts from Alpaca API.

        Returns:
            List of PriceBar objects, oldest first.
        """
        result: List[PriceBar] = []
        for bar in raw_bars:
            try:
                # Alpaca returns ISO8601 timestamps
                ts = bar.get("t", "")
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                elif isinstance(ts, (int, float)):
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                else:
                    dt = datetime.now(timezone.utc)

                price_bar = PriceBar(
                    symbol=symbol,
                    timestamp=dt,
                    open=float(bar.get("o", 0)),
                    high=float(bar.get("h", 0)),
                    low=float(bar.get("l", 0)),
                    close=float(bar.get("c", 0)),
                    volume=float(bar.get("v", 0)),
                    quote_volume=(
                        float(bar.get("vw", 0)) * float(bar.get("v", 0)) if bar.get("vw") else None
                    ),
                )
                result.append(price_bar)
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping malformed bar for {symbol}: {bar}, error: {e}")
                continue
        return result

    def fetch_ticker(self, symbol: str) -> dict:
        """Fetch latest ticker for a symbol.

        Args:
            symbol: Equity symbol (e.g., 'AAPL').

        Returns:
            Dict with latest quote data.
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to Alpaca Market Data API")

        try:
            resp = requests.get(
                f"{ALPACA_DATA_API}/stocks/{symbol.upper()}/quotes/latest",
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            q = data.get("quote", {})
            return {
                "symbol": symbol.upper(),
                "bid": float(q.get("bp", 0)),
                "ask": float(q.get("ap", 0)),
                "last": float(q.get("ap", q.get("bp", 0))),
                "volume": float(q.get("v", 0)),
            }
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            raise

    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict:
        """Fetch order book for a symbol (not supported by Alpaca Data API)."""
        raise NotImplementedError(
            "Alpaca Market Data API does not support order book snapshots. "
            "Use a Level 2 data provider for order book data."
        )
