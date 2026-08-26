import { NextResponse } from "next/server"
import { readFile } from "node:fs/promises"

export const dynamic = "force-dynamic"
export const revalidate = 0

const SCP_BASE_URL = (process.env.SCP_BASE_URL ?? "http://127.0.0.1:8002").replace(/\/+$/, "")
const TOKEN_FILE = process.env.SCP_AUTH_TOKEN_SECRET_FILE?.trim()

async function readAdminToken(): Promise<string> {
  const direct = process.env.SCP_AUTH_TOKEN_SECRET?.trim()
  if (direct) return direct
  if (!TOKEN_FILE) return ""
  try {
    return (await readFile(TOKEN_FILE, "utf8")).trim()
  } catch {
    return ""
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as Record<string, unknown>
    const audioBase64 = typeof body.audio_base64 === "string" ? body.audio_base64 : ""
    if (!audioBase64) return NextResponse.json({ error: "Chưa nhận được audio" }, { status: 400 })
    if (audioBase64.length > 8_000_000) return NextResponse.json({ error: "Audio quá lớn" }, { status: 413 })

    const token = await readAdminToken()
    if (!token) return NextResponse.json({ error: "SCP auth token chưa được cấu hình" }, { status: 503 })

    const response = await fetch(`${SCP_BASE_URL}/v104/voice/check`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ audio_base64: audioBase64 }),
      cache: "no-store",
      signal: AbortSignal.timeout(120_000),
    })
    const text = await response.text()
    let data: unknown = {}
    try { data = JSON.parse(text) } catch { data = { error: text.slice(0, 500) } }
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    const message = error instanceof Error ? error.message : "Không kết nối được SCP voice detector"
    return NextResponse.json({ error: message.slice(0, 300) }, { status: 502 })
  }
}
