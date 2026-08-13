# SCP Mini-Services

Bun-based sidecar services that extend SCP Python with capabilities that
don't belong in the FastAPI process (long-running LLM calls, cron loops,
stateful bridges). They run alongside SCP (port 8000) and the Next.js
dashboard (port 3000) and talk to each other over `127.0.0.1`.

## Services

| Service          | Port  | Purpose                                                              | Status      |
| ---------------- | ----- | -------------------------------------------------------------------- | ----------- |
| `llm-bridge`     | 11434 | Bridges SCP's LLM gateway to a local Ollama-compatible HTTP server (so SCP can call LLMs without each call going through the public OpenRouter / OpenAI APIs). | R10 NEW     |
| `loop-scheduler` | 3030  | Closed-loop scheduler. Every N seconds, calls SCP's `POST /v105/autofix/run-audit` to trigger a deep audit cycle, logs the result, exposes a status dashboard. | R10 NEW     |

## Start both

```bash
# Terminal 1 — LLM bridge
cd /home/z/my-project/mini-services/llm-bridge
bun run dev

# Terminal 2 — Loop scheduler
cd /home/z/my-project/mini-services/loop-scheduler
bun run dev

# Terminal 3 — SCP
cd /home/z/my-project
python3 -m scp 8000

# Terminal 4 — Next.js dashboard
cd /home/z/my-project
bun run dev
```

Both mini-services are **fail-open** — if SCP is offline, they log the
miss and keep ticking. They never crash the SCP process or the dashboard.

## Gateway XTransformPort pattern

The Caddy gateway (`/home/z/my-project/Caddyfile`) routes traffic based
on the `?XTransformPort=<n>` query parameter:

- `?XTransformPort=8000` → SCP Python (port 8000)
- `?XTransformPort=3030` → loop-scheduler (port 3030)
- `?XTransformPort=11434` → llm-bridge (port 11434)
- (no param) → Next.js dashboard (port 3000)

This follows the orchestrator rule: **"DO NOT write port in the api
request url, only XTransformPort"**. No `:8000` / `:3030` / `:11434`
ever appears in a public gateway URL — only in internal `127.0.0.1`
calls between services.

```bash
# Reach the loop scheduler through the gateway:
curl 'https://<gateway-host>:<gateway-port>/?XTransformPort=3030'
```

The Next.js dashboard does NOT use the gateway — it calls the mini-services
directly via `127.0.0.1:3030` (server-side fetch in
`src/app/api/scp/loop/route.ts`). End users only see `/api/scp/loop` on
the dashboard.

## Why mini-services (not part of SCP Python)?

1. **Separate failure domains.** A crash in the LLM bridge or scheduler
   must NOT take down SCP's FastAPI server (which serves /ask, /health,
   the WebSocket). Process isolation gives us that for free.
2. **Different runtime.** Bun (TypeScript) is faster to iterate on for
   stateful orchestrators + HTTP clients than CPython. SCP's runtime
   (judge / SLMs / streaming) is already CPU-bound on CPython — we don't
   want to add I/O-bound cron work to its event loop.
3. **Independent lifecycle.** Restarting the scheduler shouldn't restart
   SCP (which has a 90-second cold start). Restarting SCP shouldn't drop
   in-flight LLM bridge requests.

## See also

- `llm-bridge/README.md` — LLM bridge details
- `loop-scheduler/README.md` — loop scheduler details
- `/home/z/my-project/scp/GATEWAY.md` — gateway URL pattern (XTransformPort)
- `/home/z/my-project/src/app/api/scp/loop/route.ts` — dashboard proxy to loop-scheduler
