from __future__ import annotations

import asyncio
from pathlib import Path

from scp.hands.action_registry import ActionRegistry
from scp.hands.task_kernel_bridge import TaskKernelHandsBridge
from scp.security.capability_epoch import CapabilityAuthority
from scp.task_kernel import TaskKernel


class FakeExecutor:
    def __init__(self, root: Path, results: list[dict]) -> None:
        self.data_dir = root / "hands"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.registry = ActionRegistry()
        self.capability_authority = CapabilityAuthority(self.data_dir / "capability_state.json")
        self.results = list(results)
        self.calls: list[str] = []
        self.audit: list[tuple[str, dict]] = []

    def _audit(self, event: str, payload: dict) -> None:
        self.audit.append((event, payload))

    async def execute(self, action: str, params: dict, capability_level: int, approved: bool, dry_run: bool) -> dict:
        self.calls.append(action)
        return dict(self.results.pop(0))

    async def rollback(self, checkpoint_id: str, capability_level: int = 3, approved: bool = False) -> dict:
        return {"success": True, "checkpointId": checkpoint_id}


def test_bridge_commits_verified_mutation_to_kernel(tmp_path: Path) -> None:
    fake = FakeExecutor(
        tmp_path,
        [{"success": True, "verification": {"passed": True, "rule": "fake"}, "evidence": {"changed": True}}],
    )
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    bridge = TaskKernelHandsBridge(fake, kernel=kernel)

    result = asyncio.run(bridge.execute("pc.write_file", {"path": "safe.txt", "content": "x"}, 3, True, request_key="req-verified"))

    assert result["success"] is True
    assert result["kernel"]["state"] == "COMPLETED"
    assert kernel.get_task(result["kernel"]["taskId"])["state"] == "COMPLETED"
    assert [event["type"] for event in kernel.get_events(result["kernel"]["taskId"])] [-1] == "TASK_COMPLETED"
    assert fake.calls == ["pc.write_file"]
    kernel.close()


def test_bridge_requires_reconcile_before_same_key_retry(tmp_path: Path) -> None:
    fake = FakeExecutor(
        tmp_path,
        [
            {"success": False, "error": "lost response from local driver", "verification": {"passed": False}},
            {"success": True, "verification": {"passed": True, "rule": "fake"}, "evidence": {"changed": True}},
        ],
    )
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    bridge = TaskKernelHandsBridge(fake, kernel=kernel)

    unknown = asyncio.run(bridge.execute("pc.write_file", {"path": "safe.txt", "content": "x"}, 3, True, request_key="req-retry"))
    task_id = unknown["kernel"]["taskId"]
    checkpoint_id = unknown["kernel"]["checkpointId"]
    assert unknown["success"] is False
    assert unknown["requiresRecovery"] is True
    assert unknown["safeToRetry"] is False
    assert unknown["kernel"]["state"] == "UNKNOWN"

    reconciled = bridge.reconcile_unknown(task_id, checkpoint_id, "NOT_APPLIED", "hands://driver/status/not-applied")
    assert reconciled["state"] == "QUEUED"

    retried = asyncio.run(bridge.execute("pc.write_file", {"path": "safe.txt", "content": "x"}, 3, True, request_key="req-retry"))
    assert retried["success"] is True
    assert retried["kernel"]["state"] == "COMPLETED"
    assert fake.calls == ["pc.write_file", "pc.write_file"]
    assert kernel.verify_journal(task_id)["hash_chain_valid"] is True
    kernel.close()
