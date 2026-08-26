import { NextResponse } from "next/server"

export async function GET() {
  const base = process.env.SCP_API_URL || "http://127.0.0.1:8002"
  try {
    const response = await fetch(`${base}/v3/hands/planner/status`, { cache: "no-store", signal: AbortSignal.timeout(5000) })
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    return NextResponse.json({ version: "3.7", planner: "offline", planCount: 0, activePlan: null, states: {}, error: error instanceof Error ? error.message : "Planner offline" }, { status: 200 })
  }
}
