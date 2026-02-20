#!/usr/bin/env bash
# =============================================================================
# deploy_guard.sh — SLO + Cost deployment gate for CI/CD pipelines
#
# Exit codes:
#   0  → ALLOW, WARN, or DELAY  (pipeline continues; DELAY emits a warning)
#   1  → BLOCK                  (deployment must not proceed — pipeline fails)
#
# DELAY is treated as a soft gate: the pipeline step succeeds (exit 0) so that
# audit logging and artifact upload steps still run.  A GitHub Actions
# ::warning:: annotation is emitted so the delay is visible in the UI.
# Only BLOCK causes a hard pipeline failure.
#
# Usage:
#   ./ci/deploy_guard.sh
#
# Required environment:
#   PYTHONPATH must include the project root (set automatically if run from
#   docker compose or GitHub Actions using the provided workflow).
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[guardrail]${RESET} $*"; }
success() { echo -e "${GREEN}${BOLD}[guardrail] ✅  $*${RESET}"; }
warn()    { echo -e "${YELLOW}${BOLD}[guardrail] ⚠️   $*${RESET}"; }
error()   { echo -e "${RED}${BOLD}[guardrail] 🚫  $*${RESET}"; }

# ── Pre-flight ────────────────────────────────────────────────────────────────
info "Reliability Guardrails — Deployment Gate"
info "Service: ${SERVICE_NAME:-checkout-api}"
info "Branch:  ${BRANCH_NAME:-unknown}"
info "Commit:  ${COMMIT_SHA:-unknown}"
echo ""

export PYTHONPATH="${PYTHONPATH:-$ROOT_DIR}"

# ── Run decision engine ───────────────────────────────────────────────────────
info "Evaluating SLO and cost signals..."
echo ""

set +e
DECISION_OUTPUT=$(python -m decision.decision_engine 2>&1)
DECISION_EXIT=$?
set -e

echo "$DECISION_OUTPUT"
echo ""

# ── Read structured decision (single extra Python call; data files are static
# ── during a CI run so the result is guaranteed consistent with the report).
DECISION_ACTION=$(python -c "
from decision.decision_engine import DecisionEngine
print(DecisionEngine().evaluate().action)
" 2>/dev/null || echo "UNKNOWN")

DELAY_MINS=$(python -c "
from decision.decision_engine import DecisionEngine
print(DecisionEngine().evaluate().delay_minutes)
" 2>/dev/null || echo "0")

# Write outputs for downstream workflow steps (no-op outside GitHub Actions)
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "decision=${DECISION_ACTION}"   >> "$GITHUB_OUTPUT"
  echo "delay_minutes=${DELAY_MINS}"   >> "$GITHUB_OUTPUT"
fi

# ── Interpret exit code ───────────────────────────────────────────────────────
case $DECISION_EXIT in
  0)
    # ALLOW or WARN — engine exit 0 covers both
    if [ "$DECISION_ACTION" = "WARN" ]; then
      warn "Deployment ALLOWED with WARNING — review signals before proceeding"
      echo "::warning title=Deployment Warning::Reliability or cost signals require attention. Review before deploying."
    else
      success "Deployment ALLOWED — all signals within acceptable thresholds"
    fi
    ;;
  1)
    # DELAY — soft gate; pipeline succeeds but deployment should be staged
    warn "Deployment DELAYED ${DELAY_MINS} minutes — error budget is low, signals are recovering"
    warn "Proceed with a canary deployment or wait for error budget to stabilise"
    echo "::warning title=Deployment Delayed ${DELAY_MINS} min::Error budget is below the threshold for an unrestricted deploy. Re-evaluate after ${DELAY_MINS} minutes or use a staged rollout."
    # EXIT 0 — DELAY is informational; audit logging + artifact upload must still run
    exit 0
    ;;
  2)
    error "Deployment BLOCKED — reliability or cost signals out of bounds"
    error "Review the decision report above and resolve issues first"
    echo "::error title=Deployment Blocked::$(echo "$DECISION_OUTPUT" | grep 'Reason:' -A1 | tail -1 | sed 's/^[[:space:]]*//')"
    echo ""
    info "Running incident explainer for detailed guidance..."
    echo ""
    python -m ai.incident_explainer 2>&1 || true
    # EXIT 1 — BLOCK is a hard failure
    exit 1
    ;;
  *)
    error "Unexpected exit code ($DECISION_EXIT) from decision engine"
    exit 1
    ;;
esac
