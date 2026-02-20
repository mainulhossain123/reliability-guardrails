"""
checkout-api — Sample HTTP service with configurable failure injection.

Simulates a realistic microservice by emitting Prometheus-compatible
metrics and injecting random latency spikes and error responses so the
SLO engine always has interesting data to evaluate.
"""

import os
import random
import time

from flask import Flask, jsonify, request
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)

app = Flask(__name__)

# ── Prometheus instruments ────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
    buckets=[0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 2.5, 5.0],
)

# ── Config (overridable via environment) ──────────────────────────────────────

ERROR_RATE = float(os.getenv("APP_ERROR_RATE", "0.02"))    # 2 % synthetic errors
SLOW_RATE  = float(os.getenv("APP_SLOW_RATE",  "0.10"))    # 10 % slow responses
SLOW_MIN_S = float(os.getenv("APP_SLOW_MIN",   "0.5"))
SLOW_MAX_S = float(os.getenv("APP_SLOW_MAX",   "1.5"))

# ── Helpers ───────────────────────────────────────────────────────────────────

def _track(endpoint: str, status: int, start: float) -> None:
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=endpoint,
        status_code=str(status),
    ).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start)


def _maybe_slow() -> None:
    """Inject artificial latency on a configurable percentage of requests."""
    if random.random() < SLOW_RATE:
        time.sleep(random.uniform(SLOW_MIN_S, SLOW_MAX_S))


def _maybe_error(endpoint: str, start: float):
    """Return a 500 response on a configurable percentage of requests."""
    if random.random() < ERROR_RATE:
        _track(endpoint, 500, start)
        return jsonify({"error": "Internal Server Error"}), 500
    return None

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    start = time.time()
    _maybe_slow()
    err = _maybe_error("/", start)
    if err:
        return err
    _track("/", 200, start)
    return jsonify({"status": "ok", "service": "checkout-api"})


@app.get("/checkout")
def checkout():
    start = time.time()
    _maybe_slow()
    err = _maybe_error("/checkout", start)
    if err:
        return err
    _track("/checkout", 200, start)
    return jsonify({"order_id": random.randint(100000, 999999), "status": "accepted"})


@app.get("/health")
def health():
    return jsonify({"status": "healthy", "version": "1.0.0"}), 200


@app.get("/metrics")
def metrics():
    """Prometheus scrape endpoint."""
    return generate_latest(REGISTRY), 200, {"Content-Type": CONTENT_TYPE_LATEST}


# ── Entry-point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
