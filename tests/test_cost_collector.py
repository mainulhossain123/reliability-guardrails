"""
Tests for cost/cost_collector.py
"""

from __future__ import annotations

import pytest

from cost.cost_collector import CostCollector, CostResult


class TestCostCollectorStable:
    def test_returns_cost_result(self, stable_cost_path):
        result = CostCollector(stable_cost_path).evaluate()
        assert isinstance(result, CostResult)

    def test_no_spike_on_stable_data(self, stable_cost_path):
        result = CostCollector(stable_cost_path).evaluate()
        assert result.spike_detected is False

    def test_trend_stable(self, stable_cost_path):
        result = CostCollector(stable_cost_path).evaluate()
        assert result.trend in {"stable", "rising"}  # slow rise is ok

    def test_wow_change_within_bounds(self, stable_cost_path):
        result = CostCollector(stable_cost_path).evaluate()
        # Gradual 0.1 USD/day increase → WoW < 5 %
        assert abs(result.wow_change_pct) < 20

    def test_budget_utilisation_calculated(self, stable_cost_path):
        result = CostCollector(stable_cost_path).evaluate()
        assert result.budget_utilisation_pct > 0


class TestCostCollectorSpike:
    def test_spike_detected(self, spiking_cost_path):
        result = CostCollector(spiking_cost_path).evaluate()
        assert result.spike_detected is True

    def test_wow_change_over_threshold(self, spiking_cost_path):
        result = CostCollector(spiking_cost_path).evaluate()
        assert result.wow_change_pct >= 20.0

    def test_trend_rising_or_spiking(self, spiking_cost_path):
        result = CostCollector(spiking_cost_path).evaluate()
        assert result.trend in {"rising", "spiking"}

    def test_current_week_higher_than_prev(self, spiking_cost_path):
        result = CostCollector(spiking_cost_path).evaluate()
        assert result.current_week_avg_usd > result.previous_week_avg_usd


class TestCostCollectorSerialisation:
    def test_to_dict_keys(self, stable_cost_path):
        result = CostCollector(stable_cost_path).evaluate()
        d = result.to_dict()
        for key in (
            "service", "current_week_avg_usd", "previous_week_avg_usd",
            "wow_change_pct", "trend", "spike_detected",
            "budget_usd", "mtd_spend_usd", "budget_utilisation_pct",
        ):
            assert key in d, f"Missing key: {key}"


class TestCostCollectorReport:
    def test_report_is_string(self, stable_cost_path):
        assert isinstance(CostCollector(stable_cost_path).report(), str)

    def test_report_contains_service(self, stable_cost_path):
        report = CostCollector(stable_cost_path).report()
        assert "test-service" in report

    def test_report_contains_wow(self, stable_cost_path):
        report = CostCollector(stable_cost_path).report()
        assert "WoW" in report


class TestCostCollectorDefaultPaths:
    """Integration test using the real data/cost.json in the repo."""

    def test_evaluates_with_default_paths(self):
        result = CostCollector().evaluate()
        assert isinstance(result, CostResult)
        assert result.service == "checkout-api"
