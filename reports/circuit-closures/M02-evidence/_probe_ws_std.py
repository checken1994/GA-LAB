# M2 D3 WS probe on temporary standard-profile instance (:8001 -> container :8000).
# Token is read from auth config INSIDE the container and never printed.
import asyncio, json


async def main():
    from scp.security.auth_config import load_auth_config

    cfg = load_auth_config()
    token = cfg.token or cfg.password
    assert cfg.configured and token, "auth config not configured"
    print("auth_cfg_configured:", cfg.configured, "token_source:", "cfg.token" if cfg.token else "cfg.password")

    import websockets

    uri = "ws://127.0.0.1:8000/chat?token=" + token + "&session_id=m2ws0001"
    out = {}
    async with websockets.connect(uri, open_timeout=15) as ws:
        welcome = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        out["handshake"] = "101_switching_protocols"
        out["welcome_type"] = welcome.get("type")
        out["welcome_session"] = bool(welcome.get("session_id"))
        out["memory_mode"] = welcome.get("memory_mode")

        await ws.send(json.dumps({"message": "2 cộng 2 bằng mấy?"}))
        t0 = asyncio.get_event_loop().time()
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=120)
            frame = json.loads(raw)
            ftype = frame.get("type", "")
            if ftype in ("system",):
                continue
            out["reply_type"] = ftype
            out["verdict"] = frame.get("verdict")
            out["governance"] = frame.get("governance")
            out["answer_head"] = str(frame.get("answer", ""))[:120]
            out["has_run_id"] = bool(frame.get("run_id"))
            out["has_trace_id"] = bool(frame.get("trace_id"))
            out["latency_s"] = round(asyncio.get_event_loop().time() - t0, 2)
            break
    print(json.dumps(out, ensure_ascii=False, indent=1))


asyncio.run(main())
