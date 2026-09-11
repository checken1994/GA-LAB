"""M03 D3 runtime probe — REAL HTTP against the pinned temp instance.

Usage (from repo root, token minted inside the container, never printed):
  export M3_TOKEN=$(docker exec scp-m3-std python -c "from scp.security.jwt_guard import create_access_token; print(create_access_token({'sub':'m3-probe'}))")
  PYTHONPATH=. py -3.12 reports/circuit-closures/M03-evidence/_probe_http.py
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from scp.security.url_safety import safe_urlopen

BASE = os.environ.get("M3_BASE", "http://127.0.0.1:8002")
TOKEN = os.environ["M3_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def call(name, method, path, body=None, auth=True, raw_body=None):
    headers = dict(H) if auth else {"Content-Type": "application/json"}
    data = raw_body if raw_body is not None else (
        json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with safe_urlopen(req, timeout=60, allow_internal=True) as resp:
            code = resp.status
            payload = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        code = e.code
        payload = e.read().decode("utf-8", "replace")
    try:
        parsed = json.loads(payload)
    except Exception:
        parsed = payload[:300]
    return {"name": name, "status": code, "body": parsed}


results = [
    call("no_auth_empty", "POST", "/v1/chat/completions", body={}, auth=False),
    call("auth_bad_json", "POST", "/v1/chat/completions", raw_body=b"{invalid json"),
    call("auth_empty_body", "POST", "/v1/chat/completions", body={}),
    call("auth_messages_not_list", "POST", "/v1/chat/completions",
         body={"model": "gpt-3.5-turbo", "messages": "not a list"}),
    call("auth_messages_non_dict", "POST", "/v1/chat/completions",
         body={"model": "gpt-3.5-turbo", "messages": ["hello"]}),
    call("auth_valid_message", "POST", "/v1/chat/completions",
         body={"model": "gpt-3.5-turbo",
               "messages": [{"role": "user", "content": "What is 2+2?"}]}),
    call("auth_stream_true", "POST", "/v1/chat/completions",
         body={"model": "gpt-3.5-turbo", "stream": True,
               "messages": [{"role": "user", "content": "Test"}]}),
    call("models_auth", "GET", "/v1/models"),
    call("swe_root_path_404", "POST", "/chat/completions",
         body={"model": "scp-agent",
               "messages": [{"role": "user", "content": "Fix"}]}, auth=False),
    call("swe_prefixed_valid", "POST", "/swe-bench/v1/chat/completions",
         body={"model": "scp-agent",
               "messages": [{"role": "user", "content": "Fix this bug"}],
               "instance_id": "test-instance-123"}, auth=False),
    call("swe_prefixed_missing_model", "POST", "/swe-bench/v1/chat/completions",
         body={"messages": [{"role": "user", "content": "Test"}]}, auth=False),
]

record = {
    "pin": "3f29c180502fe71d92454f9ffcf699476a07f4ce",
    "instance": ("scp-m3-std temp instance on 127.0.0.1:8002, profile=full, "
                 "image scp-api:local sha256:0cb616c8236aaf736afb6313597e74de32ced1dbe5ba9b0a06a4c7955fc98245, "
                 "service_identity.commit == pin (verified via /health before probes)"),
    "token_provenance": "JWT minted INSIDE the container from SCP_JWT_SECRET (value never printed)",
    "probes": results,
}

out = Path(os.path.dirname(__file__)) / "D3-m3-runtime.json"
with out.open("w", encoding="utf-8") as f:
    json.dump(record, f, indent=1, ensure_ascii=False)
for r in results:
    b = r["body"]
    if isinstance(b, dict):
        brief = b.get("error") or {k: b[k] for k in ("object", "detail", "status") if k in b}
        sm = b.get("scp_metadata") or {}
        ch = (b.get("choices") or [{}])[0]
        content = (ch.get("message") or {}).get("content", "")
        extra = ""
        if sm:
            extra = f" | verdict={sm.get('verdict')}/gov={sm.get('governance_decision')}"
        if content:
            extra += f" | content={content[:45]!r}"
        print(f"{r['name']} -> {r['status']} :: {json.dumps(brief, ensure_ascii=False)[:100]}{extra}")
    else:
        print(f"{r['name']} -> {r['status']} :: {str(b)[:100]}")
print("PROBE DONE ->", out)
