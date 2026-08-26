from __future__ import annotations

import asyncio
from pathlib import Path

from scp.hands.hands_executor import HandsExecutor
from scp.security.capability_epoch import CapabilityAuthority


class FakeController:
    def kill_switch_engaged(self) -> bool:
        return False


def test_capability_epoch_revoke_and_restore_is_durable(tmp_path: Path) -> None:
    state = tmp_path / "capability_state.json"
    authority = CapabilityAuthority(state)
    token = authority.issue("test-action")
    assert authority.validate(token)

    revoked = authority.revoke(reason="test_revoke", actor="test")
    assert revoked["revoked"] is True
    assert revoked["epoch"] == 1
    assert not authority.validate(token)
    assert CapabilityAuthority(state).status()["revoked"] is True

    restored = authority.restore(reason="test_restore", actor="test")
    assert restored["revoked"] is False
    assert restored["epoch"] == 2
    assert not authority.validate(token)
    fresh = authority.issue("test-action")
    assert fresh.epoch == 2
    assert authority.validate(fresh)


def test_hands_executor_fails_closed_when_capabilities_revoked(tmp_path: Path) -> None:
    authority = CapabilityAuthority(tmp_path / "capability_state.json")
    executor = HandsExecutor(controller=FakeController(), capability_authority=authority)

    async def run() -> tuple[dict, dict, dict]:
        before = await executor.execute("pc.status", dry_run=True)
        executor.revoke_capabilities("test_revoke", "test")
        blocked = await executor.execute("pc.status", dry_run=True)
        executor.restore_capabilities("test_restore", "test")
        after = await executor.execute("pc.status", dry_run=True)
        return before, blocked, after

    before, blocked, after = asyncio.run(run())
    assert before["success"] is True
    assert blocked["success"] is False
    assert "revoked" in blocked["error"]
    assert after["success"] is True
    assert after["capabilityEpoch"] == 2
