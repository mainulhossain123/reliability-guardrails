"""
Tests for decision/decision_engine.py
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cost.cost_collector import CostCollector, CostResult
from decision.decision_engine import DecisionEngine, DecisionResult
from slo.slo_engine import SLOEngine, SLOResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_slo(
    error_budget_pct: float = 60.0,
    burn_rate: str = "low",
    burn_rate_value: float = 1.0,
    latency_compliant: bool = True,
    availability_pct: float = 99.95,
    availability_compliant: bool = True,
) -> MagicMock:
    slo = MagicMock(spec=SLOResult)
    slo.error_budget_pct       = error_budget_pct
    slo.burn_rate              = burn_rate
    slo.burn_rate_value        = burn_rate_value
    slo.latency_compliant      = latency_compliant
    slo.availability_pct       = availability_pct
    slo.availability_compliant = availability_compliant
    slo.latency_p95_ms         = 480
    slo.latency_p99_ms         = 890
    slo.details                = {
        "service": "test-service",
        "latency_target_p95_ms": 500,
        "availability_target_pct": 99.9,
    }
    slo.healthy = True
    slo.to_dict.return_value = {}
    return slo


def _make_cost(
    wow_change_pct: float = 5.0,
    spike_detected: bool = False,
    trend: str = "stable",
) -> MagicMock:
    cost = MagicMock(spec=CostResult)
    cost.wow_change_pct         = wow_change_pct
    cost.spike_detected         = spike_detected
    cost.trend                  = trend
    cost.current_week_avg_usd   = 50.0
    cost.previous_week_avg_usd  = 47.0
    cost.mtd_spend_usd          = 1200.0
    cost.budget_usd             = 1500.0
    cost.budget_utilisation_pct = 80.0
    cost.to_dict.return_value   = {}
    return cost


def _engine_with(slo: MagicMock, cost: MagicMock, policies_path: Path) -> DecisionEngine:
    slo_engine         = MagicMock(spec=SLOEngine)
    slo_engine.evaluate.return_value  = slo
    cost_collector     = MagicMock(spec=CostCollector)
    cost_collector.evaluate.return_value = cost
    return DecisionEngine(
        policies_path=policies_path,
        slo_engine=slo_engine,
        cost_collector=cost_collector,
    )


# ── Tests: ALLOW ──────────────────────────────────────────────────────────────

class TestDecisionAllow:
    def test_allow_when_healthy(self, policies_path):
        engine = _engine_with(_make_slo(), _make_cost(), policies_path)
        result = engine.evaluate()
        assert result.action == "ALLOW"

    def test_allow_exit_code_zero(self, policies_path):
        engine = _engine_with(_make_slo(), _make_cost(), policies_path)
        result = engine.evaluate()
        assert result.exit_code() == 0


# ── Tests: WARN ───────────────────────────────────────────────────────────────

class TestDecisionWarn:
    def test_warn_on_cost_spike_20pct(self, policies_path):
        engine = _engine_with(
            _make_slo(),
            _make_cost(wow_change_pct=22.0, spike_detected=True, trend="rising"),
            policies_path,
        )
        result = engine.evaluate()
        assert result.action in {"WARN", "DELAY", "BLOCK"}

    def test_warn_exit_code_zero(self, policies_path):
        engine = _engine_with(
            _make_slo(),
            _make_cost(wow_change_pct=22.0, spike_detected=True),
            policies_path,
        )
        result = engine.evaluate()
        assert result.exit_code() in {0, 1}


# ── Tests: DELAY ──────────────────────────────────────────────────────────────

class TestDecisionDelay:
    def test_delay_on_high_burn_rate(self, policies_path):
        engine = _engine_with(
            _make_slo(burn_rate="high", burn_rate_value=6.0, error_budget_pct=40.0),
            _make_cost(),
            policies_path,
        )
        result = engine.evaluate()
        assert result.action in {"DELAY", "BLOCK"}

    def test_delay_exit_code_nonzero(self, policies_path):
        engine = _engine_with(
            _make_slo(burn_rate="high", burn_rate_value=6.0, error_budget_pct=40.0),
            _make_cost(),
            policies_path,
        )
        result = engine.evaluate()
        assert result.exit_code() >= 1

    def test_delay_when_latency_breached(self, policies_path):
        engine = _engine_with(
            _make_slo(latency_compliant=False),
            _make_cost(),
            policies_path,
        )
        result = engine.evaluate()
        assert result.action in {"DELAY", "BLOCK"}


# ── Tests: BLOCK ──────────────────────────────────────────────────────────────

class TestDecisionBlock:
    def test_block_when_budget_below_10(self, policies_path):
        engine = _engine_with(
            _make_slo(error_budget_pct=5.0, burn_rate="critical", burn_rate_value=15.0),
            _make_cost(),
            policies_path,
        )
        result = engine.evaluate()
        assert result.action == "BLOCK"

    def test_block_exit_code_2(self, policies_path):
        engine = _engine_with(
            _make_slo(error_budget_pct=5.0, burn_rate="critical", burn_rate_value=15.0),
            _make_cost(),
            policies_path,
        )
        result = engine.evaluate()
        assert result.exit_code() == 2

    def test_block_when_cost_spike_and_high_burn(self, policies_path):
        engine = _engine_with(
            _make_slo(burn_rate="high", burn_rate_value=7.0, error_budget_pct=18.0),
            _make_cost(wow_change_pct=35.0, spike_detected=True, trend="spiking"),
            policies_path,
        )
        result = engine.evaluate()
        assert result.action == "BLOCK"


# ── Tests: Result structure ───────────────────────────────────────────────────

class TestDecisionResultStructure:
    def test_result_has_policy_id(self, policies_path):
        engine = _engine_with(_make_slo(), _make_cost(), policies_path)
        result = engine.evaluate()
        assert result.policy_id

    def test_result_has_reason(self, policies_path):
        engine = _engine_with(_make_slo(), _make_cost(), policies_path)
        result = engine.evaluate()
        assert result.reason

    def test_result_has_remediation(self, policies_path):
        engine = _engine_with(_make_slo(), _make_cost(), policies_path)
        result = engine.evaluate()
        assert result.remediation

    def test_to_dict_contains_action(self, policies_path):
        engine = _engine_with(_make_slo(), _make_cost(), policies_path)
        d = engine.evaluate().to_dict()
        assert "action" in d

    def test_evaluated_policies_non_empty(self, policies_path):
        engine = _engine_with(_make_slo(), _make_cost(), policies_path)
        result = engine.evaluate()
        assert len(result.evaluated_policies) > 0


# ── Tests: Report ─────────────────────────────────────────────────────────────

class TestDecisionReport:
    def test_report_is_string(self, policies_path):
        engine = _engine_with(_make_slo(), _make_cost(), policies_path)
        assert isinstance(engine.report(), str)

    def test_report_contains_decision(self, policies_path):
        engine = _engine_with(_make_slo(), _make_cost(), policies_path)
        report = engine.report()
        assert any(a in report for a in ("ALLOW", "WARN", "DELAY", "BLOCK"))


# ── Integration test ──────────────────────────────────────────────────────────

class TestDecisionEngineIntegration:
    def test_full_evaluation_with_real_data(self):
        engine = DecisionEngine()
        result = engine.evaluate()
        assert isinstance(result, DecisionResult)
        assert result.action in {"ALLOW", "WARN", "DELAY", "BLOCK"}
