"""Watchlist repository for managing trading symbols via Supabase."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

VALID_ASSET_CLASSES = {"crypto", "stock", "etf", "hk"}

SYMBOL_REGEX_CRYPTO = re.compile(r"^[A-Z]{2,10}/[A-Z]{2,10}$")
SYMBOL_REGEX_EQUITY = re.compile(r"^[A-Z]{1,5}$")
SYMBOL_REGEX_HK = re.compile(r"^\d{4}\.HK$")


class ValidationError(Exception):
    """Raised when input validation fails."""

    pass


def validate_symbol(symbol: str, asset_class: str) -> None:
    """Validate symbol format against asset class.

    Args:
        symbol: Trading symbol, e.g. "BTC/USDT" or "AAPL"
        asset_class: One of "crypto", "stock", "etf"

    Raises:
        ValidationError: If symbol format doesn't match asset class.
    """
    if asset_class == "crypto":
        if not SYMBOL_REGEX_CRYPTO.match(symbol):
            raise ValidationError(
                f"Invalid crypto symbol format: '{symbol}'. "
                "Expected format: BTC/USDT (e.g. BTC/USDT, ETH/USDT)"
            )
    elif asset_class in ("stock", "etf"):
        if not SYMBOL_REGEX_EQUITY.match(symbol):
            raise ValidationError(
                f"Invalid {asset_class} symbol format: '{symbol}'. "
                "Expected format: AAPL, SPY (uppercase, 1-5 letters)"
            )
    elif asset_class == "hk":
        if not SYMBOL_REGEX_HK.match(symbol):
            raise ValidationError(
                f"Invalid HK stock symbol format: '{symbol}'. "
                "Expected format: 0005.HK, 0100.HK (4 digits.HK)"
            )
    else:
        raise ValidationError(
            f"Invalid asset_class: '{asset_class}'. "
            f"Must be one of: {', '.join(sorted(VALID_ASSET_CLASSES))}"
        )


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WatchlistEntry:
    """A watchlist symbol entry."""

    id: str
    symbol: str
    asset_class: str
    enabled: bool
    added_by: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "enabled": self.enabled,
            "added_by": self.added_by,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    """Single cache slot for the watchlist cache."""

    entries: list[WatchlistEntry]
    timestamp: float


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class WatchlistRepository:
    """Thread-safe watchlist repository with Supabase backend and TTL cache.

    Symbols are identified by (symbol, deleted_at=NULL) uniqueness.
    Soft-delete sets deleted_at, physically keeping the row for audit.
    """

    DEFAULT_TTL_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        supabase_client: Any | None = None,
        ttl_seconds: int | None = None,
    ):
        """Initialize repository.

        Args:
            supabase_client: Optional SupabaseClient instance. If None, creates one.
            ttl_seconds: Cache TTL in seconds. Default 300 (5 min).
                        Can be overridden by WATCHLIST_CACHE_TTL_SECONDS env var.
        """
        if supabase_client is None:
            from trading_champs.data.supabase_client import get_supabase_client

            self._client = get_supabase_client()
            # Ensure connection is established (singleton calls connect() lazily)
            if not self._client._connected:
                self._client.connect()
        else:
            self._client = supabase_client

        env_ttl = os.environ.get("WATCHLIST_CACHE_TTL_SECONDS")
        self._ttl = (
            ttl_seconds
            if ttl_seconds is not None
            else (int(env_ttl) if env_ttl else self.DEFAULT_TTL_SECONDS)
        )

        self._lock = threading.Lock()
        self._cache: Optional[_CacheEntry] = None
        self._stale_cache: Optional[_CacheEntry] = None
        self._all_entries_cache: Optional[_CacheEntry] = None
        self._all_entries_stale_cache: Optional[_CacheEntry] = None

    # -------------------------------------------------------------------------
    # Cache helpers
    # -------------------------------------------------------------------------

    def _cache_is_valid(self, entry: Optional[_CacheEntry]) -> bool:
        if entry is None:
            return False
        return (time.monotonic() - entry.timestamp) < self._ttl

    def _invalidate_cache(self) -> None:
        with self._lock:
            # Move current cache to stale before replacing
            self._stale_cache = self._cache
            self._cache = None
            self._all_entries_stale_cache = self._all_entries_cache
            self._all_entries_cache = None

    # -------------------------------------------------------------------------
    # Symbol queries
    # -------------------------------------------------------------------------

    def get_enabled_symbols(self) -> list[str]:
        """Get all enabled (non-deleted) symbol strings.

        Returns:
            List of symbol strings, e.g. ["BTC/USDT", "AAPL"].

        Note:
            On DB error with no fresh cache, returns the stale cache
            (if available) and logs a warning.
        """
        # Fast path: cache hit
        with self._lock:
            if self._cache_is_valid(self._cache):
                logger.debug("Watchlist cache hit: %d symbols", len(self._cache.symbols))
                return list(self._cache.symbols)

        # Cache miss or expired — fetch from DB
        try:
            rows = self._client._request(
                "GET",
                "/watchlist_symbols",
                params={
                    "select": "symbol",
                    "enabled": "eq.true",
                    "deleted_at": "is.null",
                    "order": "created_at.asc",
                },
            )
        except Exception as e:
            logger.error("Watchlist DB error (fetching enabled symbols): %s", e)
            # Fall back to stale cache
            with self._lock:
                if self._stale_cache is not None:
                    logger.warning(
                        "Returning stale watchlist cache (%d symbols)",
                        len(self._stale_cache.symbols),
                    )
                    return list(self._stale_cache.symbols)
            return []

        if not isinstance(rows, list):
            logger.warning("Unexpected watchlist response type: %s", type(rows).__name__)
            return []

        symbols = [row["symbol"] for row in rows if row.get("symbol")]

        # Populate cache
        with self._lock:
            self._cache = _CacheEntry(
                entries=symbols,
                timestamp=time.monotonic(),
            )
            self._stale_cache = None

        logger.debug("Watchlist cache miss: fetched %d symbols from DB", len(symbols))
        return list(symbols)

    def get_all_entries(self) -> list[WatchlistEntry]:
        """Get all non-deleted watchlist entries (full detail).

        Returns:
            List of WatchlistEntry objects.
        """
        # Fast path: cache hit
        with self._lock:
            if self._cache_is_valid(self._all_entries_cache):
                logger.debug(
                    "Watchlist all_entries cache hit: %d entries",
                    len(self._all_entries_cache.entries),
                )
                return list(self._all_entries_cache.entries)

        # Cache miss or expired — fetch from DB
        try:
            rows = self._client._request(
                "GET",
                "/watchlist_symbols",
                params={
                    "select": "*",
                    "deleted_at": "is.null",
                    "order": "created_at.asc",
                },
            )
        except Exception as e:
            logger.error("Watchlist DB error (fetching all entries): %s", e)
            # Fall back to stale cache
            with self._lock:
                if self._all_entries_stale_cache is not None:
                    logger.warning(
                        "Returning stale all_entries cache (%d entries)",
                        len(self._all_entries_stale_cache.symbols),  # type: ignore[arg-type]
                    )
                    return list(self._all_entries_stale_cache.symbols)  # type: ignore[arg-type]
            return []

        if not isinstance(rows, list):
            logger.warning("Unexpected watchlist response type: %s", type(rows).__name__)
            return []

        entries: list[WatchlistEntry] = []
        for row in rows:
            try:
                entries.append(
                    WatchlistEntry(
                        id=str(row["id"]),
                        symbol=row["symbol"],
                        asset_class=row["asset_class"],
                        enabled=row.get("enabled", True),
                        added_by=row.get("added_by", "unknown"),
                        metadata=row.get("metadata", {}),
                        created_at=_parse_dt(row.get("created_at")),
                        updated_at=_parse_dt(row.get("updated_at")),
                        deleted_at=None,
                    )
                )
            except Exception as e:
                logger.warning("Skipping malformed watchlist row: %s", e)
                continue

        with self._lock:
            self._all_entries_cache = _CacheEntry(
                entries=list(entries),
                timestamp=time.monotonic(),
            )
            self._all_entries_stale_cache = None

        logger.debug("Watchlist all_entries cache miss: fetched %d entries from DB", len(entries))
        return entries

    def get_by_symbol(self, symbol: str) -> Optional[WatchlistEntry]:
        """Get a single watchlist entry by symbol.

        Args:
            symbol: Trading symbol.

        Returns:
            WatchlistEntry or None if not found.
        """
        try:
            rows = self._client._request(
                "GET",
                "/watchlist_symbols",
                params={
                    "select": "*",
                    "symbol": f"eq.{symbol}",
                    "deleted_at": "is.null",
                    "limit": "1",
                },
            )
        except Exception as e:
            logger.error("Watchlist DB error (get_by_symbol %s): %s", symbol, e)
            return None

        if not isinstance(rows, list) or len(rows) == 0:
            return None

        row = rows[0]
        return WatchlistEntry(
            id=str(row["id"]),
            symbol=row["symbol"],
            asset_class=row["asset_class"],
            enabled=row.get("enabled", True),
            added_by=row.get("added_by", "unknown"),
            metadata=row.get("metadata", {}),
            created_at=_parse_dt(row.get("created_at")),
            updated_at=_parse_dt(row.get("updated_at")),
            deleted_at=None,
        )

    # -------------------------------------------------------------------------
    # Mutations
    # -------------------------------------------------------------------------

    def add_symbol(
        self,
        symbol: str,
        asset_class: str,
        added_by: str = "manual",
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Add a symbol to the watchlist.

        Args:
            symbol: Trading symbol (e.g. "BTC/USDT", "AAPL").
            asset_class: One of "crypto", "stock", "etf".
            added_by: Who/what added this symbol (e.g. "agent:claude").
            metadata: Optional extra data as JSONB.

        Returns:
            True if inserted, False on error or duplicate.
        """
        # Validate
        validate_symbol(symbol, asset_class)
        if asset_class not in VALID_ASSET_CLASSES:
            raise ValidationError(
                f"Invalid asset_class: '{asset_class}'. "
                f"Must be one of: {', '.join(sorted(VALID_ASSET_CLASSES))}"
            )

        data = {
            "symbol": symbol,
            "asset_class": asset_class,
            "enabled": True,
            "added_by": added_by,
            "metadata": metadata or {},
        }

        try:
            result = self._client._request("POST", "/watchlist_symbols", json=data)
            if result is not None:
                self._invalidate_cache()
                logger.info("Watchlist: %s added by %s", symbol, added_by)
                return True
            return False
        except Exception as e:
            # Check for duplicate key (HTTP 409 from Supabase)
            err_str = str(e).lower()
            if "409" in err_str or "duplicate" in err_str or "unique" in err_str:
                logger.warning("Watchlist: duplicate symbol %s", symbol)
                return False
            logger.error("Watchlist DB error (add_symbol %s): %s", symbol, e)
            return False

    def soft_delete(self, symbol: str) -> bool:
        """Soft-delete a symbol from the watchlist (sets deleted_at).

        Idempotent: if already deleted, returns True.

        Args:
            symbol: Trading symbol to remove.

        Returns:
            True if deleted (or already deleted), False if not found.
        """
        # First check if it exists and is not already deleted
        entry = self.get_by_symbol(symbol)
        if entry is None:
            return False

        # Already soft-deleted (shouldn't happen via get_by_symbol but safety first)
        if entry.deleted_at is not None:
            return True

        try:
            result = self._client._request(
                "PATCH",
                "/watchlist_symbols",
                json={"deleted_at": datetime.utcnow().isoformat()},
                params={"id": f"eq.{entry.id}"},
            )
            if result is not None:
                self._invalidate_cache()
                logger.info("Watchlist: %s soft-deleted", symbol)
                return True
            return False
        except Exception as e:
            logger.error("Watchlist DB error (soft_delete %s): %s", symbol, e)
            return False

    def update_symbol(
        self,
        symbol: str,
        enabled: Optional[bool] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Update a symbol's enabled flag and/or metadata.

        Args:
            symbol: Trading symbol to update.
            enabled: New enabled state, or None to skip.
            metadata: New metadata dict, or None to skip.

        Returns:
            True if updated, False if not found.
        """
        entry = self.get_by_symbol(symbol)
        if entry is None:
            return False

        updates: dict[str, Any] = {}
        if enabled is not None:
            updates["enabled"] = enabled
        if metadata is not None:
            updates["metadata"] = metadata

        if not updates:
            return True  # No-op

        try:
            result = self._client._request(
                "PATCH",
                "/watchlist_symbols",
                json=updates,
                params={"id": f"eq.{entry.id}"},
            )
            if result is not None:
                self._invalidate_cache()
                logger.info("Watchlist: %s updated (enabled=%s)", symbol, enabled)
                return True
            return False
        except Exception as e:
            logger.error("Watchlist DB error (update_symbol %s): %s", symbol, e)
            return False

    def bulk_add(
        self,
        entries: list[dict[str, Any]],
        added_by: str = "manual",
    ) -> tuple[int, list[str]]:
        """Add multiple symbols in a single batch.

        Validates ALL entries first; if any fail, none are inserted (all-or-nothing).

        Args:
            entries: List of dicts with keys: symbol, asset_class, metadata (optional).
            added_by: Who/what is adding these symbols.

        Returns:
            Tuple of (success_count, error_messages).

        Raises:
            ValidationError: If any entry fails validation (no inserts attempted).
        """
        if not entries:
            raise ValidationError("bulk_add requires at least one entry")

        # Phase 1: validate all
        validated: list[dict[str, Any]] = []
        errors: list[str] = []

        for i, entry in enumerate(entries):
            sym = entry.get("symbol")
            ac = entry.get("asset_class")
            if not sym or not ac:
                errors.append(f"Entry {i}: missing 'symbol' or 'asset_class'")
                continue
            try:
                validate_symbol(sym, ac)
                validated.append(
                    {
                        "symbol": sym,
                        "asset_class": ac,
                        "added_by": added_by,
                        "metadata": entry.get("metadata", {}),
                    }
                )
            except ValidationError as ve:
                errors.append(f"Entry {i} ({sym}): {ve}")

        if errors:
            raise ValidationError(f"Bulk add validation failed: {'; '.join(errors)}")

        # Phase 2: insert all via multiple POST calls (Supabase doesn't support bulk INSERT)
        # We still validate all first so we don't partially insert
        success_count = 0
        insert_errors: list[str] = []

        for v in validated:
            try:
                ok = self._add_symbol_no_invalidate(
                    v["symbol"], v["asset_class"], v["added_by"], v["metadata"]
                )
            except Exception as e:
                logger.error("Watchlist bulk_add: %s failed — %s", v["symbol"], e)
                ok = False
            if ok:
                success_count += 1
            else:
                insert_errors.append(f"{v['symbol']} (insert failed)")

        if insert_errors:
            logger.warning(
                "Watchlist bulk_add: %d succeeded, %d failed: %s",
                success_count,
                len(insert_errors),
                insert_errors,
            )

        # Invalidate once after all inserts
        if success_count > 0:
            self._invalidate_cache()
            logger.info("Watchlist bulk_add: %d symbols added by %s", success_count, added_by)

        return success_count, insert_errors

    # Internal helper — adds without invalidating cache (caller must invalidate)
    def _add_symbol_no_invalidate(
        self,
        symbol: str,
        asset_class: str,
        added_by: str,
        metadata: dict[str, Any],
    ) -> bool:
        data = {
            "symbol": symbol,
            "asset_class": asset_class,
            "enabled": True,
            "added_by": added_by,
            "metadata": metadata,
        }
        try:
            result = self._client._request("POST", "/watchlist_symbols", json=data)
            return result is not None
        except ConnectionError as e:
            logger.error("Watchlist: connection error adding %s: %s", symbol, e)
            return False
        except Exception as e:
            err_str = str(e).lower()
            logger.error("Watchlist: error adding %s: %s (%s)", symbol, type(e).__name__, e)
            if (
                "409" in err_str
                or "duplicate" in err_str
                or "unique" in err_str
                or "23505" in str(e)
            ):
                logger.warning("Watchlist: duplicate symbol %s", symbol)
            return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        # Supabase returns ISO 8601 strings
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_watchlist_repo: Optional[WatchlistRepository] = None
_watchlist_lock = threading.Lock()


def get_watchlist_repository() -> WatchlistRepository:
    """Get or create the WatchlistRepository singleton (thread-safe)."""
    global _watchlist_repo
    if _watchlist_repo is None:
        with _watchlist_lock:
            if _watchlist_repo is None:
                _watchlist_repo = WatchlistRepository()
    return _watchlist_repo
