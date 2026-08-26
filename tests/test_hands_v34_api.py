from __future__ import annotations

import sys
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8002"
ROOT = Path(__file__).resolve().parents[1]


def request(method: str, path: str, payload: dict | None = None) -> requests.Response:
    return requests.request(method, BASE + path, json=payload, timeout=120)


def check(name: str, condition: bool, detail: object) -> None:
    print(f"{name}={'PASS' if condition else 'FAIL'}|{detail}")
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def main() -> None:
    status_response = request("GET", "/v3/hands/status")
    status = status_response.json()
    check("status_route_compatible", status_response.status_code == 200 and status.get("hands") == "online", status)
    check("v34_metadata", status.get("version") == "3.4" and status.get("actionCount", 0) >= 20, status)

    actions_response = request("GET", "/v3/hands/actions")
    actions = actions_response.json()
    names = {item.get("name") for item in actions.get("actions", [])}
    old_actions = {"pc.status", "pc.read_file", "pc.list_dir", "pc.process_snapshot", "pc.service_snapshot", "pc.workspace_diff_check", "pc.file_hash", "pc.search_workspace", "pc.directory_tree", "pc.git_status", "pc.validate_jsonl", "pc.write_file", "web.search_public", "web.browse_public", "web.extract_links", "web.read_logged_in"}
    check("actions_route_compatible", actions_response.status_code == 200 and old_actions.issubset(names), sorted(names))

    plan = request("POST", "/v3/hands/plan", {"action": "pc.status", "params": {}, "capabilityLevel": 0, "approved": False, "dryRun": True}).json()
    check("plan_payload_compatible", plan.get("allowed") is True, plan)

    execute = request("POST", "/v3/hands/execute", {"action": "pc.status", "params": {}, "capabilityLevel": 0, "approved": False, "dryRun": False}).json()
    check("execute_payload_compatible", execute.get("success") is True and execute.get("verification", {}).get("passed") is True, execute)

    unknown = request("POST", "/v3/hands/execute", {"action": "pc.unknown_compatibility_probe", "params": {}, "capabilityLevel": 5, "approved": True, "dryRun": False}).json()
    check("unknown_action_still_blocked", unknown.get("success") is False, unknown)

    bad_rollback = request("POST", "/v3/hands/rollback", {"checkpointId": "nonexistent-checkpoint", "capabilityLevel": 3, "approved": True}).json()
    check("rollback_route_compatible", bad_rollback.get("success") is False and "not found" in bad_rollback.get("error", "").lower(), bad_rollback)

    print("HANDS_V33_BACKWARD_COMPAT_PASS=True")


if __name__ == "__main__":
    main()
