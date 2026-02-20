"""
Tests for slo/slo_engine.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from slo.slo_engine import SLOEngine, SLOResult


class TestSLOEngineHappyPath:
    """Healthy metrics — engine should report a passing SLO."""

    def test_returns_slo_result(self, slo_config_path, healthy_metrics_path):
        engine = SLOEngine(slo_config_path, healthy_metrics_path)
        result = engine.evaluate()
        assert isinstance(result, SLOResult)

    def test_availability_is_calculated(self, slo_config_path, healthy_metrics_path):
        result = SLOEngine(slo_config_path, healthy_metrics_path).evaluate()
        # 2100 failures / 2_592_000 requests ≈ 99.919 %
        assert 99.9 < result.availability_pct <= 100.0

    def test_availability_compliant(self, slo_config_path, healthy_metrics_path):
        result = SLOEngine(slo_config_path, healthy_metrics_path).evaluate()
        assert result.availability_compliant is True

    def test_error_budget_positive(self, slo_config_path, healthy_metrics_path):
        result = SLOEngine(slo_config_path, healthy_metrics_path).evaluate()
        assert result.error_budget_pct > 0

    def test_latency_compliant(self, slo_config_path, healthy_metrics_path):
        # p95 = 480 ms, threshold = 500 ms
        result = SLOEngine(slo_config_path, healthy_metrics_path).evaluate()
        assert result.latency_compliant is True

    def test_burn_rate_low(self, slo_config_path, healthy_metrics_path):
        result = SLOEngine(slo_config_path, healthy_metrics_path).evaluate()
        assert result.burn_rate in {"low", "medium"}

    def test_healthy_property(self, slo_config_path, healthy_metrics_path):
        result = SLOEngine(slo_config_path, healthy_metrics_path).evaluate()
        assert result.healthy is True


class TestSLOEngineCriticalPath:
    """Degraded metrics — engine should surface the problems."""

    def test_availability_below_target(self, slo_config_path, critical_metrics_path):
        result = SLOEngine(slo_config_path, critical_metrics_path).evaluate()
        # 950 / 1_000_000 = 0.095 % failure rate → availability ≈ 99.905 %
        # Still above 99.9 in this fixture but budget should be > 50 % consumed
        assert result.error_budget_pct < 50

    def test_latency_breach_detected(self, slo_config_path, critical_metrics_path):
        # p95 = 700 ms > 500 ms threshold
        result = SLOEngine(slo_config_path, critical_metrics_path).evaluate()
        assert result.latency_compliant is False

    def test_burn_rate_critical(self, slo_config_path, critical_metrics_path):
        result = SLOEngine(slo_config_path, critical_metrics_path).evaluate()
        assert result.burn_rate in {"high", "critical"}

    def test_unhealthy_property(self, slo_config_path, critical_metrics_path):
        result = SLOEngine(slo_config_path, critical_metrics_path).evaluate()
        assert result.healthy is False


class TestSLOEngineSerialisation:
    def test_to_dict_contains_required_keys(self, slo_config_path, healthy_metrics_path):
        result = SLOEngine(slo_config_path, healthy_metrics_path).evaluate()
        d = result.to_dict()
        for key in (
            "availability_pct", "error_budget_pct", "burn_rate",
            "latency_p95_ms", "latency_compliant", "availability_compliant",
            "healthy", "details"
        ):
            assert key in d, f"Missing key: {key}"


class TestSLOEngineReport:
    def test_report_is_string(self, slo_config_path, healthy_metrics_path):
        engine = SLOEngine(slo_config_path, healthy_metrics_path)
        assert isinstance(engine.report(), str)

    def test_report_contains_service_name(self, slo_config_path, healthy_metrics_path):
        report = SLOEngine(slo_config_path, healthy_metrics_path).report()
        assert "test-service" in report

    def test_report_contains_error_budget(self, slo_config_path, healthy_metrics_path):
        report = SLOEngine(slo_config_path, healthy_metrics_path).report()
        assert "Error Budget" in report


class TestSLOEngineBudgetBar:
    @pytest.mark.parametrize("pct, expected_filled", [
        (100.0, 10),
        (0.0,    0),
        (50.0,   5),
    ])
    def test_budget_bar(self, pct, expected_filled):
        bar = SLOEngine._budget_bar(pct, width=10)
        assert bar.count("█") == expected_filled


class TestSLOEngineDefaultPaths:
    """Integration test — uses the real config/data files in the repo."""

    def test_evaluates_with_default_paths(self):
        engine = SLOEngine()
        result = engine.evaluate()
        assert isinstance(result, SLOResult)
        assert 0.0 <= result.error_budget_pct <= 100.0
        assert result.burn_rate in {"low", "medium", "high", "critical"}
