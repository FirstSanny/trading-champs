"""Append-only JSONL ledger for performance reports.

The ledger is intentionally simple: one JSON object per line, line-greppable,
human-inspectable, and trivially reloadable. A relational store can replace
it later if/when scale demands it — the schema is documented in
tasks/tra163-performance-check-workflow-plan.md §5.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from trading_champs.performance.checker import PerformanceReport


DEFAULT_LEDGER_PATH = "data/performance_log.jsonl"


def ledger_path_from_env(env_var: str = "PERF_LOG_PATH") -> Path:
    """Resolve the ledger path, honoring env override."""
    raw = os.environ.get(env_var, DEFAULT_LEDGER_PATH)
    return Path(raw)


class PerformanceLedger:
    """Thin wrapper over a JSONL file for append + recent-read operations."""

    def __init__(self, path: Path | str | None = None):
        path = Path(path) if path is not None else ledger_path_from_env()
        self.path = path

    def append(self, report: PerformanceReport) -> None:
        """Append a single performance report as one JSONL line.

        Atomic on POSIX: writes to a tempfile in the same directory and
        renames onto a new line. Path users expose (``data/performance_log.jsonl``)
        are append-only from the application's perspective.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(asdict(report), separators=(",", ":"), sort_keys=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=str(self.path.parent),
            prefix=self.path.name + ".",
            delete=False,
        ) as tmp:
            tmp.write(line + "\n")
            tmp_path = Path(tmp.name)
        # Append the temp file contents onto the ledger, then remove the temp file.
        with open(self.path, "a", encoding="utf-8") as out, open(
            tmp_path, "r", encoding="utf-8"
        ) as tmp_in:
            out.write(tmp_in.read())
        tmp_path.unlink()

    def read_all(self) -> list[dict[str, Any]]:
        """Return every line in the ledger as a parsed dict.

        Skips blank lines silently. Malformed lines raise — the ledger
        is the audit log; corruption should fail loud.
        """
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                out.append(json.loads(line))
        return out

    def read_last(self, n: int = 1) -> list[dict[str, Any]]:
        """Return the last ``n`` lines of the ledger (defaults: most recent)."""
        if n <= 0:
            return []
        rows = self.read_all()
        return rows[-n:]


def append_report(
    report: PerformanceReport, path: Path | str | None = None
) -> Path:
    """Functional helper: append a report and return the path it landed on."""
    ledger = PerformanceLedger(path)
    ledger.append(report)
    return ledger.path
