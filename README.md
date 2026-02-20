# SLO-Driven Deployment Guardrails with Cost-Aware Reliability Automation

> Automatically **allows, delays, or blocks** CI/CD deployments based on real-time
> reliability (SLOs) and cloud cost signals — enforcing SRE best practices with
> explainable, auditable decisions.

---

## The Problem

| Symptom | Root Cause |
|---|---|
| Deployments happen during active incidents | No automated reliability gate |
| Error budgets silently burn to zero | No real-time SLO awareness in the pipeline |
| Cloud costs spike before anyone notices | Cost signals ignored at deploy time |
| Post-incident reviews repeat the same findings | No audit trail of what the system knew |

Teams deploy on schedules, not on *system health*. This project changes that.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CI/CD Pipeline                               │
│                                                                 │
│   git push ──► Test Suite ──► Deployment Gate                   │
│                                      │                          │
│              ┌───────────────────────┤                          │
│              ▼                       ▼                          │
│        SLO Engine              Cost Collector                   │
│              │                       │                          │
│              └──────────┬────────────┘                          │
│                         ▼                                       │
│                  Decision Engine                                │
│                  (policies.yaml)                                │
│                         │                                       │
│          ┌──────────────┼──────────────┐                        │
│          ▼              ▼              ▼                        │
│        ALLOW          DELAY          BLOCK                      │
│                         │              │                        │
│                         └──────────────►  AI Explainer          │
│                                            + Audit Log          │
└─────────────────────────────────────────────────────────────────┘
```

### Signal Flow

```
Service Metrics ──► SLO Engine ──► Error Budget %
                                   Burn Rate
                                        │
Cost Data       ──► Cost Collector ──► WoW Change %    ──► Decision Engine ──► action
                                   Trend                     (policies.yaml)
```

---

## Quick Start

**Requires:** Docker and Docker Compose

```bash
git clone https://github.com/mainulhossain123/reliability-guardrails.git
cd reliability-guardrails

# Run the full test suite
docker compose run --rm test

# View the SLO status report
docker compose run --rm slo

# View the cost analysis report
docker compose run --rm cost

# Run the deployment gate (exit 0 = allow, 1 = delay, 2 = block)
docker compose run --rm decision

# Generate a human-readable incident explanation
docker compose run --rm explainer
```

### Without Docker

```bash
python -m venv .venv && source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate                            # Windows

pip install -r requirements.txt

python -m slo.slo_engine          # SLO report
python -m cost.cost_collector     # Cost report
python -m decision.decision_engine # Deployment gate
python -m ai.incident_explainer    # Incident narrative
```

---

## Sample Output

### Deployment Gate — BLOCK scenario

```
╔══════════════════════════════════════════════════════════════╗
║         DEPLOYMENT GUARDRAIL — DECISION REPORT              ║
╠══════════════════════════════════════════════════════════════╣
║  Decision:    🚫  BLOCK                                      ║
║  Policy:      [P002] Low error budget with high burn rate    ║
╠══════════════════════════════════════════════════════════════╣
║  Reason:                                                     ║
║    Error budget below 20% with high burn rate               ║
╠══════════════════════════════════════════════════════════════╣
║  SLO Signals:                                                ║
║    Availability      99.9050%                                ║
║    Error Budget        8.50% remaining                       ║
║    Burn Rate         CRITICAL                                ║
║    Latency p95         720 ms (BREACHED)                     ║
╠══════════════════════════════════════════════════════════════╣
║  Cost Signals:                                               ║
║    WoW Change          +35.00%                              ║
║    Trend             SPIKING                                 ║
║    Spike             YES ⚠️                                  ║
╠══════════════════════════════════════════════════════════════╣
║  Remediation:                                                ║
║    Hold all deployments. Reduce traffic or roll back.        ║
╚══════════════════════════════════════════════════════════════╝
```

### Incident Explainer

```
╔══════════════════════════════════════════════════════════════╗
║         INCIDENT EXPLAINER — DEPLOYMENT NARRATIVE           ║
╚══════════════════════════════════════════════════════════════╝

Generated : 2026-02-20T14:32:00 UTC
Service   : checkout-api
Decision  : BLOCK

─────────────────────────────────────────────────────────────
CONTRIBUTING FACTORS
─────────────────────────────────────────────────────────────
  1. Error budget is critically exhausted (8.5% remaining).
  2. Error budget burning at 12.5× the normal rate.
  3. Cloud costs spiked 35.0% week-over-week.

─────────────────────────────────────────────────────────────
RECOMMENDED ACTIONS
─────────────────────────────────────────────────────────────
  1. Freeze all deployments to this service immediately.
  2. Investigate recent error logs. Consider rolling back.
  3. Open a FinOps review ticket for the cost anomaly.
```

---

## Repository Structure

```
reliability-guardrails/
├── app/                        # Sample Flask microservice
│   ├── app.py                  # HTTP API with failure injection
│   ├── Dockerfile
│   └── requirements.txt
│
├── slo/                        # SLO evaluation engine
│   └── slo_engine.py           # Error budget & burn rate calculator
│
├── cost/                       # FinOps signal generator
│   └── cost_collector.py       # Week-over-week spend analyser
│
├── decision/                   # Deployment gate core
│   └── decision_engine.py      # Policy evaluator (ALLOW/DELAY/BLOCK)
│
├── ai/                         # Human-readable decision narratives
│   └── incident_explainer.py   # Rule-based + LLM-ready explainer
│
├── storage/                    # Audit persistence
│   └── audit_log.py            # JSONL decision audit trail
│
├── utils/                      # Shared utilities
│   └── logger.py               # Structured logger
│
├── config/                     # Policy & SLO definitions
│   ├── slos.yaml               # SLO targets and thresholds
│   └── policies.yaml           # Deployment guardrail rules
│
├── data/                       # Sample telemetry data
│   ├── metrics.json            # Service reliability metrics
│   ├── cost.json               # Historical cloud spend
│   └── resources.json          # Cloud resource inventory
│
├── docker/scenarios/           # Test scenarios
│   ├── allow/                  # Metrics that produce ALLOW
│   ├── warn/                   # Metrics that produce WARN/DELAY
│   └── block/                  # Metrics that produce BLOCK
│
├── ci/
│   └── deploy_guard.sh         # CI/CD bash gate script
│
├── .github/workflows/
│   └── guardrail.yml           # GitHub Actions pipeline
│
├── tests/                      # pytest test suite
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## How Decisions Are Made

The Decision Engine evaluates **prioritised policies** from `config/policies.yaml`.
The first matching policy wins.

| Priority | Condition | Action |
|---|---|---|
| 1 | Error budget < 10% | **BLOCK** |
| 2 | Error budget < 20% AND burn rate high/critical | **BLOCK** |
| 3 | Cost spike ≥ 30% AND burn rate high/critical | **BLOCK** |
| 4 | Burn rate high/critical | **DELAY** (30 min) |
| 5 | Error budget < 30% | **DELAY** (15 min) |
| 6 | Cost spike ≥ 20% | **WARN** |
| 7 | Latency p95 above target | **DELAY** (20 min) |
| 99 | (catch-all) | **ALLOW** |

Policies are **fully configurable** — edit `config/policies.yaml` without
touching any code.

---

## Configuring SLO Targets

Edit `config/slos.yaml`:

```yaml
slos:
  availability:
    target: 99.9           # Minimum availability %
    window_days: 30

  latency:
    p95_threshold_ms: 500  # 95th percentile ceiling
    window_days: 30

burn_rate:
  thresholds:
    low: 1.0
    medium: 2.0
    high: 5.0
    critical: 10.0
```

---

## Plugging in Real Metrics

### Replacing sample data with live Prometheus

```python
# slo/slo_engine.py — replace _load_json() with a Prometheus query:

from prometheus_api_client import PrometheusConnect

prom = PrometheusConnect(url="http://prometheus:9090")

error_rate = prom.custom_query(
    'sum(rate(http_requests_total{status=~"5.."}[30d]))'
    ' / sum(rate(http_requests_total[30d]))'
)
```

### Replacing sample cost data with AWS Cost Explorer

```python
# cost/cost_collector.py — replace _load() with a boto3 call:

import boto3

ce = boto3.client("ce", region_name="us-east-1")
response = ce.get_cost_and_usage(
    TimePeriod={"Start": start, "End": end},
    Granularity="DAILY",
    Metrics=["UnblendedCost"],
)
```

---

## Enabling the AI Explainer (LLM Backend)

The explainer defaults to a deterministic rule-based engine.
To use an LLM, set the environment variable and install the SDK:

```bash
# OpenAI
export EXPLAINER_BACKEND=openai
export OPENAI_API_KEY=sk-...
pip install openai

# Anthropic
export EXPLAINER_BACKEND=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
pip install anthropic
```

The interface is identical — no callers need to change.

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=slo --cov=cost --cov=decision --cov=ai --cov=storage \
       --cov-report=term-missing

# Specific module
pytest tests/test_decision_engine.py -v
```

---

## CI/CD Integration

The GitHub Actions workflow (`.github/workflows/guardrail.yml`) runs on every
push to `main` and `release/**`:

1. **Test Suite** — runs the full pytest suite
2. **SLO Report** — prints current reliability signals
3. **Deployment Gate** — evaluates policies; fails the pipeline if BLOCK
4. **Incident Explainer** — runs only when the gate fires (BLOCK)
5. **Audit Log** — uploaded as a GitHub Actions artifact (90-day retention)

### Integrating into an existing workflow

```yaml
- name: Reliability guardrail check
  run: |
    pip install -r requirements.txt
    bash ci/deploy_guard.sh
  env:
    SERVICE_NAME: my-service
    BRANCH_NAME:  ${{ github.ref_name }}
    COMMIT_SHA:   ${{ github.sha }}
```

Exit codes: `0` = proceed, `1` = delay, `2` = block (fails the job).

---

## What I'd Add in Production

| Enhancement | Why |
|---|---|
| Live Prometheus / Datadog integration | Replace simulated metrics with real SLIs |
| Multi-window burn rate (1h / 6h / 72h) | Google SRE-style alerting precision |
| Canary awareness | Different thresholds for canary vs. full rollout |
| Slack / PagerDuty notifications | Immediate human awareness on BLOCK |
| Postmortem auto-draft | SRE maturity — structured incident context |
| Multi-service policies | Cascade-aware deployment ordering |
| Terraform provider integration | GitOps-native infrastructure guardrails |

---

## Resume Bullet

> Designed a production-grade SLO-driven, cost-aware deployment guardrail system
> that automatically blocked or delayed CI/CD deployments based on real-time
> reliability and FinOps signals, enforcing SRE best practices and reducing
> simulated incident risk during high error-budget burn periods.

---

## License

MIT — see [LICENSE](LICENSE).
