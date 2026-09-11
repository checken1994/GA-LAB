import { NextResponse } from "next/server"
// [S6b security sweep] Base URL is resolved AND validated in
// scp-backend-url.ts (single PEP, no fetch sink there); this handler fetches
// only the validated base it returns.
import { resolveScpApiBase } from "../../../../../../../lib/scp-backend-url"

export async function GET() {
  try {
    // [S6b security sweep] Resolve + allowlist-validate the backend base
    // BEFORE fetch (single PEP in scp-backend-url.ts). A blocked target
    // throws into the existing catch — offline shape unchanged.
    const base = resolveScpApiBase()
    const response = await fetch(`${base}/v3/hands/planner/status`, { cache: "no-store", signal: AbortSignal.timeout(5000) })
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    return NextResponse.json({ version: "3.7", planner: "offline", planCount: 0, activePlan: null, states: {}, error: error instanceof Error ? error.message : "Planner offline" }, { status: 200 })
  }
}
