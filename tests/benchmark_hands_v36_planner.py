from __future__ import annotations

import statistics
import time

import requests

BASE = "http://127.0.0.1:8002"


def request(method: str, path: str, payload: dict | None = None) -> dict:
    response = requests.request(method, BASE + path, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def main() -> None:
    safe_latencies: list[float] = []
    safe_success = 0
    for index in range(3):
        started = time.perf_counter()
        created = request("POST", "/v3/hands/planner", {"goal": f"Benchmark safe plan {index}", "steps": [{"action": "pc.status"}, {"action": "web.tab_snapshot"}]})
        plan_id = created["plan"]["planId"]
        result = request("POST", f"/v3/hands/planner/{plan_id}/run", {"capabilityLevel": 0, "approved": False, "dryRun": False})
        safe_latencies.append(round((time.perf_counter() - started) * 1000, 2))
        if result.get("success") is True and result.get("plan", {}).get("state") == "COMPLETED":
            safe_success += 1
    started = time.perf_counter()
    risky_created = request("POST", "/v3/hands/planner", {"goal": "Benchmark approval pause", "steps": [{"action": "web.open_public_tab", "params": {"url": "https://example.com"}, "capabilityLevel": 2}]})
    risky_result = request("POST", f"/v3/hands/planner/{risky_created['plan']['planId']}/run", {"capabilityLevel": 2, "approved": False})
    approval_ms = round((time.perf_counter() - started) * 1000, 2)
    print("safePlanCases=3")
    print("safePlanSuccess=" + str(safe_success))
    print("safePlanLatencyMinMs=" + str(min(safe_latencies)))
    print("safePlanLatencyMedianMs=" + str(round(statistics.median(safe_latencies), 2)))
    print("safePlanLatencyMaxMs=" + str(max(safe_latencies)))
    print("approvalPauseMs=" + str(approval_ms))
    print("approvalPauseSuccess=" + str(risky_result.get("waitingApproval") is True))
    print("BENCHMARK_HANDS_V36_PLANNER_DONE=True")


if __name__ == "__main__":
    main()
