import { NextResponse } from "next/server"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function GET() {
  const base = process.env.SCP_API_URL || "http://127.0.0.1:8000"
  try {
    const response = await fetch(`${base}/v3/hands/status`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(5000),
    })
    const data = await response.json().catch(() => ({ hands: "offline" }))
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    return NextResponse.json({ hands: "offline", version: "3.2", error: error instanceof Error ? error.message : "Hands unavailable" }, { status: 503 })
  }
}
