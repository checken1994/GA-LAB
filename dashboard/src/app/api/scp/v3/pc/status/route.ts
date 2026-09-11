import { NextResponse } from "next/server"
// [S6b security sweep] Base URL is resolved AND validated in
// scp-backend-url.ts (single PEP, no fetch sink there); this handler fetches
// only the validated base it returns.
import { resolveScpApiBase } from "../../../../../../lib/scp-backend-url"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function GET() {
  try {
    const headers: Record<string, string> = { Accept: "application/json" }
    if (process.env.SCP_PC_CONTROLLER_TOKEN) {
      headers["X-SCP-PC-Token"] = process.env.SCP_PC_CONTROLLER_TOKEN
    }
    // [S6b security sweep] Resolve + allowlist-validate the backend base
    // BEFORE fetch (single PEP in scp-backend-url.ts). A blocked target
    // throws into the existing catch — offline shape unchanged.
    const base = resolveScpApiBase()
    const response = await fetch(`${base}/v3/pc/status`, { cache: "no-store", headers, signal: AbortSignal.timeout(5000) })
    const data = await response.json().catch(() => ({ error: "Invalid PC Controller response" }))
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    return NextResponse.json({ controller: "offline", error: error instanceof Error ? error.message : "PC Controller unavailable" }, { status: 503 })
  }
}
