"""
Decision Engine — Deployment Guardrail Core

Combines SLO and cost signals, evaluates policies, and returns a
structured deployment decision: ALLOW | WARN | DELAY | BLOCK.

Usage (CLI)::

    python -m decision.decision_engine

Usage (as library)::

    from decision.decision_engine import DecisionEngine
    result = DecisionEngine().evaluate()
    print(result.action)  # "BLOCK"
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cost.cost_collector import CostCollector, CostResult
from slo.slo_engine import SLOEngine, SLOResult

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICIES = ROOT / "config" / "policies.yaml"

# ── Decision action hierarchy (higher index = more severe) ───────────────────
ACTION_RANK = {"ALLOW": 0, "WARN": 1, "DELAY": 2, "BLOCK": 3}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class DecisionResult:
    """Full deployment decision with supporting evidence."""

    action: str                          # ALLOW | WARN | DELAY | BLOCK
    policy_id: str
    policy_name: str
    reason: str
    remediation: str
    delay_minutes: int = 0
    slo: SLOResult | None = None
    cost: CostResult | None = None
    evaluated_policies: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "action":            self.action,
            "policy_id":         self.policy_id,
            "policy_name":       self.policy_name,
            "reason":            self.reason,
            "remediation":       self.remediation,
            "delay_minutes":     self.delay_minutes,
            "evaluated_policies": self.evaluated_policies,
        }
        if self.slo:
            d["slo"] = self.slo.to_dict()
        if self.cost:
            d["cost"] = self.cost.to_dict()
        return d

    def exit_code(self) -> int:
        """Return shell exit code: 0 = allow/warn, 1 = delay, 2 = block."""
        return {"ALLOW": 0, "WARN": 0, "DELAY": 1, "BLOCK": 2}.get(self.action, 2)


# ── Engine ────────────────────────────────────────────────────────────────────

class DecisionEngine:
    """
    Evaluates deployment eligibility by combining SLO and cost signals
    against a prioritised policy ruleset.
    """

    def __init__(
        self,
        policies_path: str | Path = DEFAULT_POLICIES,
        slo_engine: SLOEngine | None = None,
        cost_collector: CostCollector | None = None,
    ) -> None:
        self.policies = self._load_policies(Path(policies_path))
        self._slo  = slo_engine   or SLOEngine()
        self._cost = cost_collector or CostCollector()

    @staticmethod
    def _load_policies(path: Path) -> list[dict]:
        with path.open() as fh:
            data = yaml.safe_load(fh)
        return sorted(data.get("policies", []), key=lambda p: p.get("priority", 99))

    # ── Signal collection ─────────────────────────────────────────────────────

    def _collect_signals(self) -> dict[str, Any]:
        slo  = self._slo.evaluate()
        cost = self._cost.evaluate()
        return {
            "slo":  slo,
            "cost": cost,
            "signals": {
                "error_budget_pct":    slo.error_budget_pct,
                "burn_rate":           slo.burn_rate,
                "availability_pct":    slo.availability_pct,
                "latency_compliant":   slo.latency_compliant,
                "cost_spike_pct":      cost.wow_change_pct,
                "cost_spike_detected": cost.spike_detected,
                "cost_trend":          cost.trend,
            },
        }

    # ── Policy evaluation ─────────────────────────────────────────────────────

    def _matches(self, policy: dict, signals: dict[str, Any]) -> bool:
        conditions = policy.get("conditions", {})
        if not conditions:
            return True  # Catch-all

        for key, rule in conditions.items():
            value = signals.get(key)
            if value is None:
                return False

            op    = rule.get("operator", "eq")
            target = rule.get("value")

            if op == "lt"  and not (value <  target):   return False
            if op == "lte" and not (value <= target):   return False
            if op == "gt"  and not (value >  target):   return False
            if op == "gte" and not (value >= target):   return False
            if op == "eq"  and not (value == target):   return False
            if op == "neq" and not (value != target):   return False
            if op == "in"  and value not in target:      return False

        return True

    def evaluate(self) -> DecisionResult:
        ctx      = self._collect_signals()
        signals  = ctx["signals"]
        slo_r    = ctx["slo"]
        cost_r   = ctx["cost"]
        evaluated: list[dict] = []

        matched_policy: dict | None = None

        for policy in self.policies:
            matched = self._matches(policy, signals)
            evaluated.append({
                "id":      policy["id"],
                "name":    policy["name"],
                "matched": matched,
                "action":  policy["action"],
            })
            if matched and matched_policy is None:
                matched_policy = policy

        # Fallback — should never happen (P008 is catch-all) but be safe
        if matched_policy is None:
            matched_policy = {
                "id": "P-FALLBACK", "name": "Fallback allow",
                "action": "ALLOW",  "priority": 999,
                "reason": "No matching policy found — defaulting to ALLOW",
                "remediation": "Review your policies.yaml configuration.",
                "delay_minutes": 0,
            }

        return DecisionResult(
            action=matched_policy["action"],
            policy_id=matched_policy["id"],
            policy_name=matched_policy["name"],
            reason=matched_policy["reason"],
            remediation=matched_policy["remediation"],
            delay_minutes=matched_policy.get("delay_minutes", 0),
            slo=slo_r,
            cost=cost_r,
            evaluated_policies=evaluated,
        )

    # ── CLI report ────────────────────────────────────────────────────────────

    def report(self) -> str:
        result = self.evaluate()
        action_icons = {
            "ALLOW": "✅  ALLOW",
            "WARN":  "⚠️   WARN",
            "DELAY": "⏳  DELAY",
            "BLOCK": "🚫  BLOCK",
        }
        icon = action_icons.get(result.action, result.action)

        slo  = result.slo
        cost = result.cost

        lines = [
            "╔══════════════════════════════════════════════════════════════╗",
            "║         DEPLOYMENT GUARDRAIL — DECISION REPORT              ║",
            "╠══════════════════════════════════════════════════════════════╣",
            f"║  Decision:    {icon:<49}║",
            f"║  Policy:      [{result.policy_id}] {result.policy_name:<41}║",
            "╠══════════════════════════════════════════════════════════════╣",
            f"║  Reason:                                                     ║",
            f"║    {result.reason:<58}║",
            "╠══════════════════════════════════════════════════════════════╣",
            "║  SLO Signals:                                                ║",
        ]
        if slo:
            lines += [
                f"║    Availability      {slo.availability_pct:.4f}%                              ║",
                f"║    Error Budget      {slo.error_budget_pct:>6.2f}% remaining                       ║",
                f"║    Burn Rate         {slo.burn_rate.upper():<40}║",
                f"║    Latency p95       {slo.latency_p95_ms} ms ({'OK' if slo.latency_compliant else 'BREACHED':<36})║",
            ]
        if cost:
            lines += [
                "╠══════════════════════════════════════════════════════════════╣",
                "║  Cost Signals:                                               ║",
                f"║    WoW Change        {cost.wow_change_pct:>+7.2f}%                              ║",
                f"║    Trend             {cost.trend.upper():<40}║",
                f"║    Spike             {'YES ⚠️' if cost.spike_detected else 'NO  ✅':<40}║",
            ]
        if result.delay_minutes:
            lines.append(
                f"║  Delay               {result.delay_minutes} minutes{' ' * 44}║"
            )
        lines += [
            "╠══════════════════════════════════════════════════════════════╣",
            f"║  Remediation:                                                ║",
            f"║    {result.remediation:<58}║",
            "╚══════════════════════════════════════════════════════════════╝",
        ]
        return "\n".join(lines)


# ── CLI entry-point ───────────────────────────────────────────────────────────

def main() -> None:
    engine = DecisionEngine()
    result = engine.evaluate()
    print(engine.report())

    # Optionally dump JSON
    if "--json" in sys.argv:
        print(json.dumps(result.to_dict(), indent=2))

    sys.exit(result.exit_code())


if __name__ == "__main__":
    main()
