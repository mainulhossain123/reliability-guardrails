"""
Incident Decision Explainer — human-readable deployment decision narratives.

Currently implemented as a deterministic rule-based engine.
The interface is LLM-ready: swap ``_generate_rule_based()`` for an
OpenAI / Anthropic call without touching any callers.

Usage::

    from ai.incident_explainer import IncidentExplainer
    from decision.decision_engine import DecisionEngine

    result = DecisionEngine().evaluate()
    explanation = IncidentExplainer().explain(result)
    print(explanation)
"""

from __future__ import annotations

import os
import textwrap
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decision.decision_engine import DecisionResult


# ── Explainer ─────────────────────────────────────────────────────────────────

class IncidentExplainer:
    """
    Generates a human-readable narrative explaining a deployment decision.

    Plug-in LLM support:
        Set ``OPENAI_API_KEY`` (or ``ANTHROPIC_API_KEY``) in the environment
        and set ``EXPLAINER_BACKEND=openai`` (or ``anthropic``).
        The engine will automatically route to the LLM backend.
    """

    BACKEND_ENV = "EXPLAINER_BACKEND"

    def __init__(self) -> None:
        self.backend = os.getenv(self.BACKEND_ENV, "rule_based").lower()

    def explain(self, result: "DecisionResult") -> str:
        if self.backend == "openai":
            return self._generate_openai(result)
        if self.backend == "anthropic":
            return self._generate_anthropic(result)
        return self._generate_rule_based(result)

    # ── Rule-based backend (default) ──────────────────────────────────────────

    def _generate_rule_based(self, result: "DecisionResult") -> str:
        now       = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        slo       = result.slo
        cost      = result.cost
        issues    = self._collect_issues(result)
        recs      = self._collect_recommendations(result)

        action_verb = {
            "BLOCK": "has been BLOCKED",
            "DELAY": f"has been DELAYED by {result.delay_minutes} minutes",
            "WARN":  "is ALLOWED with a WARNING",
            "ALLOW": "is ALLOWED",
        }.get(result.action, result.action)

        section_sep = "─" * 60
        header = f"""
╔══════════════════════════════════════════════════════════════╗
║         INCIDENT EXPLAINER — DEPLOYMENT NARRATIVE           ║
╚══════════════════════════════════════════════════════════════╝

Generated : {now}
Service   : {slo.details.get('service', 'unknown') if slo else 'unknown'}
Decision  : {result.action}
Policy    : [{result.policy_id}] {result.policy_name}
""".strip()

        summary = f"""
{section_sep}
SUMMARY
{section_sep}
Deployment {action_verb}.

{textwrap.fill(result.reason, width=60)}
""".strip()

        contributing = ""
        if issues:
            contributing = f"""
{section_sep}
CONTRIBUTING FACTORS
{section_sep}
""".strip()
            for i, issue in enumerate(issues, 1):
                contributing += f"\n  {i}. {issue}"

        slo_section = ""
        if slo:
            slo_section = f"""

{section_sep}
RELIABILITY SIGNALS
{section_sep}
  • Availability       : {slo.availability_pct:.4f}%  (target {slo.details.get('availability_target_pct', 99.9)}%)
  • Error Budget Left  : {slo.error_budget_pct:.2f}%  {'🔴 CRITICAL' if slo.error_budget_pct < 10 else '🟠 LOW' if slo.error_budget_pct < 30 else '🟢 OK'}
  • Burn Rate          : {slo.burn_rate.upper()}  (×{slo.burn_rate_value:.1f} normal)
  • Latency p95        : {slo.latency_p95_ms} ms  ({'within target' if slo.latency_compliant else '⚠️  above target'})
  • Latency p99        : {slo.latency_p99_ms} ms""".strip()

        cost_section = ""
        if cost:
            cost_section = f"""

{section_sep}
FINOPS SIGNALS
{section_sep}
  • Week-over-week change : {cost.wow_change_pct:+.2f}%  ({cost.trend.upper()})
  • Current week avg      : ${cost.current_week_avg_usd:.2f}/day
  • Previous week avg     : ${cost.previous_week_avg_usd:.2f}/day
  • MTD spend             : ${cost.mtd_spend_usd:.2f}  of ${cost.budget_usd:.2f} budget
  • Budget utilisation    : {cost.budget_utilisation_pct:.2f}%
  • Spike detected        : {'YES ⚠️' if cost.spike_detected else 'NO'}""".strip()

        rec_section = ""
        if recs:
            rec_section = f"""

{section_sep}
RECOMMENDED ACTIONS
{section_sep}""".strip()
            for i, rec in enumerate(recs, 1):
                rec_section += f"\n  {i}. {rec}"

        context_section = f"""

{section_sep}
CONTEXT & NEXT STEPS
{section_sep}
  {textwrap.fill(result.remediation, width=58, subsequent_indent='  ')}

  If you believe this decision is incorrect:
    • Review the active policies in config/policies.yaml
    • Re-run the SLO engine to confirm current signals
    • Escalate to the on-call SRE team with this report
{section_sep}""".strip()

        parts = [header, "", summary]
        if contributing:
            parts += ["", contributing]
        if slo_section:
            parts += ["", slo_section]
        if cost_section:
            parts += ["", cost_section]
        if rec_section:
            parts += ["", rec_section]
        parts += ["", context_section]

        return "\n".join(parts)

    # ── Issue / recommendation builders ───────────────────────────────────────

    @staticmethod
    def _collect_issues(result: "DecisionResult") -> list[str]:
        issues: list[str] = []
        slo  = result.slo
        cost = result.cost

        if slo:
            if slo.error_budget_pct < 10:
                issues.append(
                    f"Error budget is critically exhausted ({slo.error_budget_pct:.1f}% remaining). "
                    "SLO breach is imminent."
                )
            elif slo.error_budget_pct < 30:
                issues.append(
                    f"Error budget is running low ({slo.error_budget_pct:.1f}% remaining). "
                    "Continued errors will breach the SLO."
                )
            if slo.burn_rate in {"high", "critical"}:
                issues.append(
                    f"Error budget is burning at {slo.burn_rate_value:.1f}× the normal rate. "
                    "At this rate the remaining budget will be exhausted quickly."
                )
            if not slo.latency_compliant:
                issues.append(
                    f"p95 latency ({slo.latency_p95_ms} ms) exceeds the SLO target "
                    f"({slo.details.get('latency_target_p95_ms', '?')} ms). User experience is degraded."
                )
            if not slo.availability_compliant:
                issues.append(
                    f"Availability ({slo.availability_pct:.4f}%) is below the SLO target "
                    f"({slo.details.get('availability_target_pct', '?')}%). "
                )

        if cost:
            if cost.wow_change_pct >= 30:
                issues.append(
                    f"Cloud costs spiked {cost.wow_change_pct:.1f}% week-over-week "
                    f"(${cost.previous_week_avg_usd:.2f} → ${cost.current_week_avg_usd:.2f}/day). "
                    "Deploying now amplifies spend risk."
                )
            elif cost.wow_change_pct >= 20:
                issues.append(
                    f"Cloud costs increased {cost.wow_change_pct:.1f}% week-over-week. "
                    "Monitor closely before proceeding."
                )

        return issues

    @staticmethod
    def _collect_recommendations(result: "DecisionResult") -> list[str]:
        recs: list[str] = []
        slo  = result.slo
        cost = result.cost
        action = result.action

        if action == "BLOCK":
            recs.append("Freeze all deployments to this service immediately.")
        if action in {"BLOCK", "DELAY"} and slo:
            if slo.burn_rate in {"high", "critical"}:
                recs.append(
                    "Investigate recent error logs and traces. "
                    "Consider rolling back the last deployment."
                )
            if not slo.latency_compliant:
                recs.append(
                    "Profile request handlers for latency regressions. "
                    "Check for dependency slowness (DB, downstream APIs)."
                )
        if cost and cost.spike_detected:
            recs.append(
                "Open a FinOps review ticket. "
                "Check for runaway auto-scaling or orphaned resources."
            )
        if slo and slo.error_budget_pct < 20:
            recs.append(
                "Set a budget exhaustion alert in your monitoring platform "
                "so on-call is notified before the next threshold is hit."
            )
        if action == "ALLOW":
            recs.append(
                "All signals are within acceptable thresholds. "
                "Proceed with deployment using your standard review process."
            )
        return recs

    # ── LLM stubs (plug-in ready) ─────────────────────────────────────────────

    def _generate_openai(self, result: "DecisionResult") -> str:  # pragma: no cover
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            raise RuntimeError(
                "openai package not installed. "
                "Run: pip install openai"
            )
        client = OpenAI()
        prompt = self._build_llm_prompt(result)
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            messages=[
                {"role": "system", "content": "You are an expert SRE narrating deployment decisions."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content

    def _generate_anthropic(self, result: "DecisionResult") -> str:  # pragma: no cover
        try:
            import anthropic  # type: ignore
        except ImportError:
            raise RuntimeError(
                "anthropic package not installed. "
                "Run: pip install anthropic"
            )
        client = anthropic.Anthropic()
        prompt = self._build_llm_prompt(result)
        message = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    @staticmethod
    def _build_llm_prompt(result: "DecisionResult") -> str:
        import json as _json
        return (
            "You are an expert Site Reliability Engineer. "
            "Explain the following deployment decision in clear, concise language "
            "for a non-technical stakeholder. Include the key reliability and cost signals, "
            "why the decision was made, and recommended next steps.\n\n"
            f"Decision JSON:\n{_json.dumps(result.to_dict(), indent=2)}"
        )


# ── CLI entry-point ───────────────────────────────────────────────────────────

def main() -> None:
    from decision.decision_engine import DecisionEngine
    result = DecisionEngine().evaluate()
    explainer = IncidentExplainer()
    print(explainer.explain(result))


if __name__ == "__main__":
    main()
