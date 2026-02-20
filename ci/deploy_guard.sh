#!/usr/bin/env bash
# =============================================================================
# deploy_guard.sh — SLO + Cost deployment gate for CI/CD pipelines
#
# Exit codes:
#   0  → ALLOW or WARN  (deployment may proceed)
#   1  → DELAY           (retry after $DELAY_MINUTES)
#   2  → BLOCK           (deployment must not proceed)
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

# ── Interpret exit code ───────────────────────────────────────────────────────
case $DECISION_EXIT in
  0)
    success "Deployment ALLOWED — all signals within threshold"
    ;;
  1)
    DELAY=${DELAY_MINUTES:-30}
    warn "Deployment DELAYED — re-evaluate in ${DELAY} minutes"
    warn "Fix open reliability issues before retrying"
    exit 1
    ;;
  2)
    error "Deployment BLOCKED — reliability or cost signals out of bounds"
    error "Review the decision report above and resolve issues first"
    echo ""
    info "Running incident explainer for detailed guidance..."
    echo ""
    python -m ai.incident_explainer 2>&1 || true
    exit 2
    ;;
  *)
    error "Unexpected exit code ($DECISION_EXIT) from decision engine"
    exit 2
    ;;
esac
