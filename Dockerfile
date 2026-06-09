# ── Stage 1: Build wheel ───────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --upgrade pip build

COPY pyproject.toml README.md ./
COPY cortexflow/ ./cortexflow/

RUN python -m build --wheel --outdir /dist

# ── Stage 2: Runtime image ─────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# libsndfile: required by soundfile (voice/audio processing)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /dist/*.whl /tmp/wheels/

RUN pip install --no-cache-dir /tmp/wheels/*.whl \
    && rm -rf /tmp/wheels

# Data directory for SQLite memory and workspace files
RUN mkdir -p /root/.cortexflow/workspace

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 7432

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fs http://localhost:7432/health || exit 1

ENTRYPOINT ["cortex"]
CMD ["start", "--bind", "0.0.0.0"]
