"""Yahoo Finance connector for fetching free equity OHLCV data."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

import requests

from trading_champs.data.connectors.base import BaseConnector, PriceBar

logger = logging.getLogger(__name__)

YAHOO_CHART_API = "https://query1.finance.yahoo.com/v8/finance/chart"

# Map generic timeframes to Yahoo Finance intervals
# Yahoo doesn't have 4h, so we use 1h as the closest approximation
TIMEFRAME_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "1h",  # Yahoo doesn't have 4h — use 1h as closest
    "1d": "1d",
    "1wk": "1wk",
}

# Map generic timeframes to Yahoo Finance range (lookback)
TIMEFRAME_RANGE = {
    "1m": "5d",
    "5m": "5d",
    "15m": "1mo",
    "1h": "2mo",
    "4h": "2mo",  # 100 4h bars ≈ 50 days → 2mo covers it
    "1d": "2y",
    "1wk": "5y",
}


class YahooFinanceConnector(BaseConnector):
    """Free stock data connector using Yahoo Finance public API.

    No API key required. Fetches OHLCV data for US equities.
    Note: Yahoo doesn't support 4h bars — uses 1h as the closest interval.
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config or {})
        self._connected = False
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
        )

    @property
    def name(self) -> str:
        return "yahoo-finance"

    def connect(self) -> None:
        """Verify connectivity with a lightweight request."""
        for attempt in range(3):
            try:
                resp = self._session.get(
                    f"{YAHOO_CHART_API}/AAPL",
                    params={"interval": "1d", "range": "5d"},
                    timeout=15,
                )

                if resp.status_code == 429:
                    wait_time = 2**attempt
                    logger.warning(
                        "Yahoo Finance rate limited during connect, retrying in %ds", wait_time
                    )
                    time.sleep(wait_time)
                    continue

                resp.raise_for_status()
                data = resp.json()
                if "chart" not in data or "result" not in data["chart"]:
                    raise ConnectionError("Yahoo Finance returned unexpected response format")
                if data["chart"]["result"] is None:
                    raise ConnectionError("Yahoo Finance symbol not found: AAPL")
                self._connected = True
                logger.info("Connected to Yahoo Finance")
                return
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    continue
                logger.error(
                    "Yahoo Finance HTTPError during connect: %s %s",
                    e.response.status_code if e.response else "unknown",
                    e.response.text[:200] if e.response else "",
                )
                raise ConnectionError(f"Yahoo Finance connection failed: {e}")
            except requests.exceptions.Timeout:
                logger.error("Yahoo Finance connection timed out")
                raise ConnectionError("Yahoo Finance connection timed out")
            except requests.exceptions.ConnectionError as e:
                logger.error("Yahoo Finance connection error: %s", e)
                raise ConnectionError(f"Yahoo Finance unreachable: {e}")
            except ConnectionError:
                raise
            except Exception as e:
                logger.error("Yahoo Finance unexpected connect error: %s", e)
                raise ConnectionError(f"Yahoo Finance connection failed: {e}")

        # All 3 attempts exhausted
        raise ConnectionError("Yahoo Finance connection failed after 3 attempts")

    def disconnect(self) -> None:
        self._connected = False
        self._session.close()
        logger.info("Disconnected from Yahoo Finance")

    def is_connected(self) -> bool:
        return self._connected

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        since: Optional[int] = None,
        limit: int = 100,
    ) -> List[PriceBar]:
        """Fetch OHLCV bars for a US equity from Yahoo Finance.

        Args:
            symbol: Equity symbol (e.g. 'AAPL', 'MSFT').
            timeframe: Timeframe string ('1m', '5m', '15m', '1h', '4h', '1d', '1wk').
                       Note: '4h' maps to '1h' since Yahoo doesn't support 4h.
            since: Unix timestamp to fetch bars since (optional, Yahoo uses 'period1' internally).
            limit: Max number of bars (1-1000, Yahoo caps at range limit).

        Returns:
            List of PriceBar objects, oldest first.
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to Yahoo Finance")

        yahoo_interval = TIMEFRAME_MAP.get(timeframe, "1d")
        yahoo_range = TIMEFRAME_RANGE.get(timeframe, "1mo")

        params: dict = {
            "interval": yahoo_interval,
            "range": yahoo_range,
        }

        if since is not None:
            # Convert Unix timestamp to Yahoo period1/period2
            params["period1"] = since
            # period2 = now + small buffer
            params["period2"] = since + (60 * 60 * 24 * 365)  # 1 year from since

        for attempt in range(3):
            try:
                resp = self._session.get(
                    f"{YAHOO_CHART_API}/{symbol.upper()}",
                    params=params,
                    timeout=15,
                )

                if resp.status_code == 429:
                    wait_time = 2**attempt
                    logger.warning(f"Yahoo Finance rate limited, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue

                resp.raise_for_status()
                data = resp.json()

                result = data.get("chart", {}).get("result", [])
                if not result or result[0] is None:
                    raise ValueError(f"Symbol not found or delisted: {symbol}")

                entry = result[0]
                timestamps = entry.get("timestamp", [])
                quote = entry.get("indicators", {}).get("quote", [{}])[0]
                volumes = entry.get("indicators", {}).get("quote", [{}])
                volumes = volumes[0] if volumes else {}

                if not timestamps:
                    logger.warning("No timestamp data for %s from Yahoo Finance", symbol)
                    return []

                bars: List[PriceBar] = []
                for i, ts in enumerate(timestamps):
                    try:
                        close = quote.get("close", [])
                        close_val = close[i] if i < len(close) and close[i] is not None else None
                        if close_val is None:
                            continue

                        bars.append(
                            PriceBar(
                                symbol=symbol.upper(),
                                timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
                                open=(
                                    quote.get("open", [])[i]
                                    if i < len(quote.get("open", []))
                                    else close_val
                                ),
                                high=(
                                    quote.get("high", [])[i]
                                    if i < len(quote.get("high", []))
                                    else close_val
                                ),
                                low=(
                                    quote.get("low", [])[i]
                                    if i < len(quote.get("low", []))
                                    else close_val
                                ),
                                close=close_val,
                                volume=(
                                    quote.get("volume", [])[i]
                                    if i < len(quote.get("volume", []))
                                    else 0
                                ),
                            )
                        )
                    except (IndexError, KeyError):
                        continue

                # Trim to limit
                return bars[-limit:] if len(bars) > limit else bars

            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    raise ValueError(f"Symbol not found on Yahoo Finance: {symbol}")
                # Retry on 429 (rate limit) and 5xx (server error) up to max attempts
                if e.response is not None and e.response.status_code in (429, 500, 502, 503, 504):
                    if attempt < 2:
                        wait_time = 2**attempt
                        logger.warning(
                            "Yahoo Finance HTTP %s for %s, retrying in %ds",
                            e.response.status_code,
                            symbol,
                            wait_time,
                        )
                        time.sleep(wait_time)
                        continue
                logger.error("Yahoo Finance HTTP error for %s: %s", symbol, e)
                raise ConnectionError(f"Yahoo Finance request failed: {e}")
            except requests.exceptions.Timeout:
                logger.warning("Yahoo Finance timeout for %s (attempt %d)", symbol, attempt + 1)
                if attempt == 2:
                    raise ConnectionError(f"Yahoo Finance timed out after 3 attempts for {symbol}")
                time.sleep(1)
                continue
            except ConnectionError:
                raise
            except Exception as e:
                logger.error("Yahoo Finance error fetching %s: %s", symbol, e)
                raise ConnectionError(f"Yahoo Finance request failed: {e}")

        return []

    def fetch_ticker(self, symbol: str) -> dict:
        """Fetch current ticker data for a symbol."""
        if not self.is_connected():
            raise ConnectionError("Not connected to Yahoo Finance")

        try:
            resp = self._session.get(
                f"{YAHOO_CHART_API}/{symbol.upper()}",
                params={"interval": "1m", "range": "1d"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if not result or result[0] is None:
                raise ValueError(f"Symbol not found: {symbol}")
            meta = result[0].get("meta", {})
            return {
                "symbol": symbol.upper(),
                "price": meta.get("regularMarketPrice", 0),
                "bid": meta.get("bid", 0),
                "ask": meta.get("ask", 0),
                "volume": meta.get("regularMarketVolume", 0),
            }
        except Exception as e:
            raise ConnectionError(f"Yahoo Finance ticker fetch failed: {e}")

    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict:
        """Order book not available from Yahoo Finance."""
        raise NotImplementedError("Order book is not available from Yahoo Finance")
