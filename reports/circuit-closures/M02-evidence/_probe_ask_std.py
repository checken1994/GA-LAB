import json, os, urllib.request, sqlite3

from scp.security.url_safety import safe_urlopen

BASE = "http://127.0.0.1:8000"

def post(path, payload, headers=None, timeout=90):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(BASE + path, data=data, headers=h, method="POST")
    try:
        with safe_urlopen(req, timeout=timeout, allow_internal=True) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"_error_body": e.read().decode("utf-8", "replace")[:400]}

admin_key = os.environ.get("SCP_ADMIN_KEY", "")
assert admin_key, "SCP_ADMIN_KEY missing"
status, tok = post("/auth/token", {"admin_key": admin_key})
assert status == 200, f"auth/token failed: {status}"
auth = {"Authorization": "Bearer " + tok["access_token"]}

out = {"auth_token_minted": True}

# Context-backed /ask WITHOUT caller ai_answer: gateway must generate the
# candidate from the local fixture answer source, judge PASS, kernel VERIFIED.
p = {
    "question": "Theo ngữ cảnh được cung cấp, 2 cộng 2 bằng mấy?",
    "contexts": ["Đáp án fixture cục bộ: 2 cộng 2 bằng 4. Phép cộng cơ bản."],
    "session_id": "m2stdask01",
}
h = dict(auth)
h["X-SCP-Idempotency-Key"] = "m2-std-ctx-001"
code, body = post("/ask", p, h)
out["ask_context_backed"] = {
    "http_status": code,
    "verdict": body.get("verdict"),
    "confidence": body.get("confidence"),
    "governance_decision": body.get("governance_decision"),
    "final_answer_head": str(body.get("final_answer", ""))[:120],
    "withheld": str(body.get("final_answer", "")).startswith("[SCP:"),
    "detector_degraded": body.get("detector_degraded"),
    "run_status": body.get("run_status"),
    "run_id_present": bool(body.get("run_id")),
    "trace_id_present": bool(body.get("trace_id")),
    "ledger_status": body.get("ledger_status"),
}

# Kernel durable state for this task (own volume, read via sqlite)
con = sqlite3.connect("/var/lib/scp/data/task_kernel.sqlite3")
rows = con.execute(
    "SELECT task_id, state, goal, risk_tier, attempts FROM tasks ORDER BY created_at DESC LIMIT 4"
).fetchall()
out["kernel_recent_tasks"] = [
    {"task_id": r[0], "state": r[1], "goal": r[2], "risk_tier": r[3], "attempts": r[4]}
    for r in rows
]
idem = con.execute(
    "SELECT logical_key, task_id, status FROM idempotency ORDER BY created_at DESC LIMIT 2"
).fetchall()
out["kernel_idempotency_recent"] = [
    {"logical_key": r[0][:20] + "...", "task_id": r[1], "status": r[2]} for r in idem
]
con.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
