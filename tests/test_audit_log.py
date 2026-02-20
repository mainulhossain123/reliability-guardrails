"""
Tests for storage/audit_log.py
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from decision.decision_engine import DecisionResult
from storage.audit_log import AuditLog


def _mock_result(action: str = "ALLOW") -> DecisionResult:
    result = MagicMock(spec=DecisionResult)
    result.action            = action
    result.policy_id         = "P008"
    result.policy_name       = "Test policy"
    result.reason            = "Test reason"
    result.remediation       = "No action"
    result.delay_minutes     = 0
    result.evaluated_policies = []
    result.to_dict.return_value = {
        "action": action, "policy_id": "P008",
        "reason": "Test reason", "remediation": "No action",
        "delay_minutes": 0, "evaluated_policies": [],
    }
    return result


class TestAuditLog:
    def test_write_creates_file(self, tmp_path):
        log = AuditLog(tmp_path)
        path = log.write(_mock_result())
        assert path.exists()

    def test_written_record_is_valid_json(self, tmp_path):
        log = AuditLog(tmp_path)
        path = log.write(_mock_result("BLOCK"))
        line = path.read_text().strip().splitlines()[0]
        record = json.loads(line)
        assert record["action"] == "BLOCK"

    def test_written_record_has_timestamp(self, tmp_path):
        log = AuditLog(tmp_path)
        path = log.write(_mock_result())
        record = json.loads(path.read_text().strip().splitlines()[0])
        assert "timestamp" in record

    def test_multiple_writes_append(self, tmp_path):
        log = AuditLog(tmp_path)
        log.write(_mock_result("ALLOW"))
        log.write(_mock_result("BLOCK"))
        records = log.read_today()
        assert len(records) == 2

    def test_read_today_empty_on_new_dir(self, tmp_path):
        log = AuditLog(tmp_path / "empty")
        assert log.read_today() == []

    def test_log_dir_created_automatically(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        log = AuditLog(nested)
        log.write(_mock_result())
        assert nested.exists()
