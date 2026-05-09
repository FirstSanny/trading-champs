#!/usr/bin/env python3
"""
Standalone script to remove duplicate watchlist entries and enforce unique constraint.
Run this ONCE after migration 005 to clean up any remaining duplicates.

Usage:
    python scripts/cleanup_watchlist_duplicates.py <supabase_project_ref> <service_key>
"""

import sys
import urllib.request
import urllib.error
import json


def cleanup_duplicates(project_ref: str, service_key: str) -> None:
    exec_url = f"https://{project_ref}.supabase.co/rest/v1/rpc/exec_sql"

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    # Step 1: Check for duplicates
    check_sql = """
    SELECT symbol, COUNT(*) as cnt, ARRAY_AGG(id ORDER BY created_at ASC) as ids
    FROM watchlist_symbols WHERE deleted_at IS NULL
    GROUP BY symbol HAVING COUNT(*) > 1;
    """

    payload = json.dumps({"query": check_sql}).encode()
    req = urllib.request.Request(exec_url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:300]}")
        sys.exit(1)

    if not result:
        print("No duplicate entries found - database is clean.")
        return

    print(f"Found {len(result)} symbols with duplicate entries:")
    for r in result:
        print(f"  {r['symbol']}: {r['cnt']} rows")

    # Step 2: Delete duplicates (keep oldest per symbol)
    delete_sql = """
    WITH ranked AS (
        SELECT id, symbol,
               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY created_at ASC) AS rn
        FROM watchlist_symbols
        WHERE deleted_at IS NULL
    ),
    duplicates AS (
        SELECT id FROM ranked WHERE rn > 1
    )
    DELETE FROM watchlist_symbols WHERE id IN (SELECT id FROM duplicates);
    """

    payload = json.dumps({"query": delete_sql}).encode()
    req = urllib.request.Request(exec_url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"Cleanup complete - status {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:300]}")
        sys.exit(1)

    # Step 3: Verify
    payload = json.dumps({"query": check_sql}).encode()
    req = urllib.request.Request(exec_url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        remaining = json.loads(resp.read().decode())

    if remaining:
        print(f"WARNING: {len(remaining)} duplicates still remain!")
        sys.exit(1)
    else:
        print("All duplicates removed successfully.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python cleanup_watchlist_duplicates.py <project_ref> <service_key>")
        print("  project_ref: hbbbxbjyhurrmdwfmnft")
        sys.exit(1)

    project_ref = sys.argv[1]
    service_key = sys.argv[2]
    cleanup_duplicates(project_ref, service_key)
