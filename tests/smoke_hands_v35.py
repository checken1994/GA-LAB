from __future__ import annotations

import json
import sys
import time
from collections import Counter

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE = "http://127.0.0.1:8002"


def call(method: str, path: str, payload: dict | None = None) -> requests.Response:
    return requests.request(method, BASE + path, json=payload, timeout=120)


def check(name: str, ok: bool, detail: object) -> None:
    print(f"{name}={'PASS' if ok else 'FAIL'}|{detail}")
    if not ok:
        raise AssertionError(f"{name}: {detail}")


def main() -> None:
    actions_response = call("GET", "/v3/hands/actions")
    actions_payload = actions_response.json()
    actions = actions_payload.get("actions", [])
    names = [item.get("name") for item in actions]
    check("registry_http", actions_response.status_code == 200, actions_response.status_code)
    check("registry_version", actions_payload.get("version") == "3.5", actions_payload.get("version"))
    check("registry_count", len(names) == 25 and len(set(names)) == 25, len(names))

    params_by_action = {
        "pc.read_file": {"path": "data/hands/audit.jsonl", "maxBytes": 2000},
        "pc.list_dir": {"path": "data/hands"},
        "pc.file_hash": {"path": "data/hands/audit.jsonl"},
        "pc.search_workspace": {"path": "data/hands", "query": "ACTION"},
        "pc.directory_tree": {"path": "data/hands", "maxDepth": 2},
        "pc.validate_jsonl": {"path": "data/hands/audit.jsonl"},
        "web.search_public": {"query": "SCP self correcting process", "maxResults": 2},
        "web.browse_public": {"url": "https://example.com", "maxChars": 1000},
        "web.extract_links": {"url": "https://example.com", "maxChars": 2000},
        "web.tab_snapshot": {},
        "pc.process_info": {"pid": 0},
        "pc.process_stop_owned": {"pid": 0},
        "web.dom_snapshot": {"hostname": "example.com", "maxChars": 1000},
        "web.open_public_tab": {"url": "https://example.com"},
        "web.follow_public_link": {"url": "https://example.com"},
        "web.wait_for_text": {"text": "Example Domain", "hostname": "example.com", "timeoutSeconds": 1},
    }
    high_capability = {"pc.write_file": 3, "pc.process_start_managed": 3, "pc.process_stop_owned": 4, "web.dom_snapshot": 1, "web.open_public_tab": 2, "web.follow_public_link": 2, "web.wait_for_text": 1, "web.read_logged_in": 1}
    dry_results = {}
    for name in names:
        payload = {"action": name, "params": params_by_action.get(name, {}), "capabilityLevel": high_capability.get(name, 0), "approved": name in high_capability, "dryRun": True}
        response = call("POST", "/v3/hands/execute", payload)
        data = response.json()
        dry_results[name] = data
        check("dry_run_" + name, response.status_code == 200 and data.get("success") is True and data.get("dryRun") is True, data.get("error", "ok"))

    actual_safe = [
        ("pc.status", {}, 0, False),
        ("pc.process_list_owned", {}, 0, False),
        ("pc.validate_jsonl", {"path": "data/hands/audit.jsonl"}, 0, False),
        ("web.tab_snapshot", {}, 0, False),
        ("web.search_public", {"query": "SCP self correcting process", "maxResults": 2}, 0, False),
    ]
    actual_outcomes = []
    for name, params, capability, approved in actual_safe:
        started = time.perf_counter()
        response = call("POST", "/v3/hands/execute", {"action": name, "params": params, "capabilityLevel": capability, "approved": approved, "dryRun": False})
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        data = response.json()
        actual_outcomes.append({"action": name, "status": response.status_code, "success": data.get("success"), "verified": data.get("verification", {}).get("passed"), "latencyMs": elapsed, "error": data.get("error", "")})
        check("actual_safe_" + name, response.status_code == 200 and data.get("success") is True, data.get("error", data))

    print("actualOutcomes=" + json.dumps(actual_outcomes, ensure_ascii=True, separators=(",", ":")))
    print("HANDS_V35_REGISTRY_SMOKE_PASS=True")


if __name__ == "__main__":
    main()
