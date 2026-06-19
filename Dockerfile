# Minimal Web UI image — Cookie/Edge sync and browser extension require host setup.
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY config/config.example.yaml ./config/config.example.yaml

RUN pip install --no-cache-dir -e ".[web,bilibili]"

ENV OSINT_DATA_DIR=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8787

VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8787/api/extension/status || exit 1

CMD ["python", "-m", "osint_toolkit.cli", "web", "--host", "0.0.0.0", "--port", "8787"]
