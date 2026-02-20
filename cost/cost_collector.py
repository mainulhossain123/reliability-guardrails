"""
Cost Collector — FinOps signal generator for the deployment guardrail system.

Reads:
  • data/cost.json — historical daily cloud spend per service

Produces:
  • CostResult dataclass with spend trends and spike detection
  • CLI report suitable for human review and policy evaluation
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COST_DATA = ROOT / "data" / "cost.json"

# ── Thresholds (overridable via environment) ──────────────────────────────────

WARN_SPIKE_PCT  = float(os.getenv("COST_WARN_PCT",  "20"))  # 20 % WoW increase
BLOCK_SPIKE_PCT = float(os.getenv("COST_BLOCK_PCT", "30"))  # 30 % WoW increase


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class CostResult:
    """Evaluated cost signals for a service."""

    service: str
    current_week_avg_usd: float
    previous_week_avg_usd: float
    wow_change_pct: float           # week-over-week % change (positive = increase)
    trend: str                      # "stable" | "rising" | "falling" | "spiking"
    spike_detected: bool
    budget_usd: float
    mtd_spend_usd: float
    budget_utilisation_pct: float
    daily_costs: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "service":                  self.service,
            "current_week_avg_usd":     self.current_week_avg_usd,
            "previous_week_avg_usd":    self.previous_week_avg_usd,
            "wow_change_pct":           self.wow_change_pct,
            "trend":                    self.trend,
            "spike_detected":           self.spike_detected,
            "budget_usd":               self.budget_usd,
            "mtd_spend_usd":            self.mtd_spend_usd,
            "budget_utilisation_pct":   self.budget_utilisation_pct,
            "details":                  self.details,
        }


# ── Collector ─────────────────────────────────────────────────────────────────

class CostCollector:
    """
    Analyses cloud spend data and surfaces FinOps signals.

    Usage::

        collector = CostCollector()
        result    = collector.evaluate()
        print(collector.report())
    """

    def __init__(self, cost_path: str | Path = DEFAULT_COST_DATA) -> None:
        self.data = self._load(Path(cost_path))

    @staticmethod
    def _load(path: Path) -> dict:
        with path.open() as fh:
            return json.load(fh)

    # ── Core evaluation ───────────────────────────────────────────────────────

    def evaluate(self) -> CostResult:
        daily: list[dict] = self.data["daily_costs"]
        budget = float(self.data.get("budget_usd_monthly", 0))
        service = self.data.get("service", "unknown")

        # Sort ascending by date just in case
        daily_sorted = sorted(daily, key=lambda d: d["date"])
        amounts = [float(d["cost"]) for d in daily_sorted]

        # Week-over-week comparison
        prev_week = amounts[-14:-7] if len(amounts) >= 14 else amounts[: len(amounts) // 2]
        curr_week = amounts[-7:]    if len(amounts) >= 7  else amounts[len(amounts) // 2 :]

        prev_avg = sum(prev_week) / len(prev_week) if prev_week else 0.0
        curr_avg = sum(curr_week) / len(curr_week) if curr_week else 0.0

        wow_pct = (
            round(((curr_avg - prev_avg) / prev_avg) * 100, 2)
            if prev_avg > 0
            else 0.0
        )

        # Month-to-date spend (all available data if window < 30 days)
        mtd = round(sum(amounts), 2)

        # Budget utilisation
        budget_util = round((mtd / budget) * 100, 2) if budget > 0 else 0.0

        # Trend label
        if wow_pct >= BLOCK_SPIKE_PCT:
            trend = "spiking"
        elif wow_pct >= WARN_SPIKE_PCT:
            trend = "rising"
        elif wow_pct <= -10:
            trend = "falling"
        else:
            trend = "stable"

        spike_detected = wow_pct >= WARN_SPIKE_PCT

        return CostResult(
            service=service,
            current_week_avg_usd=round(curr_avg, 2),
            previous_week_avg_usd=round(prev_avg, 2),
            wow_change_pct=wow_pct,
            trend=trend,
            spike_detected=spike_detected,
            budget_usd=budget,
            mtd_spend_usd=mtd,
            budget_utilisation_pct=budget_util,
            daily_costs=daily_sorted[-7:],
            details={
                "currency":         self.data.get("currency", "USD"),
                "prev_week_avg":    round(prev_avg, 2),
                "curr_week_avg":    round(curr_avg, 2),
                "wow_change_pct":   wow_pct,
                "cost_breakdown":   self.data.get("cost_breakdown", {}),
                "warn_threshold":   WARN_SPIKE_PCT,
                "block_threshold":  BLOCK_SPIKE_PCT,
            },
        )

    # ── CLI report ────────────────────────────────────────────────────────────

    def report(self) -> str:
        r = self.evaluate()
        trend_icon = {"stable": "→", "rising": "↑", "falling": "↓", "spiking": "⚠️ ↑↑"}
        icon = trend_icon.get(r.trend, "?")

        lines = [
            "╔══════════════════════════════════════════════════╗",
            "║        COST COLLECTOR — FINOPS REPORT           ║",
            "╠══════════════════════════════════════════════════╣",
            f"║  Service:            {r.service:<28}║",
            "╠══════════════════════════════════════════════════╣",
            f"║  Prev-week avg       ${r.previous_week_avg_usd:>8.2f}/day                ║",
            f"║  Curr-week avg       ${r.current_week_avg_usd:>8.2f}/day                ║",
            f"║  WoW change          {r.wow_change_pct:>+7.2f}%   {icon:<12}         ║",
            f"║  Trend               {r.trend.upper():<28}║",
            f"║  Spike detected      {'YES ⚠️' if r.spike_detected else 'NO  ✅':<28}║",
            "╠══════════════════════════════════════════════════╣",
            f"║  MTD spend           ${r.mtd_spend_usd:>10.2f}                  ║",
            f"║  Monthly budget      ${r.budget_usd:>10.2f}                  ║",
            f"║  Budget utilisation  {r.budget_utilisation_pct:>6.2f}%                         ║",
            "╚══════════════════════════════════════════════════╝",
        ]
        return "\n".join(lines)


# ── CLI entry-point ───────────────────────────────────────────────────────────

def main() -> None:
    path = os.getenv("COST_DATA", str(DEFAULT_COST_DATA))
    collector = CostCollector(path)
    print(collector.report())

    result = collector.evaluate()
    if result.wow_change_pct >= BLOCK_SPIKE_PCT:
        sys.exit(1)


if __name__ == "__main__":
    main()
