# Top-level Dockerfile used by CI runners, the decision engine,
# and the test service (docker compose run --rm test)

FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source
COPY . .

ENV PYTHONPATH=/app \
    LOG_LEVEL=INFO

ENTRYPOINT ["python"]
CMD ["-m", "decision.decision_engine"]
