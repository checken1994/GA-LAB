from __future__ import annotations

import sys

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE = "http://127.0.0.1:8000"


def req(method: str, path: str, payload: dict | None = None) -> dict:
    response = requests.request(method, BASE + path, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def check(name: str, ok: bool, detail: object) -> None:
    print(f"{name}={'PASS' if ok else 'FAIL'}|{detail}")
    if not ok:
        raise AssertionError(f"{name}: {detail}")


def main() -> None:
    status = req("GET", "/v3/hands/status")
    check("hands_v35_contract", status.get("version") == "3.5" and status.get("actionCount") == 25, status)
    check("planner_v37_metadata", status.get("plannerVersion") == "3.7" and status.get("planner", {}).get("version") == "3.7", status)

    parsed = req("POST", "/v3/hands/planner/parse", {"goal": "Tìm nguồn công khai về SCP", "preferLocal": False})
    check("goal_parser_proposal", parsed.get("success") is True and parsed.get("proposalOnly") is True and parsed.get("approved") is False, parsed)
    check("goal_parser_allowlisted", parsed.get("plan", {}).get("steps", [{}])[0].get("action") == "web.search_public", parsed)

    created = req("POST", "/v3/hands/planner", {"goal": "DAG safe probe", "steps": [{"stepId": "a", "action": "pc.status"}, {"stepId": "b", "action": "web.tab_snapshot"}, {"stepId": "c", "action": "pc.status", "dependsOn": ["a", "b"]}]})
    check("dag_plan_create", created.get("success") is True and created.get("version") == "3.7", created)
    plan_id = created["plan"]["planId"]
    dag = req("POST", f"/v3/hands/planner/{plan_id}/run-dag", {"maxParallel": 2, "capabilityLevel": 0, "approved": False})
    states = [step.get("state") for step in dag.get("plan", {}).get("steps", [])]
    check("dag_safe_run", dag.get("success") is True and dag.get("plan", {}).get("scheduler") == "dag" and states == ["VERIFIED", "VERIFIED", "VERIFIED"], dag)

    risky = req("POST", "/v3/hands/planner", {"goal": "DAG approval probe", "steps": [{"stepId": "open", "action": "web.open_public_tab", "params": {"url": "https://example.com"}, "capabilityLevel": 2}]})
    risky_id = risky["plan"]["planId"]
    paused = req("POST", f"/v3/hands/planner/{risky_id}/run-dag", {"maxParallel": 2, "capabilityLevel": 2, "approved": False})
    check("dag_approval_pause", paused.get("success") is False and paused.get("waitingApproval") is True and paused.get("plan", {}).get("state") == "WAITING_APPROVAL", paused)
    print("HANDS_V37_API_REGRESSION_PASS=True")


if __name__ == "__main__":
    main()
