import json, os, urllib.request, sqlite3

from scp.security.url_safety import safe_urlopen

BASE = "http://127.0.0.1:8000"

def post(path, payload, headers=None, timeout=60):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(BASE + path, data=data, headers=h, method="POST")
    try:
        with safe_urlopen(req, timeout=timeout, allow_internal=True) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        return e.code, {"_error_body": body}

# 1) Mint JWT inside the container; the secret never leaves this process.
admin_key = os.environ.get("SCP_ADMIN_KEY", "")
assert admin_key, "SCP_ADMIN_KEY missing in container env"
status, tok = post("/auth/token", {"admin_key": admin_key})
assert status == 200, f"auth/token failed: {status} {tok}"
jwt = tok["access_token"]
auth = {"Authorization": "Bearer " + jwt}

out = {"auth_token_minted": status == 200, "token_type": tok.get("token_type")}

# 2) Probe A: context-backed /ask (caller supplies ai_answer + contexts)
#    with client idempotency key header.
pA = {
    "question": "Theo ngữ cảnh được cung cấp, 2 cộng 2 bằng mấy?",
    "ai_answer": "2 cộng 2 bằng 4.",
    "contexts": ["Phép cộng số học cơ bản: 2 + 2 = 4."],
    "session_id": "m2d3a0001",
}
hA = dict(auth); hA["X-SCP-Idempotency-Key"] = "m2-d3-ctx-001"
codeA, bodyA = post("/ask", pA, hA)
out["probe_a_context_backed"] = {
    "http_status": codeA,
    "verdict": bodyA.get("verdict"),
    "confidence": bodyA.get("confidence"),
    "governance": (bodyA.get("reasoning") or "")[:200],
    "final_answer_withheld": str(bodyA.get("final_answer", "")).startswith("[SCP: Answer withheld"),
    "final_answer_head": str(bodyA.get("final_answer", ""))[:120],
    "detector_degraded": bodyA.get("detector_degraded"),
    "fact_check_degraded": bodyA.get("fact_check_degraded"),
    "session_id": bodyA.get("session_id"),
    "keys": sorted(bodyA.keys())[:40],
}

# 3) Probe A2: same idempotency key resend -> duplicate handling expected
codeA2, bodyA2 = post("/ask", pA, hA)
out["probe_a2_same_idem_key"] = {
    "http_status": codeA2,
    "verdict": bodyA2.get("verdict"),
    "duplicate_note": str(bodyA2.get("note") or bodyA2.get("detail") or "")[:200],
}

# 4) Probe B: missing-context /ask (no ai_answer, no contexts) -> fail-closed
pB = {"question": "Trái Đất có bao nhiêu vệ tinh tự nhiên?", "session_id": "m2d3b0001"}
hB = dict(auth); hB["X-SCP-Idempotency-Key"] = "m2-d3-noctx-001"
codeB, bodyB = post("/ask", pB, hB)
out["probe_b_missing_context"] = {
    "http_status": codeB,
    "verdict": bodyB.get("verdict"),
    "confidence": bodyB.get("confidence"),
    "final_answer_withheld": str(bodyB.get("final_answer", "")).startswith("[SCP: Answer withheld"),
    "final_answer_head": str(bodyB.get("final_answer", ""))[:120],
}

# 5) TaskKernel durable status for the probes
con = sqlite3.connect("/var/lib/scp/data/task_kernel.sqlite3")
rows = con.execute(
    "SELECT task_id, state, goal, risk_tier, attempts FROM tasks ORDER BY created_at DESC LIMIT 8"
).fetchall()
out["kernel_recent_tasks"] = [
    {"task_id": r[0], "state": r[1], "goal": r[2], "risk_tier": r[3], "attempts": r[4]} for r in rows
]
idem = con.execute(
    "SELECT logical_key, task_id, step_id, action_type, resource_identity, status FROM idempotency ORDER BY created_at DESC LIMIT 6"
).fetchall()
out["kernel_idempotency_recent"] = [
    {"logical_key": r[0], "task_id": r[1], "step_id": r[2], "action_type": r[3],
     "resource_identity": (r[4] or "")[:80], "status": r[5]} for r in idem
]
con.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
