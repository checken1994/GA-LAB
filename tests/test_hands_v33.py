from __future__ import annotations

import json
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"


def post(action: str, params: dict | None = None, capability: int = 0, approved: bool = False, dry_run: bool = False) -> dict:
    response = requests.post(
        BASE + "/v3/hands/execute",
        json={"action": action, "params": params or {}, "capabilityLevel": capability, "approved": approved, "dryRun": dry_run},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def check(name: str, condition: bool, detail: object) -> None:
    print(f"{name}={'PASS' if condition else 'FAIL'}|{detail}")
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def main() -> None:
    actions = requests.get(BASE + "/v3/hands/actions", timeout=45).json()
    check("hands_v33_registry", actions.get("version") == "3.3" and len(actions.get("actions", [])) == 16, actions)

    status = post("pc.status")
    check("pc_status", status.get("success") is True and status.get("verification", {}).get("passed") is True, status)

    tree = post("pc.directory_tree", {"path": "data/hands", "maxDepth": 2})
    check("directory_tree", tree.get("success") is True and tree.get("verification", {}).get("passed") is True, tree)

    audit_path = "data/hands/audit.jsonl"
    audit = post("pc.validate_jsonl", {"path": audit_path})
    check("audit_jsonl_valid", audit.get("success") is True and audit.get("verification", {}).get("passed") is True, audit)

    git = post("pc.git_status")
    check("git_status", git.get("success") is True and git.get("verification", {}).get("passed") is True, git)

    links = post("web.extract_links", {"url": "https://example.com", "maxChars": 5000})
    check("extract_links", links.get("success") is True and links.get("verification", {}).get("passed") is True, links)

    token = f"SCP_HANDS_V33_WRITE_{int(time.time())}"
    test_path = f"data/hands/manual-write-{int(time.time())}.txt"
    write = post("pc.write_file", {"path": test_path, "content": token + "\n"}, capability=3, approved=True)
    checkpoint = write.get("checkpointId")
    check("write_created_checkpoint", write.get("success") is True and bool(checkpoint) and write.get("verification", {}).get("passed") is True, write)

    hashed = post("pc.file_hash", {"path": test_path})
    check("hash_after_write", hashed.get("success") is True and hashed.get("sha256"), hashed)

    found = post("pc.search_workspace", {"path": "data/hands", "query": token})
    check("search_finds_written_token", found.get("success") is True and found.get("evidence", {}).get("matchCount", 0) >= 1, found)

    rollback_response = requests.post(BASE + "/v3/hands/rollback", json={"checkpointId": checkpoint, "capabilityLevel": 3, "approved": True}, timeout=120)
    rollback_response.raise_for_status()
    rollback = rollback_response.json()
    check("rollback_success", rollback.get("success") is True, rollback)

    after = post("pc.file_hash", {"path": test_path})
    check("file_absent_after_rollback", after.get("success") is False, after)

    print("HANDS_V33_WRITE_ROLLBACK_PASS=True")


if __name__ == "__main__":
    main()
