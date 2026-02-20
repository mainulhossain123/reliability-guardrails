"""
Audit Log — persists every deployment decision to a JSONL file.

Each line is a self-contained JSON record so log files remain
parseable even when very large.

Usage::

    from storage.audit_log import AuditLog
    AuditLog().write(decision_result)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decision.decision_engine import DecisionResult

ROOT        = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data" / "audit"


class AuditLog:
    """Appends deployment decision records to a JSONL audit file."""

    def __init__(self, log_dir: str | Path = DEFAULT_DIR) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _log_path(self) -> Path:
        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        return self.log_dir / f"decisions-{date_str}.jsonl"

    def write(self, result: "DecisionResult") -> Path:
        """Append a decision record and return the log file path."""
        record = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            **result.to_dict(),
        }
        path = self._log_path()
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return path

    def read_today(self) -> list[dict]:
        """Return today's decision records as a list of dicts."""
        path = self._log_path()
        if not path.exists():
            return []
        records = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
