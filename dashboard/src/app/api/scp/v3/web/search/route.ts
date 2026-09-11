import { NextResponse } from "next/server"
// [S6b security sweep] Base URL is resolved AND validated in
// scp-backend-url.ts (single PEP, no fetch sink there); this handler fetches
// only the validated base it returns.
import { resolveScpApiBase } from "../../../../../../lib/scp-backend-url"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({}))
    // [S6b security sweep] Resolve + allowlist-validate the backend base
    // BEFORE fetch (single PEP in scp-backend-url.ts). A blocked target
    // throws into the existing catch — offline shape unchanged.
    const base = resolveScpApiBase()
    const response = await fetch(`${base}/v3/web/search`, {
      method: "POST",
      cache: "no-store",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30000),
    })
    const data = await response.json().catch(() => ({ error: "Invalid search response" }))
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    return NextResponse.json({ success: false, error: error instanceof Error ? error.message : "Internet search unavailable", results: [] }, { status: 503 })
  }
}
