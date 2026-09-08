# SCP CLI Docker Image
# Base: python:3.12-slim with uv for fast dependency installation
FROM python:3.12-slim

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY scp/requirements.txt scp/requirements-otel.txt ./

# Install dependencies
RUN uv pip install --system --no-cache -r requirements.txt || pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY scp/ ./scp/
COPY README* ./


# Environment variable placeholders (override at runtime)
ENV OPENROUTER_API_KEY=""
ENV OPENROUTER_MODEL="deepseek/deepseek-v4-flash-0731"
ENV OPENROUTER_MODEL_AUTO="0"
ENV SCP_FALLBACK_WATCH_INTERVAL="21600"
ENV SCP_RETRY_TIMEOUT_SEC="300"
ENV SCP_KW_ENABLE="0"

EXPOSE 8080

RUN useradd -u 10001 -m scpuser && \
    mkdir -p /app/data && \
    chown -R scpuser:scpuser /app/data
USER 10001

ENTRYPOINT ["python", "-m", "scp"]
CMD ["--help"]