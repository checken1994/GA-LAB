# syntax=docker/dockerfile:1.7
# SCP API — reproducible local/container candidate.
# This image does not bundle Ollama, provider credentials, datasets, or private evidence.

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    SCP_HOST=0.0.0.0 \
    SCP_PORT=8000 \
    SCP_DATA_DIR=/var/lib/scp/data

WORKDIR /app

# Install only pinned runtime dependencies. Build tools are intentionally absent.
COPY scp/requirements.txt /tmp/scp-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/scp-requirements.txt

# Copy source only. .dockerignore excludes .env, private evidence, caches and VCS data.
COPY scp ./scp

# The API may create runtime state under SCP_DATA_DIR; keep it writable without
# granting the process root privileges.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin scp \
    && install --directory --owner=scp --group=scp /var/lib/scp/data \
    && chown -R scp:scp /app

USER scp
EXPOSE 8000

# Liveness is deliberately separate from readiness: /health can be 200 while
# startup dependencies are still initializing; /ready is the promotion gate.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

ENTRYPOINT ["python", "-m", "scp"]
