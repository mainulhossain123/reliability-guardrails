# SLO-Driven Deployment Guardrails

[![CI Pipeline](https://github.com/mainulhossain123/reliability-guardrails/actions/workflows/guardrail.yml/badge.svg)](https://github.com/mainulhossain123/reliability-guardrails/actions/workflows/guardrail.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://docs.docker.com/compose/)

An automated deployment gate that **allows, delays, or blocks** CI/CD pipelines based on real-time SLO health and cloud cost signals — with a live web dashboard and full audit trail.

---

## Features

### 🛡️ SLO Engine
- Calculates error budget remaining (30-day rolling window)
- Classifies burn rate: low / medium / high / critical
- Evaluates p95 and p99 latency compliance
- Configurable targets via `config/slos.yaml`

### 💰 Cost Collector
- Week-over-week cloud spend analysis
- Spike detection with configurable thresholds
- Trend classification: stable / rising / spiking / falling
- Pluggable data source (default: `data/cost.json`)

### ⚖️ Decision Engine
- Single-responsibility policy evaluator
- Eight prioritised guardrail rules, first-match wins
- Returns `ALLOW`, `WARN`, `DELAY`, or `BLOCK`
- CI exit codes: `0` = allow/warn, `1` = delay, `2` = block

### 🤖 Incident Explainer
- Human-readable narrative for every deployment decision
- Rule-based by default; LLM-ready via environment variable
- Supports OpenAI and Anthropic as backend providers

### 📊 Web Dashboard
- Live dark-mode UI at `http://localhost:5000`
- Auto-refreshes every 30 seconds
- Full policy evaluation trace, audit log, and simulate button

### 📁 Audit Trail
- Every gate evaluation written to JSONL at `data/audit/decisions-YYYY-MM-DD.jsonl`
- Uploaded as a GitHub Actions artifact (90-day retention)

---

## Architecture

```
Git Push
    |
    v
+-------------------+
|   Test Suite      |
+-------------------+
    |
    v
+-------------------+     +-------------------+
|   SLO Engine      |     |  Cost Collector   |
|  (error budget,   |     |  (WoW spend,      |
|   burn rate,      |     |   spike detect)   |
|   latency)        |     |                   |
+--------+----------+     +----------+--------+
         |                           |
         +----------+----------------+
                    |
                    v
         +--------------------+
         |  Decision Engine   |
         |  (policies.yaml)   |
         +--------------------+
                    |
         +----------+----------+
         |          |          |
      ALLOW       WARN      DELAY / BLOCK
                    |
                    v
         +--------------------+     +-------------------+
         |  Incident          |     |  Audit Log        |
         |  Explainer         |     |  (JSONL)          |
         +--------------------+     +-------------------+
```

---

## Quick Start

**Requirements:** Docker and Docker Compose

```bash
git clone https://github.com/mainulhossain123/reliability-guardrails.git
cd reliability-guardrails

# Start the web dashboard
docker compose up dashboard -d
# Open http://localhost:5000

# Run the full test suite
docker compose run --rm test

# One-shot CLI tools
docker compose run --rm slo        # SLO status report
docker compose run --rm cost       # Cost analysis report
docker compose run --rm decision   # Deployment gate
docker compose run --rm explainer  # Incident narrative
```

**Without Docker:**

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m slo.slo_engine
python -m cost.cost_collector
python -m decision.decision_engine
python -m ai.incident_explainer
```

---

## Dashboard

The web UI at `http://localhost:5000` shows:

| Panel | Contents |
|---|---|
| Decision banner | ALLOW / WARN / DELAY / BLOCK with matched policy and reason |
| SLO card | Error budget bar, burn rate classification, latency p95/p99 |
| Cost card | 30-day spend chart, WoW % change, trend label |
| Policy trace | Each policy evaluated, whether it matched, and why |
| Explainer | Human-readable narrative generated for the current decision |
| Audit log | Every gate run in the current session with timestamps |

Click **Run Deployment Gate** to evaluate all signals, write an audit record, and display the result in a modal.

---

## Service Access Points

| Service | URL | Purpose |
|---|---|---|
| Dashboard | http://localhost:5000 | Live web UI |
| Sample app | http://localhost:8080 | Metrics endpoint |
| API — SLO | http://localhost:5000/api/slo | SLO engine result |
| API — Cost | http://localhost:5000/api/cost | Cost analysis result |
| API — Decision | http://localhost:5000/api/decision | Gate decision |
| API — All | http://localhost:5000/api/all | Combined payload |

---

## Decision Logic

Policies in `config/policies.yaml` are evaluated top-to-bottom. First match wins.

| ID | Name | Condition | Action |
|---|---|---|---|
| P001 | Critical budget exhaustion | Error budget < 10% | BLOCK |
| P002 | Low budget + high burn | Budget < 20% **and** burn is high or critical | BLOCK |
| P003 | Cost spike during incident | Cost spike >= 30% **and** burn is high or critical | BLOCK |
| P004 | High burn rate | Burn rate is high or critical | DELAY 30 min |
| P005 | Moderate budget consumed | Error budget < 30% | DELAY 15 min |
| P006 | Significant cost spike | Cost spike >= 20% | WARN |
| P007 | Latency SLO breach | p95 latency above target | DELAY 20 min |
| P008 | Catch-all | _(always matches)_ | ALLOW |

All thresholds are editable in `config/policies.yaml` — no code changes required.

---

## API Reference

### SLO Engine

```
GET /api/slo
```

```json
{
  "ok": true,
  "data": {
    "error_budget_pct": 91.9,
    "burn_rate_label": "low",
    "burn_rate_value": 0.25,
    "latency_ok": true,
    "p95_ms": 480,
    "p99_ms": 820,
    "within_budget": true
  }
}
```

### Cost Collector

```
GET /api/cost
```

```json
{
  "ok": true,
  "data": {
    "current_week_avg": 58.4,
    "prior_week_avg": 46.7,
    "wow_change_pct": 25.1,
    "trend": "rising",
    "spike_detected": false
  }
}
```

### Decision Engine

```
GET  /api/decision
POST /api/simulate
```

```json
{
  "ok": true,
  "data": {
    "action": "WARN",
    "policy_id": "P006",
    "policy_name": "Significant cost spike",
    "reason": "Cloud costs increased significantly week-over-week",
    "remediation": "Review resource usage and scaling events before proceeding."
  }
}
```

### Full Payload

```
GET /api/all
```

Returns SLO, cost, decision, explanation, and audit log combined in a single response.

---

## Configuration

### SLO targets — `config/slos.yaml`

```yaml
slos:
  availability:
    target: 99.9           # minimum availability %
    window_days: 30
  latency:
    p95_threshold_ms: 500
    p99_threshold_ms: 1000

burn_rate:
  thresholds:
    low: 1.0
    medium: 2.0
    high: 5.0
    critical: 10.0
```

### AI Explainer backend

The explainer defaults to rule-based output. To switch to an LLM:

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

### Plugging in real metrics

Replace `data/metrics.json` with data from Prometheus or your APM tool:

```json
{
  "total_requests": 2592000,
  "failed_requests": 2100,
  "p95_latency_ms": 480,
  "p99_latency_ms": 820,
  "burn_rates": [0.9, 1.1, 1.4, 2.1, 3.1]
}
```

Replace `data/cost.json` with daily cost records from AWS Cost Explorer or your cloud billing API.

---

## Project Structure

```
reliability-guardrails/
├── app/                    # Sample Flask microservice with Prometheus metrics
├── slo/                    # SLO engine: error budget, burn rate, latency
├── cost/                   # Cost collector: WoW analysis, spike detection
├── decision/               # Decision engine: policy evaluator
├── ai/                     # Incident explainer: rule-based + LLM-ready
├── storage/                # Audit log: append-only JSONL
├── dashboard/              # Web dashboard: Flask backend + dark-mode UI
├── config/
│   ├── slos.yaml           # SLO targets and burn rate thresholds
│   └── policies.yaml       # Guardrail policy rules
├── data/
│   ├── metrics.json        # Sample service metrics (replace with real data)
│   ├── cost.json           # Sample cost records (replace with real data)
│   ├── resources.json      # Sample resource inventory
│   └── audit/              # JSONL audit log output
├── tests/                  # pytest suite — 80 tests across 6 files
├── ci/
│   └── deploy_guard.sh     # Bash gate script for any CI pipeline
├── .github/
│   └── workflows/
│       └── guardrail.yml   # GitHub Actions pipeline
├── docker-compose.yml      # All services: app, slo, cost, decision, dashboard, test
└── Dockerfile              # Shared Python 3.12 image
```

---

## Testing

```bash
# Run all 80 tests via Docker (no local Python required)
docker compose run --rm test

# Run locally
pytest tests/ -v --tb=short

# Run with coverage
pytest tests/ \
  --cov=slo --cov=cost --cov=decision --cov=ai --cov=storage \
  --cov-report=term-missing
```

| Test File | Coverage |
|---|---|
| `test_slo_engine.py` | Error budget, burn rate, latency, edge cases |
| `test_cost_collector.py` | WoW calculation, spike detection, trend labels |
| `test_decision_engine.py` | All 8 policies, priority ordering, exit codes |
| `test_incident_explainer.py` | Rule-based narratives, all decision types |
| `test_audit_log.py` | JSONL write, read, daily rotation |
| `test_app.py` | Sample Flask app endpoints |

---

## CI/CD Integration

The included GitHub Actions workflow (`.github/workflows/guardrail.yml`) runs on every push to `main` or `release/**`:

1. **Test suite** — pytest with coverage uploaded to Codecov
2. **SLO report** — prints current error budget and cost signals to the job log
3. **Deployment gate** — fails the job on BLOCK (exit `2`) or DELAY (exit `1`)
4. **Incident explainer** — generates a narrative when the gate blocks
5. **Audit upload** — uploads `data/audit/` as a workflow artifact (90-day retention)

### Adding the gate to an existing pipeline

```yaml
- name: Reliability guardrail check
  run: |
    pip install -r requirements.txt
    bash ci/deploy_guard.sh
  env:
    SERVICE_NAME: my-service
    BRANCH_NAME:  ${{ github.ref_name }}
    COMMIT_SHA:   ${{ github.sha }}
    PYTHONPATH:   ${{ github.workspace }}
```

Exit codes: `0` = allow/warn &nbsp; `1` = delay &nbsp; `2` = block

---

## Development

### Local setup

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Running individual modules

```bash
python -m slo.slo_engine            # Print SLO report
python -m cost.cost_collector       # Print cost report
python -m decision.decision_engine  # Run deployment gate
python -m ai.incident_explainer     # Generate incident narrative
python -m dashboard.app             # Start web dashboard on :5000
```

### Docker services

| Service | Command | Description |
|---|---|---|
| `app` | `docker compose up app` | Sample microservice on port 8080 |
| `dashboard` | `docker compose up dashboard -d` | Web UI on port 5000 |
| `slo` | `docker compose run --rm slo` | One-shot SLO report |
| `cost` | `docker compose run --rm cost` | One-shot cost report |
| `decision` | `docker compose run --rm decision` | One-shot gate evaluation |
| `explainer` | `docker compose run --rm explainer` | One-shot incident narrative |
| `test` | `docker compose run --rm test` | Full test suite |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'feat: add your feature'`
4. Push and open a Pull Request

---

## License

MIT — see [LICENSE](LICENSE) for details.
