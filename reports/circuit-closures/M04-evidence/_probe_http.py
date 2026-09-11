"""M04 D3 runtime probe — token-only fail-closed + positive mint-token paths.

Runs against a TEMPORARY full-profile instance (scp-m4-probe, 127.0.0.1:8003)
built from the SAME pinned image scp-api:local (sha_pin e13fad4...). The PC
controller token and capability tokens are minted/provided out-of-band and are
NEVER written to this evidence file: only HTTP status codes, error-class
markers and truncated token ids are recorded.

Usage (values come from the environment):
  PC_TOKEN=... PCAP_JSON=... HCAP_JSON=... python _probe_http.py

Output: D3-m4-runtime.json (redacted).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from scp.security.url_safety import safe_urlopen

BASE = "http://127.0.0.1:8003"
PIN = "e13fad455afbfaa7b5e53ec677c1e9772eecc19d"


def request(method: str, path: str, token: str | None = None, cap_token: str | None = None, body: dict | None = None, cap_token_in_body: bool = False):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("X-SCP-PC-Token", token)
    if cap_token and not cap_token_in_body:
        req.add_header("X-SCP-Capability-Token", cap_token)
    data = None
    if body is not None:
        payload = dict(body)
        if cap_token and cap_token_in_body:
            # hands_routes reads payload.capabilityToken from the JSON body
            payload["capabilityToken"] = cap_token
        data = json.dumps(payload).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with safe_urlopen(req, data=data, timeout=30, allow_internal=True) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, {}


def redact_token(tok: dict | None) -> dict | None:
    if not isinstance(tok, dict):
        return None
    return {"subject": tok.get("subject"), "epoch": tok.get("epoch"),
            "token_id_prefix": str(tok.get("token_id", ""))[:8], "signature": "<redacted>"}


def main() -> None:
    pc_token = os.environ["PC_TOKEN"]
    pcap = json.loads(os.environ["PCAP_JSON"])
    hcap = json.loads(os.environ["HCAP_JSON"])
    results: list[dict] = []

    def record(name: str, method: str, path: str, status: int, body: dict, expect: int, notes: str = ""):
        results.append({
            "probe": name, "method": method, "path": path,
            "status": status, "expected_status": expect,
            "pass": status == expect,
            "detail_marker": (str(body.get("detail", ""))[:80] if isinstance(body, dict) else ""),
            "notes": notes,
        })

    # ---- Negative-first: NO PC token (token-only fail-closed boundary) ----
    s, b = request("GET", "/v3/pc/status")
    record("N1_pc_status_no_token", "GET", "/v3/pc/status", s, b, 403)
    s, b = request("POST", "/v3/pc/execute", body={"command": "whoami", "capabilityLevel": 0})
    record("N2_pc_execute_no_token", "POST", "/v3/pc/execute", s, b, 403)
    s, b = request("POST", "/v3/hands/plan", body={"action": "pc.write_file", "capabilityLevel": 3})
    record("N3_hands_plan_no_token", "POST", "/v3/hands/plan", s, b, 403)
    s, b = request("POST", "/v3/hands/execute",
                   body={"action": "pc.write_file", "params": {"path": "x.txt", "content": "y"},
                         "capabilityLevel": 3, "approved": True})
    record("N4_hands_execute_no_token", "POST", "/v3/hands/execute", s, b, 403)
    s, b = request("GET", "/v3/web/status")
    record("N5_web_status_no_token", "GET", "/v3/web/status", s, b, 403)
    # ---- Wrong token ----
    s, b = request("GET", "/v3/pc/status", token="wrong-token-value")
    record("N6_pc_status_wrong_token", "GET", "/v3/pc/status", s, b, 403)

    # ---- PC token valid, NO capability token (PEP layer) ----
    s, b = request("GET", "/v3/pc/status", token=pc_token)
    record("P1_pc_status_with_token", "GET", "/v3/pc/status", s, b, 200,
           "keys=" + ",".join(sorted(k for k in b if k in ("killSwitch", "workingDir"))))
    s, b = request("GET", "/v3/web/status", token=pc_token)
    record("P2_web_status_with_token", "GET", "/v3/web/status", s, b, 200,
           "keys=" + ",".join(sorted(k for k in b if k in ("navigator", "orchestrator"))))
    s, b = request("POST", "/v3/hands/plan", token=pc_token,
                   body={"action": "pc.write_file", "capabilityLevel": 3})
    record("P3_hands_plan_with_token", "POST", "/v3/hands/plan", s, b, 200)
    s, b = request("POST", "/v3/pc/execute", token=pc_token,
                   body={"command": "whoami", "capabilityLevel": 0})
    record("P4_pc_execute_no_capability_token", "POST", "/v3/pc/execute", s, b, 403,
           "PEP CapabilityRequiredError expected in detail")
    s, b = request("POST", "/v3/hands/execute", token=pc_token,
                   body={"action": "pc.write_file", "params": {"path": "x.txt", "content": "y"},
                         "capabilityLevel": 3, "approved": True})
    record("P5_hands_execute_no_capability_token", "POST", "/v3/hands/execute", s, b, 403,
           "bridge FA-05 ordering mapped to 403 (was unhandled 500 before e13fad4)")

    # ---- Positive with capability tokens minted INSIDE the container ----
    cap_header = json.dumps(pcap)
    s, b = request("POST", "/v3/pc/execute", token=pc_token, cap_token=cap_header,
                   body={"command": "whoami", "capabilityLevel": 0})
    results.append({
        "probe": "P6_pc_execute_with_capability_token", "method": "POST", "path": "/v3/pc/execute",
        "status": s, "expected_status": 200, "pass": s == 200,
        "token_sent": redact_token(pcap),
        "pep_passed_token_id_echo": bool(isinstance(b, dict) and b.get("tokenId", "").startswith(str(pcap.get("token_id", ""))[:8])),
        "command_runtime": ("executed" if isinstance(b, dict) and b.get("success") is True
                            else f"platform-limited:{str(b.get('error', ''))[:60]}"),
        "notes": "Linux container has no powershell.exe; PEP pass-through is proven by the "
                 "tokenId echo + policy decision, real command execution is proven at D1 on Windows.",
    })
    hands_header = json.dumps(hcap)
    s, b = request("POST", "/v3/hands/execute", token=pc_token, cap_token=hands_header,
                   cap_token_in_body=True,
                   body={"action": "pc.write_file",
                         "params": {"path": "/var/lib/scp/m4_probe_write.txt", "content": "m4 runtime golden path"},
                         "capabilityLevel": 3, "approved": True})
    results.append({
        "probe": "P7_hands_execute_golden_path", "method": "POST", "path": "/v3/hands/execute",
        "status": s, "expected_status": 200, "pass": s == 200,
        "token_sent": redact_token(hcap),
        "success": bool(isinstance(b, dict) and b.get("success")),
        "kernel_state": (b or {}).get("kernel", {}).get("state"),
        "token_id_echo": bool(isinstance(b, dict) and b.get("tokenId", "").startswith(str(hcap.get("token_id", ""))[:8])),
        "notes": "full runtime golden path: route -> kernel bridge -> executor -> controller PEP -> filesystem",
    })

    # ---- Health identity of the probe instance ----
    s, b = request("GET", "/health")
    results.append({
        "probe": "P8_probe_instance_health", "method": "GET", "path": "/health",
        "status": s, "expected_status": 200, "pass": s == 200,
        "commit": (b or {}).get("service_identity", {}).get("commit"),
        "commit_matches_pin": (b or {}).get("service_identity", {}).get("commit") == PIN,
    })

    with (Path(os.path.dirname(__file__)) / "D3-m4-runtime.json").open("w", encoding="utf-8") as fh:
        json.dump({
            "pin": PIN,
            "instance": "temporary full-profile container scp-m4-probe, same pinned image, torn down after probe",
            "redaction": "capability token values/signatures and the PC token are never recorded; token_id truncated to 8 chars",
            "results": results,
            "all_pass": all(item.get("pass") for item in results),
        }, fh, indent=1)
    print("ALL_PASS=", all(item.get("pass") for item in results))
    for item in results:
        print(item["probe"], item["status"], "PASS" if item.get("pass") else "FAIL")


if __name__ == "__main__":
    main()
