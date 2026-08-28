from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8002"


def post(path: str, payload: dict) -> dict:
    response = requests.post(BASE + path, json=payload, timeout=90)
    response.raise_for_status()
    return response.json()


def check(label: str, condition: bool, detail: object) -> None:
    print(f"{label}={'PASS' if condition else 'FAIL'}|{detail}")
    if not condition:
        raise AssertionError(f"{label}: {detail}")


def main() -> None:
    actions = requests.get(BASE + "/v3/hands/actions", timeout=30).json()
    check("registry_10_actions", len(actions.get("actions", [])) == 10, len(actions.get("actions", [])))

    plan_safe = post("/v3/hands/plan", {"action": "pc.status", "params": {}, "capabilityLevel": 0, "approved": False, "dryRun": True})
    check("safe_plan_allowed", plan_safe.get("allowed") is True, plan_safe)

    plan_write_blocked = post("/v3/hands/plan", {"action": "pc.write_file", "params": {}, "capabilityLevel": 3, "approved": False, "dryRun": False})
    check("write_without_approval_blocked", plan_write_blocked.get("allowed") is False, plan_write_blocked)

    unknown = post("/v3/hands/execute", {"action": "pc.delete_everything", "params": {}, "capabilityLevel": 5, "approved": True})
    check("unknown_action_blocked", unknown.get("success") is False, unknown)

    dry = post("/v3/hands/execute", {"action": "pc.status", "params": {}, "capabilityLevel": 0, "approved": False, "dryRun": True})
    check("dry_run_verified", dry.get("success") is True and dry.get("verification", {}).get("passed") is True, dry)

    status = post("/v3/hands/execute", {"action": "pc.status", "params": {}, "capabilityLevel": 0, "approved": False})
    check("pc_status_verified", status.get("success") is True and status.get("verification", {}).get("passed") is True, status)

    listing = post("/v3/hands/execute", {"action": "pc.list_dir", "params": {}, "capabilityLevel": 0, "approved": False})
    check("pc_list_verified", listing.get("success") is True and listing.get("verification", {}).get("passed") is True, listing)

    process = post("/v3/hands/execute", {"action": "pc.process_snapshot", "params": {}, "capabilityLevel": 0, "approved": False})
    check("process_snapshot_verified", process.get("success") is True and process.get("verification", {}).get("passed") is True, process)

    service = post("/v3/hands/execute", {"action": "pc.service_snapshot", "params": {}, "capabilityLevel": 0, "approved": False})
    check("service_snapshot_verified", service.get("success") is True and service.get("verification", {}).get("passed") is True, service)

    diff = post("/v3/hands/execute", {"action": "pc.workspace_diff_check", "params": {}, "capabilityLevel": 0, "approved": False})
    check("workspace_diff_verified", diff.get("success") is True and diff.get("verification", {}).get("passed") is True, diff)

    search = post("/v3/hands/execute", {"action": "web.search_public", "params": {"query": "SCP self correcting process", "maxResults": 3}, "capabilityLevel": 0, "approved": False})
    check("web_search_verified", search.get("success") is True and search.get("verification", {}).get("passed") is True, search)

    public = post("/v3/hands/execute", {"action": "web.browse_public", "params": {"url": "https://example.com", "maxChars": 2000}, "capabilityLevel": 0, "approved": False})
    check("public_browse_verified", public.get("success") is True and public.get("verification", {}).get("passed") is True, public)

    logged_in_blocked = post("/v3/hands/execute", {"action": "web.read_logged_in", "params": {"url": "https://chatgpt.com/"}, "capabilityLevel": 1, "approved": False})
    check("logged_in_without_approval_blocked", logged_in_blocked.get("success") is False, logged_in_blocked)

    filename = f"data/hands/smoke-{int(time.time())}.txt"
    write = post("/v3/hands/execute", {"action": "pc.write_file", "params": {"path": filename, "content": "SCP_HANDS_V32_SMOKE_TEST\n"}, "capabilityLevel": 3, "approved": True})
    checkpoint = write.get("checkpointId")
    check("write_checkpoint_created", write.get("success") is True and bool(checkpoint) and write.get("verification", {}).get("passed") is True, write)

    rollback = post("/v3/hands/rollback", {"checkpointId": checkpoint, "capabilityLevel": 3, "approved": True})
    check("rollback_verified", rollback.get("success") is True, rollback)

    print("HANDS_V32_PASS=True")


if __name__ == "__main__":
    main()
