from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi import FastAPI

from scp.api.routes import hands_routes
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
        self.calls = 0

    def _audit(self, event: str, payload: dict) -> None:
        return None

    async def execute(self, action: str, params: dict, capability_level: int, approved: bool, dry_run: bool) -> dict:
        self.calls += 1
        return dict(self.results.pop(0))

    async def rollback(self, checkpoint_id: str, capability_level: int = 3, approved: bool = False) -> dict:
        return {"success": True, "checkpointId": checkpoint_id}


def test_hands_execute_route_persists_unknown_then_reconciles(tmp_path: Path, monkeypatch) -> None:
    fake = FakeExecutor(
        tmp_path,
        [
            {"success": False, "error": "lost response from local driver", "verification": {"passed": False}},
            {"success": True, "verification": {"passed": True, "rule": "fake"}, "evidence": {"changed": True}},
        ],
    )
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    bridge = TaskKernelHandsBridge(fake, kernel=kernel)
    app = FastAPI()
    app.include_router(hands_routes.router)
    monkeypatch.setattr(hands_routes, "_hands", fake)
    monkeypatch.setattr(hands_routes, "_hands_bridge", bridge)

    async def scenario() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/v3/hands/execute",
                headers={"X-SCP-Idempotency-Key": "route-retry-1"},
                json={"action": "pc.write_file", "params": {"path": "safe.txt", "content": "x"}, "capabilityLevel": 3, "approved": True},
            )
            unknown = first.json()
            reconciled = await client.post(
                "/v3/hands/reconcile",
                json={
                    "taskId": unknown["kernel"]["taskId"],
                    "checkpointId": unknown["kernel"]["checkpointId"],
                    "outcome": "NOT_APPLIED",
                    "evidenceRef": "hands://driver/status/not-applied",
                },
            )
            second = await client.post(
                "/v3/hands/execute",
                headers={"X-SCP-Idempotency-Key": "route-retry-1"},
                json={"action": "pc.write_file", "params": {"path": "safe.txt", "content": "x"}, "capabilityLevel": 3, "approved": True},
            )
            return first, reconciled, second

    first, reconciled, second = asyncio.run(scenario())
    assert first.status_code == 200
    assert first.json()["requiresRecovery"] is True
    assert first.json()["kernel"]["state"] == "UNKNOWN"
    assert reconciled.status_code == 200
    assert reconciled.json()["success"] is True
    assert reconciled.json()["task"]["state"] == "QUEUED"
    assert second.status_code == 200
    assert second.json()["success"] is True
    assert second.json()["kernel"]["state"] == "COMPLETED"
    assert fake.calls == 2
    kernel.close()
