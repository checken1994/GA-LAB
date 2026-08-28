from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

from scp.api.routes import hands_routes
from scp.hands.hands_executor import HandsExecutor
from scp.security.capability_epoch import CapabilityAuthority


class FakeController:
    def kill_switch_engaged(self) -> bool:
        return False


def test_hands_api_revoke_restore_controls_action_boundary(tmp_path: Path, monkeypatch) -> None:
    executor = HandsExecutor(
        controller=FakeController(),
        capability_authority=CapabilityAuthority(tmp_path / "capability_state.json"),
    )
    app = FastAPI()
    app.include_router(hands_routes.router)
    monkeypatch.setattr(hands_routes, "_hands", executor)

    async def scenario() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            responses = [await client.get("/v3/hands/capabilities")]
            responses.append(await client.post("/v3/hands/capabilities/revoke", json={"reason": "test_api_revoke"}))
            responses.append(await client.post("/v3/hands/execute", json={"action": "pc.status", "dryRun": True}))
            responses.append(await client.post("/v3/hands/capabilities/restore", json={"reason": "test_api_restore"}))
            responses.append(await client.post("/v3/hands/execute", json={"action": "pc.status", "dryRun": True}))
            return responses

    status, revoked, blocked, restored, allowed = asyncio.run(scenario())
    assert status.status_code == 200
    assert status.json()["capability"]["revoked"] is False
    assert revoked.status_code == 200
    assert revoked.json()["capability"]["revoked"] is True
    assert blocked.status_code == 200
    assert blocked.json()["success"] is False
    assert "revoked" in blocked.json()["error"]
    assert restored.status_code == 200
    assert restored.json()["capability"]["revoked"] is False
    assert allowed.status_code == 200
    assert allowed.json()["success"] is True
    assert allowed.json()["capabilityEpoch"] == 2
