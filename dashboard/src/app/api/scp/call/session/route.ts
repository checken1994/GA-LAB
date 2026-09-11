import { readFile } from "node:fs/promises"
import { NextResponse } from "next/server"
// [S6b security sweep] Base URL is resolved AND validated in
// scp-backend-url.ts (single PEP, no fetch sink there); this handler fetches
// only the validated base it returns.
import { resolveScpProxyBase } from "../../../../../lib/scp-backend-url"

export const dynamic = "force-dynamic"
export const revalidate = 0

const TOKEN_FILE = process.env.SCP_AUTH_TOKEN_SECRET_FILE?.trim()

async function readAdminToken() {
  const direct = process.env.SCP_AUTH_TOKEN_SECRET?.trim()
  if (direct) return direct
  if (!TOKEN_FILE) return ""
  try { return (await readFile(TOKEN_FILE, "utf8")).trim() } catch { return "" }
}

export async function POST() {
  try {
    const token = await readAdminToken()
    if (!token) return NextResponse.json({ error: "SCP auth token chưa được cấu hình" }, { status: 503 })
    // [S6b security sweep] Resolve + allowlist-validate the backend base
    // BEFORE fetch (single PEP in scp-backend-url.ts). A blocked target
    // throws into the existing catch — response shape unchanged.
    const base = resolveScpProxyBase()
    const response = await fetch(`${base}/v3/call/sessions`, {
      method: "POST",
      headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    })
    const text = await response.text()
    let data: unknown = {}
    try { data = JSON.parse(text) } catch { data = { error: text.slice(0, 300) } }
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message.slice(0, 300) : "Không kết nối được SCP" }, { status: 502 })
  }
}
