"""One-time migration of loop state SQLite data to Supabase.

Run this script once to backfill existing state from SQLite into Supabase.
It reads from the local .loop_state.db and per-strategy variants.

Usage:
    python scripts/migrate_loop_state_to_supabase.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def migrate_loop_state(db_path: str, supabase: object, dry_run: bool = False) -> int:
    """Migrate loop_state table rows to Supabase."""
    migrated = 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM loop_state WHERE id = 1")
        row = cursor.fetchone()
        if row is None:
            logger.info("No loop_state row found in %s", db_path)
            return 0

        state_dict = {
            "running": bool(row["running"]),
            "last_run": row["last_run"],
            "last_symbol": row["last_symbol"],
            "last_signal": row["last_signal"],
            "last_action": row["last_action"],
            "consecutive_buy_signals": row["consecutive_buy_signals"],
            "consecutive_sell_signals": row["consecutive_sell_signals"],
            "last_error": row["last_error"],
            "iterations": row["iterations"],
        }

        if dry_run:
            logger.info("[DRY RUN] Would upsert loop_state: %s", state_dict)
        else:
            ok = supabase.save_loop_state(
                strategy_id=None,
                **state_dict,
            )
            if ok:
                logger.info("Migrated loop_state from %s", db_path)
                migrated += 1
            else:
                logger.error("Failed to migrate loop_state from %s", db_path)
    except Exception as e:
        logger.error("Error migrating loop_state from %s: %s", db_path, e)
    finally:
        conn.close()

    return migrated


def migrate_strategy_state(db_path: str, supabase: object, dry_run: bool = False) -> int:
    """Migrate strategy_state table rows to Supabase."""
    migrated = 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM strategy_state")
        rows = cursor.fetchall()
        for row in rows:
            state_dict = {
                "stage": row["stage"],
                "stage_entered_at": row["stage_entered_at"],
                "current_metrics": json.loads(row["current_metrics"]) if row["current_metrics"] else {},
            }

            if dry_run:
                logger.info("[DRY RUN] Would upsert strategy_state %s: %s", row["strategy_id"], state_dict)
            else:
                ok = supabase.save_strategy_state(
                    strategy_id=row["strategy_id"],
                    **state_dict,
                )
                if ok:
                    logger.info("Migrated strategy_state %s from %s", row["strategy_id"], db_path)
                    migrated += 1
                else:
                    logger.error("Failed to migrate strategy_state %s from %s", row["strategy_id"], db_path)
    except Exception as e:
        logger.error("Error migrating strategy_state from %s: %s", db_path, e)
    finally:
        conn.close()

    return migrated


def migrate_stage_history(db_path: str, supabase: object, dry_run: bool = False) -> int:
    """Migrate stage_history table rows to Supabase."""
    migrated = 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM stage_history ORDER BY timestamp ASC")
        rows = cursor.fetchall()
        for row in rows:
            transition_dict = {
                "from_stage": row["from_stage"],
                "to_stage": row["to_stage"],
                "trigger": row["trigger"],
                "metrics_snapshot": json.loads(row["metrics_snapshot"]) if row["metrics_snapshot"] else {},
                "timestamp": row["timestamp"],
                "actor": row["actor"],
                "override_reason": row["override_reason"],
            }

            if dry_run:
                logger.info("[DRY RUN] Would insert stage_history %s: %s", row["strategy_id"], transition_dict)
            else:
                ok = supabase.append_stage_history(
                    strategy_id=row["strategy_id"],
                    **transition_dict,
                )
                if ok:
                    logger.info("Migrated stage_history %s from %s", row["strategy_id"], db_path)
                    migrated += 1
                else:
                    logger.error("Failed to migrate stage_history %s from %s", row["strategy_id"], db_path)
    except Exception as e:
        logger.error("Error migrating stage_history from %s: %s", db_path, e)
    finally:
        conn.close()

    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate loop state SQLite data to Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing to Supabase")
    args = parser.parse_args()

    # Connect to Supabase
    from trading_champs.data.supabase_client import SupabaseClient

    supabase = SupabaseClient()
    if not supabase.connect():
        logger.error("Failed to connect to Supabase — aborting migration")
        sys.exit(1)

    # Migrate main .loop_state.db
    main_db = Path(".loop_state.db")
    total_migrated = 0

    if main_db.exists():
        logger.info("Migrating main database: %s", main_db)
        total_migrated += migrate_loop_state(str(main_db), supabase, args.dry_run)
        total_migrated += migrate_strategy_state(str(main_db), supabase, args.dry_run)
        total_migrated += migrate_stage_history(str(main_db), supabase, args.dry_run)
    else:
        logger.info("Main database not found: %s — skipping", main_db)

    # Migrate per-strategy databases
    strategy_dbs = list(Path(".").glob("_*.db"))
    if strategy_dbs:
        logger.info("Found %d per-strategy databases", len(strategy_dbs))
        for db_file in strategy_dbs:
            logger.info("Migrating: %s", db_file)
            total_migrated += migrate_loop_state(str(db_file), supabase, args.dry_run)
            total_migrated += migrate_strategy_state(str(db_file), supabase, args.dry_run)
            total_migrated += migrate_stage_history(str(db_file), supabase, args.dry_run)
    else:
        logger.info("No per-strategy databases found")

    logger.info("Migration complete — %d rows migrated", total_migrated)
    supabase.disconnect()


if __name__ == "__main__":
    main()
