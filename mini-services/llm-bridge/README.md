# SCP LLM Bridge — Ollama-compatible HTTP shim → z-ai-web-dev-sdk

A tiny Bun HTTP service that **impersonates Ollama** on port `11434` and forwards
chat/generate requests to the **z-ai-web-dev-sdk** (which talks to a real cloud
LLM). This lets SCP's LLM Gateway (`scp/llm_gateway/client.py`) work end-to-end
**without changing any SCP code or config** — its default
`OLLAMA_HOST=http://127.0.0.1:11434` just hits the bridge.

## Why

- SCP's `OllamaProvider.chat()` POSTs to `http://127.0.0.1:11434/api/chat`
  (non-reasoning models: `qwen2.5:7b`, `llama3.2`) and `/api/generate`
  (reasoning model: `deepseek-r1:8b`).
- SCP's `LLMGatewayHealth` GETs `http://127.0.0.1:11434/api/tags` to check
  which models are available.
- Ollama is **not installed** in this environment, but the
  **z-ai-web-dev-sdk** (Node/Bun) is. The bridge closes that gap.

## Endpoints

| Method | Path           | Description                                            |
|--------|----------------|--------------------------------------------------------|
| GET    | `/`            | Health / info HTML page                                |
| GET    | `/api/tags`    | Fake Ollama model list (qwen2.5:7b, llama3.2, deepseek-r1:8b) |
| GET    | `/api/version` | Fake Ollama version                                    |
| POST   | `/api/chat`    | `{model, messages, stream}` → real LLM via z-ai-web-dev-sdk |
| POST   | `/api/generate`| `{model, prompt,  stream}` → real LLM via z-ai-web-dev-sdk |

## Run

```bash
cd $SCP_ROOT/mini-services/llm-bridge
bun install           # installs z-ai-web-dev-sdk locally
bun run dev           # bun --hot index.ts  (auto-restart on change)
# → [scp-llm-bridge] listening on http://127.0.0.1:11434
```

Override port/host via env:

```bash
ZAI_BRIDGE_PORT=11435 ZAI_BRIDGE_HOST=127.0.0.1 bun run dev
```

## Test

```bash
# 1. Tags
curl -s http://127.0.0.1:11434/api/tags | jq '.models[].name'

# 2. Non-streaming chat
curl -s -X POST http://127.0.0.1:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"What is 2+2? Reply with just the number."}],"stream":false}' \
  | jq '.message.content'

# 3. Generate (single prompt — used by SCP for reasoning models)
curl -s -X POST http://127.0.0.1:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-r1:8b","prompt":"What is the capital of France? Reply with just the name.","stream":false}' \
  | jq '.response'
```

## SCP integration

Start the bridge first, then start SCP — its default `OLLAMA_HOST` already
points at `127.0.0.1:11434`:

```bash
# Terminal 1: bridge
cd $SCP_ROOT/mini-services/llm-bridge && bun run dev

# Terminal 2: SCP
cd $SCP_ROOT && python3 -m scp 8002

# Test
curl -s -X POST http://127.0.0.1:8002/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the capital of France?"}' | jq .
```

## Model handling

The `model` field in incoming requests is **accepted but ignored** —
z-ai-web-dev-sdk selects its own backend model. We surface the requested model
name back in the response so SCP's task-routing / stats logging stays
consistent. `/api/tags` advertises exactly the three models SCP's
`TASK_MODEL_MAP` uses (`deepseek-r1:8b`, `qwen2.5:7b`, `llama3.2`).

## Streaming

For `stream: true` requests we emit NDJSON with one content chunk + a final
`done: true` envelope. (SCP's `OllamaProvider` only uses `stream: false`, so
this is sufficient for end-to-end `/ask` to work. Real token-by-token streaming
from the SDK is a future enhancement.)

## Rate-limit handling

`z-ai-web-dev-sdk`'s backend (`internal-api.z.ai`) enforces a strict request
rate. SCP's `/ask` fires ~20–50 parallel LLM calls (judge / why / learning /
fast_learning / etc.) per request, which would all 429 if fired simultaneously.
The bridge has two layers of defense:

1. **Concurrency queue** (`MAX_CONCURRENT_ZAI_CALLS=1` by default,
   `MAX_QUEUE_DEPTH=16`). All SDK calls are serialized through a single slot
   so we don't burst-fire. If the queue is full, the bridge returns HTTP 502
   immediately so SCP can fall back to its SLMs fast instead of stalling.
   Tune via env: `ZAI_BRIDGE_CONCURRENCY=2 ZAI_BRIDGE_QUEUE_DEPTH=32`.
2. **Exponential backoff retries on 429**: 500ms → 1000ms → 2000ms (4 attempts
   total per call). Logged as `[llm-bridge] 429 rate-limit on attempt N/4,
   retrying in Xms...`.

When all retries are exhausted, the bridge returns HTTP 502 with an Ollama-style
`{"error": "..."}` body. SCP's `OllamaProvider.chat()` catches the exception and
returns `(None, "ollama:<model>")`, which triggers SCP's SLM-fallback path —
so `/ask` still returns a valid answer even when the LLM is fully rate-limited.

## Verified end-to-end behavior

| Scenario | Result |
|---|---|
| `GET /api/tags` | Returns 3 models (deepseek-r1:8b, qwen2.5:7b, llama3.2) ✓ |
| `POST /api/chat` (single, SDK healthy) | Returns real LLM answers (e.g. "4" for "What is 2+2?", "Paris" for "Capital of France?", "hello" for "Reply with the single word: hello") ✓ |
| `POST /api/generate` (single, SDK healthy) | Returns real LLM answers (e.g. "Paris") ✓ |
| `POST /api/chat` with `stream:true` | Returns NDJSON with content chunk + done envelope ✓ |
| `POST /api/chat` (SDK 429) | Returns `{"error":"..."}` HTTP 502 — SCP falls back to SLMs ✓ |
| SCP `POST /ask` integration | SCP's `httpx` log shows `POST http://127.0.0.1:11434/api/chat` — bridge is hit; SCP returns valid answer via LLM (when SDK healthy) or via SLM fallback (when SDK rate-limited) ✓ |

## Honest limitations

- This is a **shim**, not a real Ollama. No model files, no real digests.
- The `total_duration`/`eval_count` etc. timing fields are stubbed to `0`
  because z-ai-web-dev-sdk doesn't expose token-level metrics in a stable way.
- One ZAI client is shared across all requests (singleton) for connection
  reuse. If `ZAI.create()` fails on first call, the bridge returns HTTP 502 to
  `/api/chat` and `/api/generate` so SCP's gateway can fall back.
- **z-ai-web-dev-sdk rate limit (429)** is the main real-world bottleneck.
  Under SCP's bursty `/ask` load (20–50 parallel LLM calls), most calls 429
  even with serialization + retries. SCP's graceful SLM-fallback path means
  `/ask` still returns correct answers (e.g. "Paris" via GeoSLM) even when
  the LLM is fully rate-limited. To get a 100% LLM-sourced answer through
  SCP, you'd need either a higher-tier z-ai-web-dev-sdk API key or to wait
  several minutes between `/ask` calls for the quota to recover.
- The streaming implementation sends the full content as a single chunk
  rather than token-by-token. This is sufficient for SCP (which only uses
  `stream: false`) but is not a true streaming experience for other clients.
