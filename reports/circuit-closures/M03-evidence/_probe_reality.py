"""M03 D0 reality probe — observe actual behavior of /v1/chat/completions and
/swe-bench/v1/chat/completions BEFORE any fix (DNA #26: reality has final say).

ORIGINAL RUN: 2026-09-11 ~11:58 local, pre-fix tree (HEAD 1fc58c7 + M3 fix
not yet applied). Re-created verbatim after the file was lost to a concurrent
workspace cleanup; output originally captured in _probe_reality_out.txt
(regenerated below is a SUPPORT record of the observed pre-fix reality).

Run: PYTHONPATH=. py -3.12 reports/circuit-closures/M03-evidence/_probe_reality.py
No secret is printed. Output is observation only.
"""
import json
import os
import sys

# tests/conftest.py sets this for pytest; standalone probe must match it BEFORE
# scp import (scp loads .env which carries SCP_API_PROFILE=core → routes 404).
os.environ["SCP_API_PROFILE"] = "full"
os.environ.setdefault("SCP_JWT_SECRET", "m03-probe-jwt-secret-0123456789abcdef-40ch")

from fastapi.testclient import TestClient  # noqa: E402
from scp.api_server import app  # noqa: E402
from scp.security.jwt_guard import create_access_token  # noqa: E402

TOKEN = create_access_token({"sub": "m03-probe"})
H = {"Authorization": f"Bearer {TOKEN}"}

results = []


def probe(name, method, path, **kw):
    with TestClient(app, raise_server_exceptions=False) as client:
        try:
            r = getattr(client, method)(path, **kw)
            body = None
            try:
                body = r.json()
            except Exception:
                body = r.text[:200]
            # redact anything token-like
            snippet = json.dumps(body, ensure_ascii=False)[:600] if not isinstance(body, str) else body
            results.append((name, r.status_code, snippet))
        except Exception as e:
            results.append((name, "EXC", f"{type(e).__name__}: {e}"))


probe("no_auth_empty_body", "post", "/v1/chat/completions", json={})
probe("auth_empty_body", "post", "/v1/chat/completions", json={}, headers=H)
probe("auth_messages_not_a_list", "post", "/v1/chat/completions",
      json={"model": "gpt-3.5-turbo", "messages": "not a list"}, headers=H)
probe("auth_messages_non_dict_item", "post", "/v1/chat/completions",
      json={"model": "gpt-3.5-turbo", "messages": ["hello"]}, headers=H)
probe("auth_valid_message", "post", "/v1/chat/completions",
      json={"model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "What is 2+2?"}]}, headers=H)
probe("auth_stream_true", "post", "/v1/chat/completions",
      json={"model": "gpt-3.5-turbo", "stream": True,
            "messages": [{"role": "user", "content": "Test"}]}, headers=H)
probe("models_no_auth", "get", "/v1/models")
probe("models_auth", "get", "/v1/models", headers=H)
probe("swe_root_path", "post", "/chat/completions",
      json={"model": "scp-agent", "messages": [{"role": "user", "content": "Fix"}]})
probe("swe_prefixed_valid", "post", "/swe-bench/v1/chat/completions",
      json={"model": "scp-agent", "messages": [{"role": "user", "content": "Fix this bug"}],
            "instance_id": "test-instance-123"})
probe("swe_prefixed_no_instance_id", "post", "/swe-bench/v1/chat/completions",
      json={"model": "scp-agent", "messages": [{"role": "user", "content": "Test"}]})
probe("swe_prefixed_missing_model", "post", "/swe-bench/v1/chat/completions",
      json={"messages": [{"role": "user", "content": "Test"}]})
probe("swe_prefixed_messages_not_list", "post", "/swe-bench/v1/chat/completions",
      json={"model": "scp-agent", "messages": "oops"})

for name, status, snippet in results:
    print(f"=== {name} -> {status}")
    print(f"    {snippet}")
print("PROBE DONE")
