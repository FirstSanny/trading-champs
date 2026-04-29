"""Pytest configuration for tests."""

import os

# Set test environment variables before any test modules are imported.
# These must be set before api.index is loaded (which reads these vars at import time).
os.environ.setdefault("API_SECRET", "test-secret-key")
os.environ.setdefault("SUPABASE_URL", "")
os.environ.setdefault("SUPABASE_ANON_KEY", "")
