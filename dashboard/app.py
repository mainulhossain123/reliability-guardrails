"""
Reliability Guardrails — Web Dashboard

Serves a real-time HTML dashboard that visualises:
  • SLO health (error budget, burn rate, latency)
  • Cost signals (WoW change, trend, spend)
  • Deployment gate decision (ALLOW / WARN / DELAY / BLOCK)
  • Incident explanation narrative

Run:
    python -m dashboard.app
    # or via docker compose up dashboard
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai.incident_explainer import IncidentExplainer
from cost.cost_collector import CostCollector
from decision.decision_engine import DecisionEngine
from slo.slo_engine import SLOEngine
from storage.audit_log import AuditLog

app = Flask(__name__, template_folder="templates")

# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/slo")
def api_slo():
    try:
        result = SLOEngine().evaluate()
        return jsonify({"ok": True, "data": result.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/cost")
def api_cost():
    try:
        result = CostCollector().evaluate()
        return jsonify({"ok": True, "data": result.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/decision")
def api_decision():
    try:
        engine = DecisionEngine()
        result = engine.evaluate()
        return jsonify({"ok": True, "data": result.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/explain")
def api_explain():
    try:
        engine = DecisionEngine()
        result = engine.evaluate()
        explanation = IncidentExplainer().explain(result)
        return jsonify({"ok": True, "data": {"text": explanation}})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/simulate")
def api_simulate():
    """
    Accept a JSON body with overrides for error_budget_pct, burn_rate, etc.
    Writes the result to the audit log and returns the decision.
    """
    try:
        overrides = request.get_json(silent=True) or {}
        engine = DecisionEngine()
        result = engine.evaluate()

        # Persist to audit log
        AuditLog().write(result)

        explanation = IncidentExplainer().explain(result)
        return jsonify({
            "ok": True,
            "data": {
                **result.to_dict(),
                "explanation": explanation,
            }
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/audit")
def api_audit():
    try:
        records = AuditLog().read_today()
        return jsonify({"ok": True, "data": records})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/all")
def api_all():
    """Single endpoint that returns all signals — powers the dashboard."""
    try:
        slo_result  = SLOEngine().evaluate()
        cost_result = CostCollector().evaluate()
        engine      = DecisionEngine()
        dec_result  = engine.evaluate()
        explanation = IncidentExplainer().explain(dec_result)

        return jsonify({
            "ok": True,
            "data": {
                "slo":         slo_result.to_dict(),
                "cost":        cost_result.to_dict(),
                "decision":    dec_result.to_dict(),
                "explanation": explanation,
            }
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html")


# ── Entry-point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print(f"\n  🚀  Dashboard running at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
