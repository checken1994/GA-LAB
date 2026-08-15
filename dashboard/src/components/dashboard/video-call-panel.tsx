"use client"

import { useCallback, useEffect, useRef, useState } from "react"

type CallInfo = { call_id: string; token: string; expires_in: number; signaling: string }
type SignalMessage = { type?: string; payload?: unknown }

function wsBaseUrl() {
  if (typeof window === "undefined") return "ws://127.0.0.1:8000"
  const host = window.location.hostname || "127.0.0.1"
  return `${window.location.protocol === "https:" ? "wss" : "ws"}://${host}:8000`
}

export function VideoCallPanel() {
  const [callInfo, setCallInfo] = useState<CallInfo | null>(null)
  const [joinCode, setJoinCode] = useState("")
  const [status, setStatus] = useState("Chưa bắt đầu cuộc gọi")
  const [connected, setConnected] = useState(false)
  const localVideo = useRef<HTMLVideoElement>(null)
  const remoteVideo = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const peerRef = useRef<RTCPeerConnection | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const callerRef = useRef(false)
  const pendingIceRef = useRef<RTCIceCandidateInit[]>([])

  const closeCall = useCallback(() => {
    try { socketRef.current?.send(JSON.stringify({ type: "hangup" })) } catch { /* socket may already be closed */ }
    socketRef.current?.close(); socketRef.current = null
    peerRef.current?.close(); peerRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop()); streamRef.current = null
    if (localVideo.current) localVideo.current.srcObject = null
    if (remoteVideo.current) remoteVideo.current.srcObject = null
    setCallInfo(null); setConnected(false); setStatus("Đã kết thúc cuộc gọi")
  }, [])

  const sendSignal = useCallback((message: Record<string, unknown>) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify(message))
  }, [])

  const setupPeer = useCallback((caller: boolean) => {
    const peer = new RTCPeerConnection()
    callerRef.current = caller
    peer.onicecandidate = (event) => { if (event.candidate) sendSignal({ type: "ice", payload: event.candidate.toJSON() }) }
    peer.ontrack = (event) => { if (remoteVideo.current) remoteVideo.current.srcObject = event.streams[0] }
    peer.onconnectionstatechange = () => { const state = peer.connectionState; setConnected(state === "connected"); setStatus(state === "connected" ? "Đã kết nối video hai chiều" : `Kết nối: ${state}`) }
    for (const track of streamRef.current?.getTracks() || []) peer.addTrack(track, streamRef.current as MediaStream)
    peerRef.current = peer
    return peer
  }, [sendSignal])

  const createOffer = useCallback(async () => {
    const peer = peerRef.current
    if (!peer) return
    const offer = await peer.createOffer(); await peer.setLocalDescription(offer)
    sendSignal({ type: "offer", payload: offer }); setStatus("Đã gửi lời mời video; đang chờ trả lời")
  }, [sendSignal])

  const connectSignal = useCallback(async (info: CallInfo, caller: boolean) => {
    const media = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
    streamRef.current = media
    if (localVideo.current) localVideo.current.srcObject = media
    const peer = setupPeer(caller)
    const socket = new WebSocket(`${wsBaseUrl()}${info.signaling}?token=${encodeURIComponent(info.token)}`)
    socketRef.current = socket
    socket.onopen = () => setStatus(caller ? "Phòng đã mở; chờ người thứ hai" : "Đã vào phòng; chờ lời mời video")
    socket.onmessage = async (event) => {
      const message = JSON.parse(event.data) as SignalMessage
      if (message.type === "peer_joined" && caller) { await createOffer(); return }
      if (message.type === "joined" && caller && message.payload === "peer_joined") { await createOffer(); return }
      if (message.type === "offer" && !caller) {
        await peer.setRemoteDescription(message.payload as RTCSessionDescriptionInit)
        for (const candidate of pendingIceRef.current) await peer.addIceCandidate(candidate).catch(() => undefined)
        pendingIceRef.current = []
        const answer = await peer.createAnswer(); await peer.setLocalDescription(answer)
        sendSignal({ type: "answer", payload: answer }); return
      }
      if (message.type === "answer" && caller) { await peer.setRemoteDescription(message.payload as RTCSessionDescriptionInit); return }
      if (message.type === "ice") {
        const candidate = message.payload as RTCIceCandidateInit
        if (peer.remoteDescription) await peer.addIceCandidate(candidate).catch(() => undefined); else pendingIceRef.current.push(candidate)
      }
      if (message.type === "peer_left") setStatus("Người kia đã rời cuộc gọi")
      if (message.type === "error") setStatus("Phòng không còn hợp lệ")
    }
    socket.onerror = () => setStatus("Không kết nối được signaling; kiểm tra backend SCP")
    socket.onclose = () => setConnected(false)
  }, [createOffer, sendSignal, setupPeer])

  const createCall = useCallback(async () => {
    try {
      setStatus("Đang tạo phòng và xin quyền camera/mic…")
      const response = await fetch("/api/scp/call/session", { method: "POST", cache: "no-store" })
      const data = await response.json() as CallInfo & { error?: string }
      if (!response.ok) throw new Error(data.error || "Không tạo được phòng")
      setCallInfo(data); await connectSignal(data, true)
    } catch (error) { setStatus(error instanceof Error ? error.message : "Không mở được cuộc gọi") }
  }, [connectSignal])

  const joinCall = useCallback(async () => {
    const [callId, token] = joinCode.trim().split(".", 2)
    if (!callId || !token) { setStatus("Mã vào phòng phải có dạng call_id.token"); return }
    try {
      setStatus("Đang vào phòng và xin quyền camera/mic…")
      const info: CallInfo = { call_id: callId, token, expires_in: 600, signaling: `/v3/call/sessions/${callId}/signal` }
      setCallInfo(info); await connectSignal(info, false)
    } catch (error) { setStatus(error instanceof Error ? error.message : "Không vào được cuộc gọi") }
  }, [connectSignal, joinCode])

  useEffect(() => () => closeCall(), [closeCall])
  const shareCode = callInfo ? `${callInfo.call_id}.${callInfo.token}` : ""

  return <section className="mt-5 rounded-3xl border border-emerald-300/20 bg-emerald-300/[0.045] p-5 sm:p-7" aria-label="Cuộc gọi video SCP">
    <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between"><div><div className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-200">00 · Cuộc gọi video</div><h2 className="mt-2 text-xl font-semibold text-white">Camera và mic có người dùng kiểm soát</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">SCP chỉ mở thiết bị sau khi bạn bấm nút. Video/audio không được lưu; server chỉ chuyển offer, answer và ICE trong phòng tối đa 10 phút.</p></div><div className="flex gap-2"><button type="button" onClick={() => void createCall()} disabled={Boolean(callInfo)} className="rounded-xl bg-emerald-300 px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:opacity-50">Tạo phòng</button><button type="button" onClick={closeCall} disabled={!callInfo} className="rounded-xl border border-white/10 px-4 py-2.5 text-sm text-slate-200 disabled:opacity-40">Tắt cuộc gọi</button></div></div>
    <div className="mt-4 flex flex-col gap-2 sm:flex-row"><input value={joinCode} onChange={(event) => setJoinCode(event.target.value)} placeholder="Dán mã call_id.token để vào phòng" className="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white outline-none" /><button type="button" onClick={() => void joinCall()} disabled={Boolean(callInfo)} className="rounded-xl border border-emerald-300/30 px-4 py-2.5 text-sm text-emerald-100 disabled:opacity-40">Vào phòng</button></div>
    {callInfo && <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-slate-300"><div>Trạng thái: {status}</div><div className="mt-1 break-all text-slate-500">Mã chia sẻ: {shareCode}</div></div>}
    <div className="mt-4 grid gap-3 md:grid-cols-2"><div className="relative overflow-hidden rounded-2xl border border-white/10 bg-black/30"><video ref={localVideo} autoPlay muted playsInline className="aspect-video w-full object-cover" /><div className="absolute bottom-2 left-2 rounded-full bg-black/60 px-2.5 py-1 text-xs text-white">Bạn</div></div><div className="relative overflow-hidden rounded-2xl border border-white/10 bg-black/30"><video ref={remoteVideo} autoPlay playsInline className="aspect-video w-full object-cover" /><div className="absolute inset-0 grid place-items-center text-4xl font-semibold text-emerald-200/70">SCP</div><div className="absolute bottom-2 left-2 rounded-full bg-black/60 px-2.5 py-1 text-xs text-white">Người kia</div></div></div>
    <div className="mt-3 text-xs text-slate-500">{connected ? "Đã nối hai chiều." : status}. Nếu camera/mic bị từ chối, Windows sẽ không cho SCP tự mở lại.</div>
  </section>
}
