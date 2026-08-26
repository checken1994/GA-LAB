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
    check("hands_v35_status_preserved", status_response.status_code == 200 and status.get("version") == "3.5" and status.get("actionCount") == 25, status)
    check("planner_embedded_status", status.get("plannerVersion") == "3.7" and status.get("planner", {}).get("planner") == "online", status)

    actions = request("GET", "/v3/hands/actions").json()
    check("actions_backward_compatible", actions.get("version") == "3.5" and len(actions.get("actions", [])) == 25 and actions.get("plannerVersion") == "3.7", actions)

    created = request("POST", "/v3/hands/planner", {"goal": "Probe safe Hands evidence", "steps": [{"stepId": "status", "action": "pc.status"}, {"stepId": "tabs", "action": "web.tab_snapshot", "dependsOn": ["status"]}]}).json()
    check("planner_create", created.get("success") is True and created.get("version") == "3.7", created)
    plan_id = created["plan"]["planId"]

    fetched = request("GET", f"/v3/hands/planner/{plan_id}").json()
    check("planner_get", fetched.get("success") is True and fetched.get("plan", {}).get("state") == "PLANNED", fetched)

    run = request("POST", f"/v3/hands/planner/{plan_id}/run", {"capabilityLevel": 0, "approved": False, "dryRun": False}).json()
    states = [step.get("state") for step in run.get("plan", {}).get("steps", [])]
    check("planner_run_safe_plan", run.get("success") is True and run.get("plan", {}).get("state") == "COMPLETED" and states == ["VERIFIED", "VERIFIED"], run)

    risky = request("POST", "/v3/hands/planner", {"goal": "Approval probe", "steps": [{"action": "web.open_public_tab", "params": {"url": "https://example.com"}, "capabilityLevel": 2}]}).json()
    risky_id = risky["plan"]["planId"]
    paused = request("POST", f"/v3/hands/planner/{risky_id}/run", {"capabilityLevel": 2, "approved": False}).json()
    check("planner_approval_pause", paused.get("success") is False and paused.get("waitingApproval") is True and paused.get("plan", {}).get("state") == "WAITING_APPROVAL", paused)

    planner_status = request("GET", "/v3/hands/planner/status").json()
    check("planner_status_route", planner_status.get("version") == "3.7" and planner_status.get("planCount", 0) >= 2, planner_status)
    print("HANDS_V36_API_REGRESSION_PASS=True")


if __name__ == "__main__":
    main()
