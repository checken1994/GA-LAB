# Deploying SCP on Google Cloud Platform

## Prerequisites
- GCP project with Cloud Run enabled
- Docker installed locally
- `gcloud` CLI authenticated

## Steps

### 1. Build and push image
```bash
docker build -t gcr.io/<PROJECT_ID>/scp-cli:latest .
docker push gcr.io/<PROJECT_ID>/scp-cli:latest
```

### 2. Deploy to Cloud Run
```bash
gcloud run deploy scp-api \
  --image gcr.io/<PROJECT_ID>/scp-cli:latest \
  --region asia-southeast1 \
  --set-env-vars OPENROUTER_API_KEY=<your-key> \
  --allow-unauthenticated \
  --port 8080
```

### 3. Verify
```bash
curl https://<CLOUD_RUN_URL>/health
```