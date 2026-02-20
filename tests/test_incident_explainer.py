"""
Tests for ai/incident_explainer.py
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai.incident_explainer import IncidentExplainer
from decision.decision_engine import DecisionResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_result(action: str = "BLOCK") -> DecisionResult:
    from unittest.mock import MagicMock
    from slo.slo_engine import SLOResult
    from cost.cost_collector import CostResult

    slo = MagicMock(spec=SLOResult)
    slo.availability_pct       = 99.85
    slo.availability_compliant = False
    slo.error_budget_pct       = 8.5
    slo.burn_rate              = "critical"
    slo.burn_rate_value        = 12.5
    slo.latency_p95_ms         = 650
    slo.latency_p99_ms         = 1100
    slo.latency_compliant      = False
    slo.details = {
        "service": "checkout-api",
        "latency_target_p95_ms": 500,
        "availability_target_pct": 99.9,
    }
    slo.to_dict.return_value = {}

    cost = MagicMock(spec=CostResult)
    cost.wow_change_pct         = 35.0
    cost.spike_detected         = True
    cost.trend                  = "spiking"
    cost.current_week_avg_usd   = 63.0
    cost.previous_week_avg_usd  = 46.5
    cost.mtd_spend_usd          = 1420.0
    cost.budget_usd             = 1500.0
    cost.budget_utilisation_pct = 94.7
    cost.to_dict.return_value   = {}

    return DecisionResult(
        action=action,
        policy_id="P001",
        policy_name="Critical error budget exhaustion",
        reason="Error budget critically exhausted",
        remediation="Freeze all deployments. Investigate and fix errors.",
        delay_minutes=0,
        slo=slo,
        cost=cost,
        evaluated_policies=[],
    )


# ── Tests: rule-based backend ─────────────────────────────────────────────────

class TestIncidentExplainerRuleBased:
    def test_returns_string(self):
        explainer = IncidentExplainer()
        result    = _make_result("BLOCK")
        output    = explainer.explain(result)
        assert isinstance(output, str)
        assert len(output) > 100

    def test_contains_action(self):
        output = IncidentExplainer().explain(_make_result("BLOCK"))
        assert "BLOCK" in output

    def test_contains_service_name(self):
        output = IncidentExplainer().explain(_make_result())
        assert "checkout-api" in output

    def test_contains_error_budget(self):
        output = IncidentExplainer().explain(_make_result())
        assert "8.5" in output or "budget" in output.lower()

    def test_contains_recommendation_section(self):
        output = IncidentExplainer().explain(_make_result())
        assert "RECOMMENDED" in output or "Freeze" in output

    def test_contains_reliability_section(self):
        output = IncidentExplainer().explain(_make_result())
        assert "RELIABILITY" in output

    def test_contains_finops_section(self):
        output = IncidentExplainer().explain(_make_result())
        assert "FINOPS" in output or "35" in output

    @pytest.mark.parametrize("action", ["ALLOW", "WARN", "DELAY", "BLOCK"])
    def test_all_actions_produce_output(self, action):
        output = IncidentExplainer().explain(_make_result(action))
        assert action in output

    def test_allow_no_freeze_recommendation(self):
        output = IncidentExplainer().explain(_make_result("ALLOW"))
        # For ALLOW, no freeze recommendation should appear (positive case)
        result = _make_result("ALLOW")
        result.slo.error_budget_pct  = 80.0
        result.slo.burn_rate         = "low"
        result.slo.latency_compliant = True
        result.cost.spike_detected   = False
        result.cost.wow_change_pct   = 2.0
        output = IncidentExplainer().explain(result)
        assert isinstance(output, str)

    def test_delay_includes_delay_info(self):
        result = _make_result("DELAY")
        result.delay_minutes = 30
        output = IncidentExplainer().explain(result)
        assert "DELAY" in output


# ── Tests: backend routing ────────────────────────────────────────────────────

class TestIncidentExplainerBackendRouting:
    def test_default_backend_is_rule_based(self):
        with patch.dict("os.environ", {}, clear=False):
            explainer = IncidentExplainer()
        assert explainer.backend == "rule_based"

    def test_env_overrides_backend(self):
        with patch.dict("os.environ", {"EXPLAINER_BACKEND": "openai"}):
            explainer = IncidentExplainer()
        assert explainer.backend == "openai"

    def test_openai_backend_raises_without_package(self):
        """openai is not installed in the test environment — expect RuntimeError."""
        with patch.dict("os.environ", {"EXPLAINER_BACKEND": "openai"}):
            explainer = IncidentExplainer()
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises((RuntimeError, ImportError)):
                explainer._generate_openai(_make_result())


# ── Tests: LLM prompt builder ─────────────────────────────────────────────────

class TestLLMPromptBuilder:
    def test_prompt_contains_decision_json(self):
        result = _make_result()
        result.to_dict = MagicMock(return_value={"action": "BLOCK"})
        prompt = IncidentExplainer._build_llm_prompt(result)
        assert "BLOCK" in prompt
        assert "SRE" in prompt or "reliability" in prompt.lower()
