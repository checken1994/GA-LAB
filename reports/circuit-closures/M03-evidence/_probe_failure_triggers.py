"""M03 micro-probe: can a REAL (no-mock) request input trigger the judge failure
branch? OpenAI multimodal content (list of parts) and non-string content are
legitimate client inputs — if judge.judge raises on them, the 503 path can be
tested with a real payload instead of an exception-injection mock.

ORIGINAL RUN: 2026-09-11, pre-fix tree — ALL cases answered gracefully
(content list/int -> 200 FAIL/KILL; content None / no user role / empty
messages -> 400), i.e. NO real input reaches the judge failure branch. This
justifies the ERR-1 fault injection at the route's get_judge seam in
test_flow_03. Re-created verbatim after workspace cleanup; re-running on the
pin gives the post-fix behavior record.
"""
import os

os.environ["SCP_API_PROFILE"] = "full"
os.environ.setdefault("SCP_JWT_SECRET", "m03-probe-jwt-secret-0123456789abcdef-40ch")

from fastapi.testclient import TestClient  # noqa: E402
from scp.api_server import app  # noqa: E402
from scp.security.jwt_guard import create_access_token  # noqa: E402

H = {"Authorization": f"Bearer {create_access_token({'sub': 'm03-probe2'})}"}

cases = {
    "content_list_parts": [{"role": "user", "content": [{"type": "text", "text": "Hi"}]}],
    "content_int": [{"role": "user", "content": 12345}],
    "content_none": [{"role": "user", "content": None}],
    "no_user_role": [{"role": "system", "content": "just system"}],
    "empty_messages": [],
}

with TestClient(app, raise_server_exceptions=False) as client:
    for name, messages in cases.items():
        r = client.post("/v1/chat/completions",
                        json={"model": "gpt-3.5-turbo", "messages": messages}, headers=H)
        try:
            body = r.json()
            brief = {k: body.get(k) for k in ("error", "scp_metadata") if k in body}
            brief.setdefault("keys", sorted(body)[:6])
        except Exception:
            brief = r.text[:120]
        print(f"=== {name} -> {r.status_code} :: {brief}")
print("MICRO PROBE DONE")
