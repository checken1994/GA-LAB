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
COPY pyproject.toml setup.cfg* README* ./

# Install the package itself
RUN uv pip install --system --no-cache -e . 2>/dev/null || pip install --no-cache-dir -e .

# Environment variable placeholders (override at runtime)
ENV OPENROUTER_API_KEY=""
ENV OPENROUTER_MODEL="deepseek/deepseek-v4-flash-0731"
ENV OPENROUTER_MODEL_AUTO="0"
ENV SCP_FALLBACK_WATCH_INTERVAL="21600"
ENV SCP_RETRY_TIMEOUT_SEC="300"
ENV SCP_KW_ENABLE="0"

EXPOSE 8080

ENTRYPOINT ["python", "-m", "scp"]
CMD ["--help"]