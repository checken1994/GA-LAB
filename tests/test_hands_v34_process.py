from __future__ import annotations

import requests

BASE = "http://127.0.0.1:8002"


def execute(action: str, params: dict | None = None, capability: int = 0, approved: bool = False) -> dict:
    response = requests.post(BASE + "/v3/hands/execute", json={"action": action, "params": params or {}, "capabilityLevel": capability, "approved": approved, "dryRun": False}, timeout=120)
    response.raise_for_status()
    return response.json()


def check(name: str, condition: bool, detail: object) -> None:
    print(f"{name}={'PASS' if condition else 'FAIL'}|{detail}")
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def main() -> None:
    status = requests.get(BASE + "/v3/hands/status", timeout=45).json()
    check("v34_status", status.get("version") == "3.4", status)

    owned = execute("pc.process_list_owned")
    check("process_list_owned", owned.get("success") is True and owned.get("verification", {}).get("passed") is True, owned)

    blocked_start = execute("pc.process_start_managed", {"commandId": "hands_probe"}, capability=3, approved=False)
    check("start_without_approval_blocked", blocked_start.get("success") is False, blocked_start)

    started = execute("pc.process_start_managed", {"commandId": "hands_probe"}, capability=3, approved=True)
    pid = started.get("pid")
    check("managed_start_owned", started.get("success") is True and started.get("owned") is True and isinstance(pid, int), started)

    info = execute("pc.process_info", {"pid": pid})
    check("managed_info", info.get("success") is True and info.get("owned") is True and info.get("alive") is True, info)

    arbitrary = execute("pc.process_stop_owned", {"pid": int(pid) + 1}, capability=4, approved=True)
    check("arbitrary_pid_stop_blocked", arbitrary.get("success") is False and "not owned" in arbitrary.get("error", "").lower(), arbitrary)

    stopped = execute("pc.process_stop_owned", {"pid": pid}, capability=4, approved=True)
    check("managed_stop_owned", stopped.get("success") is True and stopped.get("owned") is True, stopped)

    after = execute("pc.process_info", {"pid": pid})
    check("stopped_process_not_owned", after.get("success") is False, after)

    print("HANDS_V34_PROCESS_PASS=True")


if __name__ == "__main__":
    main()
