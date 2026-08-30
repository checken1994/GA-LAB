import { readFile } from "node:fs/promises"
import { NextResponse } from "next/server"

export const dynamic = "force-dynamic"
export const revalidate = 0

const SCP_BASE_URL = (process.env.SCP_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "")
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
    const question = typeof body.question === "string" ? body.question.trim() : ""
    if (!question || question.length > 8000) {
      return NextResponse.json({ error: "Câu hỏi trống hoặc quá dài" }, { status: 400 })
    }
    const imageData = typeof body.image_data === "string" ? body.image_data : null
    if (imageData && imageData.length > 900_000) {
      return NextResponse.json({ error: "Ảnh quá lớn" }, { status: 413 })
    }
    const history = Array.isArray(body.conversation_history)
      ? body.conversation_history.slice(-8).filter((item) => item && typeof item === "object")
      : []
    const payload = {
      question,
      domain: typeof body.domain === "string" ? body.domain.slice(0, 80) : "general",
      ai_answer: "",
      source: "desktop_chat",
      session_id: typeof body.session_id === "string" ? body.session_id.slice(0, 120) : undefined,
      conversation_history: history,
      image_data: imageData,
    }
    const authHeader = request.headers.get("Authorization")
    if (!authHeader) return NextResponse.json({ error: "Missing Authorization header" }, { status: 401 })
    
    const response = await fetch(`${SCP_BASE_URL}/ask`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json", Authorization: authHeader },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal: AbortSignal.timeout(120_000),
    })
    const text = await response.text()
    let data: unknown = {}
    try { data = JSON.parse(text) } catch { data = { error: text.slice(0, 500) } }
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    const message = error instanceof Error ? error.message : "Không kết nối được SCP"
    return NextResponse.json({ error: message.slice(0, 300) }, { status: 502 })
  }
}
