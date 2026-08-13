from __future__ import annotations

import json
import statistics
import time
from collections import Counter

import requests

BASE = "http://127.0.0.1:8000"

CASES = [
    ("pc.status", {}, 0, False),
    ("pc.process_list_owned", {}, 0, False),
    ("pc.validate_jsonl", {"path": "data/hands/audit.jsonl"}, 0, False),
    ("web.tab_snapshot", {}, 0, False),
    ("web.search_public", {"query": "SCP self correcting process", "maxResults": 3}, 0, False),
    ("web.browse_public", {"url": "https://example.com", "maxChars": 1000}, 0, False),
    ("web.dom_snapshot", {"hostname": "example.com", "maxChars": 1000}, 1, False),
    ("web.open_public_tab", {"url": "https://example.com"}, 2, False),
    ("pc.process_start_managed", {"commandId": "hands_probe"}, 3, False),
    ("pc.unknown_benchmark_action", {}, 5, True),
]


def main() -> None:
    rows = []
    for action, params, capability, approved in CASES:
        payload = {"action": action, "params": params, "capabilityLevel": capability, "approved": approved, "dryRun": False}
        started = time.perf_counter()
        response = requests.post(BASE + "/v3/hands/execute", json=payload, timeout=120)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        data = response.json()
        rows.append({"action": action, "http": response.status_code, "success": data.get("success"), "verified": data.get("verification", {}).get("passed"), "latencyMs": elapsed, "error": data.get("error", ""), "method": data.get("method", "")})
    success_count = sum(1 for row in rows if row["success"] is True)
    verified_count = sum(1 for row in rows if row["verified"] is True)
    blocked_count = sum(1 for row in rows if row["success"] is False and row["error"])
    latencies = [row["latencyMs"] for row in rows]
    print("benchmarkCaseCount=" + str(len(rows)))
    print("successCount=" + str(success_count))
    print("verifiedCount=" + str(verified_count))
    print("blockedOrFailedCount=" + str(blocked_count))
    print("latencyMinMs=" + str(min(latencies)))
    print("latencyMedianMs=" + str(round(statistics.median(latencies), 2)))
    print("latencyMaxMs=" + str(max(latencies)))
    for row in rows:
        print("case=" + "|".join(str(row[key]) for key in ("action", "http", "success", "verified", "latencyMs", "error")))
    print("BENCHMARK_HANDS_V35_DONE=True")


if __name__ == "__main__":
    main()
