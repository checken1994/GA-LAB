# Deploying SCP Locally

## Requirements
- Python 3.11+
- Docker (for observability stack)
- At least one OpenRouter API key

## Steps

### 1. Clone and install
```bash
git clone <repo-url> scp
cd scp
pip install -e scp/
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Run
```bash
python -m scp
```

### 4. Start observability (optional)
```bash
docker compose -f docker-compose.observability.yml up -d
# Access Grafana at http://localhost:3000 (admin / scp_admin)
```

### 5. Run benchmark
```bash
python -m scp.benchmark.benchmark_suite
```