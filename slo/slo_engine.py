"""
SLO Engine — evaluates service reliability against defined SLOs.

Reads:
  • config/slos.yaml  — SLO targets and thresholds
  • data/metrics.json — collected service telemetry

Produces:
  • SLOResult dataclass with all evaluated signals
  • CLI report suitable for human review and CI/CD gates
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── Defaults ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG  = ROOT / "config" / "slos.yaml"
DEFAULT_METRICS = ROOT / "data"   / "metrics.json"


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class SLOResult:
    """All evaluated SLO signals in a single, serialisable object."""

    availability_pct: float
    error_budget_pct: float          # % of budget *remaining*
    burn_rate: str                   # "low" | "medium" | "high" | "critical"
    burn_rate_value: float           # numeric burn-rate multiplier
    latency_p95_ms: float
    latency_p99_ms: float
    latency_compliant: bool
    availability_compliant: bool

    # Raw metadata for downstream consumers
    details: dict[str, Any] = field(default_factory=dict)

    # ── Derived helpers ───────────────────────────────────────────────────────

    @property
    def healthy(self) -> bool:
        return (
            self.availability_compliant
            and self.latency_compliant
            and self.error_budget_pct >= 20
            and self.burn_rate in {"low", "medium"}
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "availability_pct": self.availability_pct,
            "error_budget_pct": self.error_budget_pct,
            "burn_rate": self.burn_rate,
            "burn_rate_value": self.burn_rate_value,
            "latency_p95_ms": self.latency_p95_ms,
            "latency_p99_ms": self.latency_p99_ms,
            "latency_compliant": self.latency_compliant,
            "availability_compliant": self.availability_compliant,
            "healthy": self.healthy,
            "details": self.details,
        }


# ── Engine ────────────────────────────────────────────────────────────────────

class SLOEngine:
    """
    Evaluates raw service metrics against configured SLO targets.

    Usage::

        engine = SLOEngine()
        result = engine.evaluate()
        print(engine.report())
    """

    def __init__(
        self,
        config_path: str | Path = DEFAULT_CONFIG,
        metrics_path: str | Path = DEFAULT_METRICS,
    ) -> None:
        self.config  = self._load_yaml(Path(config_path))
        self.metrics = self._load_json(Path(metrics_path))

    # ── Loaders ───────────────────────────────────────────────────────────────

    @staticmethod
    def _load_yaml(path: Path) -> dict:
        with path.open() as fh:
            return yaml.safe_load(fh)

    @staticmethod
    def _load_json(path: Path) -> dict:
        with path.open() as fh:
            return json.load(fh)

    # ── Core evaluation ───────────────────────────────────────────────────────

    def evaluate(self) -> SLOResult:
        slos    = self.config["slos"]
        metrics = self.metrics
        burn_cfg = self.config.get("burn_rate", {}).get("thresholds", {})

        # ── Availability ──────────────────────────────────────────────────────
        total  = metrics["total_requests"]
        failed = metrics["failed_requests"]
        success = max(0, total - failed)
        availability_pct = round((success / total) * 100, 6) if total > 0 else 100.0

        target = slos["availability"]["target"]  # e.g. 99.9
        allowed_fail_pct = 100.0 - target        # 0.1 %
        actual_fail_pct  = 100.0 - availability_pct

        # Error budget: how much of the *allowed* failure headroom remains
        if allowed_fail_pct > 0:
            consumed_pct = (actual_fail_pct / allowed_fail_pct) * 100
        else:
            consumed_pct = 100.0 if failed > 0 else 0.0

        error_budget_pct = round(max(0.0, 100.0 - consumed_pct), 2)

        # ── Burn rate ─────────────────────────────────────────────────────────
        hourly_rates: list[float] = metrics.get("hourly_burn_rate", [1.0])
        avg_burn    = sum(hourly_rates) / len(hourly_rates)
        recent_burn = sum(hourly_rates[-3:]) / min(3, len(hourly_rates))

        critical_thr = burn_cfg.get("critical", 10.0)
        high_thr     = burn_cfg.get("high",      5.0)
        medium_thr   = burn_cfg.get("medium",     2.0)

        if recent_burn >= critical_thr or error_budget_pct < 10:
            burn_label = "critical"
        elif recent_burn >= high_thr or error_budget_pct < 20:
            burn_label = "high"
        elif recent_burn >= medium_thr or error_budget_pct < 50:
            burn_label = "medium"
        else:
            burn_label = "low"

        # ── Latency ───────────────────────────────────────────────────────────
        lat = metrics["latency_percentiles"]
        p95_ms = lat["p95_ms"]
        p99_ms = lat.get("p99_ms", lat.get("p99", p95_ms))
        lat_threshold = slos["latency"]["p95_threshold_ms"]
        latency_compliant = p95_ms <= lat_threshold

        return SLOResult(
            availability_pct=availability_pct,
            error_budget_pct=error_budget_pct,
            burn_rate=burn_label,
            burn_rate_value=round(recent_burn, 2),
            latency_p95_ms=p95_ms,
            latency_p99_ms=p99_ms,
            latency_compliant=latency_compliant,
            availability_compliant=availability_pct >= target,
            details={
                "total_requests":   total,
                "failed_requests":  failed,
                "availability_target_pct": target,
                "latency_target_p95_ms":   lat_threshold,
                "avg_burn_rate":    round(avg_burn, 2),
                "recent_burn_rate": round(recent_burn, 2),
                "hourly_burn_rates": hourly_rates,
                "service":          metrics.get("service", "unknown"),
            },
        )

    # ── CLI report ────────────────────────────────────────────────────────────

    def report(self) -> str:
        r = self.evaluate()

        def flag(ok: bool) -> str:
            return "✅" if ok else "❌"

        budget_bar = self._budget_bar(r.error_budget_pct)

        lines = [
            "╔══════════════════════════════════════════════════╗",
            "║           SLO ENGINE  — STATUS REPORT           ║",
            "╠══════════════════════════════════════════════════╣",
            f"║  Service:            {r.details.get('service', 'n/a'):<28}║",
            "╠══════════════════════════════════════════════════╣",
            f"║  Availability        {r.availability_pct:.4f}%              {flag(r.availability_compliant)} ║",
            f"║  Error Budget Left   {r.error_budget_pct:>6.2f}%   {budget_bar}    ║",
            f"║  Burn Rate           {r.burn_rate.upper():<10} (×{r.burn_rate_value:.1f})          ║",
            f"║  Latency p95         {r.latency_p95_ms:>5} ms (limit {r.details['latency_target_p95_ms']} ms) {flag(r.latency_compliant)} ║",
            f"║  Latency p99         {r.latency_p99_ms:>5} ms                       ║",
            "╠══════════════════════════════════════════════════╣",
            f"║  Overall Health      {'HEALTHY ✅' if r.healthy else 'DEGRADED ❌':<38}║",
            "╚══════════════════════════════════════════════════╝",
        ]
        return "\n".join(lines)

    @staticmethod
    def _budget_bar(pct: float, width: int = 10) -> str:
        filled = round(pct / 100 * width)
        return "[" + "█" * filled + "░" * (width - filled) + "]"


# ── CLI entry-point ───────────────────────────────────────────────────────────

def main() -> None:
    config_path  = os.getenv("SLO_CONFIG",  str(DEFAULT_CONFIG))
    metrics_path = os.getenv("SLO_METRICS", str(DEFAULT_METRICS))

    engine = SLOEngine(config_path, metrics_path)
    print(engine.report())

    result = engine.evaluate()
    if not result.availability_compliant or not result.latency_compliant:
        sys.exit(2)
    if result.error_budget_pct < 10:
        sys.exit(1)


if __name__ == "__main__":
    main()
