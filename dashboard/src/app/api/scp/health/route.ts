/**
 * API /api/scp/health — composite health check across all 3 SCP subsystems.
 *
 * Makes the dashboard a CONTROL PANEL (not just a static report).
 *
 * [Task 1-A · Fix 4-d-010] Previously this endpoint ONLY probed the FastAPI
 * Python backend on port 8002. So "SCP online" was a false-green whenever
 * the loop-scheduler (port 3030) or the llm-bridge (port 11434) was dead
 * — even though SCP's autofix engine depends on the LLM bridge. Now this
 * endpoint probes all 3 services in parallel with 1s timeouts and returns
 * a composite status. DNA #19 (observation gap closed) + #22 (PASS ≠ TRUE:
 * "online" no longer claimed from a single-subsystem probe) + #26 (reality
 * test).
 *
 * Backward compat: the legacy `scp: "online"|"degraded"|"offline"` field is
 * preserved for existing consumers (scp-control-panel.tsx). It is derived
 * from the new composite: "online" only if all 3 services ok.
 *
 * SCP started via:    SCP_PORT=8002 python -m scp
 * Scheduler started via: bun run mini-services/loop-scheduler
 * LLM bridge started via: bun run mini-services/llm-bridge
 */
import { NextRequest, NextResponse } from "next/server"


const SCP_BASE_URL =
  process.env.SCP_INTERNAL_URL ?? "http://127.0.0.1:8002"
const LOOP_SCHEDULER_URL =
  process.env.LOOP_SCHEDULER_URL ?? "http://127.0.0.1:3030"
const LLM_BRIDGE_URL =
  process.env.LLM_BRIDGE_URL ?? "http://127.0.0.1:11434"

const START_HINTS = {
  fastapi: "Run: SCP_PORT=8002 python -m scp (in your scp folder)",
  loopScheduler: "Run: bun run mini-services/loop-scheduler (in project root)",
  llmBridge: "Run: bun run mini-services/llm-bridge (in project root)",
}

interface ServiceHealth {
  ok: boolean
  latencyMs: number | null
  status?: number
  error?: string
  hint?: string
}

/**
 * Probe one HTTP endpoint with a hard timeout. Returns the latency in ms
 * if the response was ok, or `{ ok: false }` with the error otherwise.
 * DNA #7: fail-open — never throws.
 */
async function probe(
  url: string,
  timeoutMs = 1000,
): Promise<ServiceHealth> {
  const t0 = Date.now()
  try {
    const res = await fetch(url, {
      signal: AbortSignal.timeout(timeoutMs),
      headers: { Accept: "application/json" },
      cache: "no-store",
    })
    const latencyMs = Date.now() - t0
    if (res.ok) {
      return { ok: true, latencyMs, status: res.status }
    }
    return { ok: false, latencyMs, status: res.status }
  } catch (e) {
    const latencyMs = Date.now() - t0
    const err = e instanceof Error ? e.message : String(e)
    return { ok: false, latencyMs, error: err.slice(0, 200) }
  }
}

export async function GET(request: NextRequest) {
  const _url = request.url
  const checkedAt = new Date().toISOString()

  // Probe all 3 services in parallel. DNA #19: cover observation gaps.
  // Promise.allSettled so one slow service can't block the others.
  const [fastapiResult, loopResult, llmResult] = await Promise.allSettled([
    probe(`${SCP_BASE_URL}/health`),
    // loop-scheduler exposes /healthz per mini-services/loop-scheduler/index.ts
    // (falls back to "/" if 404 — see below).
    probe(`${LOOP_SCHEDULER_URL}/healthz`).then(async (h) => {
      if (h.ok || h.status !== 404) return h
      // Retry with "/" if /healthz is not implemented.
      return probe(`${LOOP_SCHEDULER_URL}/`)
    }),
    // llm-bridge (Ollama-compatible API) exposes /api/tags — list of installed models.
    probe(`${LLM_BRIDGE_URL}/api/tags`),
  ])

  const fastapi: ServiceHealth =
    fastapiResult.status === "fulfilled"
      ? { ...fastapiResult.value, hint: START_HINTS.fastapi }
      : { ok: false, latencyMs: null, error: "probe rejected", hint: START_HINTS.fastapi }
  const loopScheduler: ServiceHealth =
    loopResult.status === "fulfilled"
      ? { ...loopResult.value, hint: START_HINTS.loopScheduler }
      : { ok: false, latencyMs: null, error: "probe rejected", hint: START_HINTS.loopScheduler }
  const llmBridge: ServiceHealth =
    llmResult.status === "fulfilled"
      ? { ...llmResult.value, hint: START_HINTS.llmBridge }
      : { ok: false, latencyMs: null, error: "probe rejected", hint: START_HINTS.llmBridge }

  const overall = fastapi.ok && loopScheduler.ok && llmBridge.ok

  // Backward-compat derivation: legacy `scp` field that the control panel
  // already consumes. "online" only if FastAPI responds 200.
  // "degraded" if FastAPI is up but a sibling service is down.
  // "offline" if FastAPI itself is unreachable.
  const scp: "online" | "degraded" | "offline" = fastapi.ok
    ? (overall ? "online" : "degraded")
    : "offline"

  const httpStatus = overall ? 200 : fastapi.ok ? 200 : 503

  return NextResponse.json(
    {
      // Legacy fields (backward compat for scp-control-panel.tsx).
      scp,
      hint: scp === "online" ? null : START_HINTS.fastapi,
      // Composite fields (new in Task 1-A — Fix 4-d-010).
      overall,
      fastapi,
      loopScheduler,
      llmBridge,
      checkedAt,
    },
    { status: httpStatus },
  )
}
