"""
Shared pytest fixtures for the reliability-guardrails test suite.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml


# ── SLO fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture()
def slo_config_path(tmp_path: Path) -> Path:
    """Write a minimal slos.yaml to a temp dir and return the path."""
    cfg = {
        "slos": {
            "availability": {"target": 99.9, "window_days": 30},
            "latency": {"p95_threshold_ms": 500, "window_days": 30},
        },
        "error_budget": {
            "alert_thresholds": {
                "warning_pct": 50,
                "critical_pct": 80,
                "block_pct": 90,
            }
        },
        "burn_rate": {
            "thresholds": {
                "low": 1.0, "medium": 2.0, "high": 5.0, "critical": 10.0
            }
        },
    }
    p = tmp_path / "slos.yaml"
    p.write_text(yaml.dump(cfg))
    return p


def _metrics(
    total: int = 2_592_000,
    failed: int = 500,      # ~80% budget remaining at 99.9% SLO target
    p95_ms: int = 480,
    p99_ms: int = 890,
    hourly_rates: list[float] | None = None,
) -> dict:
    return {
        "service": "test-service",
        "window_days": 30,
        "total_requests": total,
        "failed_requests": failed,
        "latency_percentiles": {"p50_ms": 120, "p95_ms": p95_ms, "p99_ms": p99_ms},
        "hourly_burn_rate": hourly_rates or [1.0] * 24,
    }


@pytest.fixture()
def healthy_metrics_path(tmp_path: Path) -> Path:
    p = tmp_path / "metrics_healthy.json"
    p.write_text(json.dumps(_metrics()))
    return p


@pytest.fixture()
def critical_metrics_path(tmp_path: Path) -> Path:
    """Metrics that put the error budget below 10 %."""
    # SLO target = 99.9 % → allowed_fail = 0.1 % of 1_000_000 = 1000 failures
    # To exhaust > 90 % of budget: fail > 900 out of 1_000_000
    data = _metrics(
        total=1_000_000,
        failed=950,         # 0.095 % failure rate — budget exhausted ~ 95 %
        p95_ms=700,         # Also breach latency SLO
        hourly_rates=[12.0] * 24,  # Critical burn rate
    )
    p = tmp_path / "metrics_critical.json"
    p.write_text(json.dumps(data))
    return p


@pytest.fixture()
def recovering_metrics_path(tmp_path: Path) -> Path:
    """Reproduces the CI-failure scenario: budget ~19 %, recent burn <1×.

    The service burned heavily mid-day (peaked at ~3×), consuming the error
    budget, but has since recovered to sub-1×.  The burn rate label should be
    'low' (not inflated to 'high' because of the low budget), and the gate
    decision should be DELAY via P005, NOT BLOCK via P002.
    """
    data = _metrics(
        total=2_592_000,
        failed=2_100,  # 99.9190 % availability → ~19 % budget remaining
        p95_ms=480,
        hourly_rates=[
            0.8, 0.9, 1.0, 1.1, 0.9, 0.8,
            1.2, 1.4, 1.8, 2.4, 3.1, 2.8,
            2.5, 2.1, 1.9, 1.7, 1.5, 1.4,
            1.2, 1.1, 1.0, 0.9, 0.8, 0.9,
        ],
    )
    p = tmp_path / "metrics_recovering.json"
    p.write_text(json.dumps(data))
    return p


# ── Cost fixtures ─────────────────────────────────────────────────────────────

def _cost_data(base_cost: float = 45.0, spike: bool = False) -> dict:
    costs = []
    from datetime import date, timedelta
    start = date(2026, 1, 22)
    for i in range(30):
        day = start + timedelta(days=i)
        if spike and i >= 21:
            amount = round(base_cost * 1.40 + i * 0.5, 2)
        else:
            amount = round(base_cost + i * 0.1, 2)
        costs.append({"date": day.isoformat(), "cost": amount})
    return {
        "service": "test-service",
        "currency": "USD",
        "collected_at": "2026-02-20T00:00:00Z",
        "daily_costs": costs,
        "budget_usd_monthly": 1500,
    }


@pytest.fixture()
def stable_cost_path(tmp_path: Path) -> Path:
    p = tmp_path / "cost_stable.json"
    p.write_text(json.dumps(_cost_data(spike=False)))
    return p


@pytest.fixture()
def spiking_cost_path(tmp_path: Path) -> Path:
    p = tmp_path / "cost_spike.json"
    p.write_text(json.dumps(_cost_data(spike=True)))
    return p


# ── Policy fixtures ───────────────────────────────────────────────────────────

@pytest.fixture()
def policies_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "policies.yaml"


# ── App fixture ───────────────────────────────────────────────────────────────

@pytest.fixture()
def app_client():
    """Return a Flask test client for the sample app."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
    from app import app as flask_app  # type: ignore
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
