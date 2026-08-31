# Getting Started with SCP

SCP (SCP-OS) is an autonomous AI agent operating system built on top of LLM APIs.

## Installation

### Via pip
```bash
pip install scp-cli
```

### Via uv
```bash
uv pip install scp-cli
```

### Via Docker
```bash
docker pull scp/cli:latest
docker run -e OPENROUTER_API_KEY=<your-key> scp/cli:latest
```

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:
```env
OPENROUTER_API_KEY=your-key-here
OPENROUTER_MODEL=deepseek/deepseek-v4-flash-0731
OPENROUTER_MODEL_AUTO=0
```

## Quick Start

```bash
# Start the SCP API server
python -m scp

# Run a benchmark
python -m scp.benchmark.benchmark_suite

# Start observability stack (requires Docker)
docker compose -f docker-compose.observability.yml up -d
```

## Features
- Multi-provider LLM gateway with circuit breaker and failover
- Task kernel with checkpoint and auto-recovery
- HandsPlanner for step-by-step action execution
- OpenTelemetry observability (Grafana + Prometheus + Loki)
- Benchmark suite (MMLU, GSM-8K, Code-generation)
- Knowledge warehouse with FAISS embeddings