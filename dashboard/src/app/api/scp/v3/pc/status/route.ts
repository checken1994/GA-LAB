import { NextResponse } from "next/server"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function GET() {
  const base = process.env.SCP_API_URL || "http://127.0.0.1:8000"
  try {
    const response = await fetch(`${base}/v3/pc/status`, { cache: "no-store", headers: { Accept: "application/json" }, signal: AbortSignal.timeout(5000) })
    const data = await response.json().catch(() => ({ error: "Invalid PC Controller response" }))
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    return NextResponse.json({ controller: "offline", error: error instanceof Error ? error.message : "PC Controller unavailable" }, { status: 503 })
  }
}
