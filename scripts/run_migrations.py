#!/usr/bin/env python3
"""Run all Supabase migrations directly (no API deployment needed)."""
import os
import sys

# Add scripts/ to path so we can import seed_watchlist_api
sys.path.insert(0, os.path.dirname(__file__))

from seed_watchlist_api import run_migrations

if __name__ == "__main__":
    supabase_url = os.environ.get("SUPABASE_URL", "")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not service_key:
        print("ERROR: SUPABASE_SERVICE_KEY is not set")
        sys.exit(1)

    print("Applying Supabase migrations...")
    if not run_migrations(supabase_url, service_key):
        print("ERROR: migrations failed")
        sys.exit(1)

    print("Done.")