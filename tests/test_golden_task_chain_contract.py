from __future__ import annotations

import asyncio
import json
from pathlib import Path

from scp.hands.hands_executor import HandsExecutor
from scp.hands.planner import HandsPlanner


class FakeController:
    def kill_switch_engaged(self) -> bool:
        return False

    def status(self) -> dict[str, str]:
        return {"controller": "online"}


def test_safe_golden_task_chain_captures_policy_tool_verifier_and_audit(tmp_path: Path) -> None:
    executor = HandsExecutor(controller=FakeController())
    executor.data_dir = tmp_path / "hands"
    executor.data_dir.mkdir(parents=True, exist_ok=True)
    executor.audit_path = executor.data_dir / "audit.jsonl"
    executor.checkpoint_path = executor.data_dir / "checkpoints.jsonl"
    executor.capability_authority.state_path = executor.data_dir / "capability_state.json"
    planner = HandsPlanner(executor)
    plan = planner.create_plan(
        "Safe status golden task",
        [
            {"stepId": "observe", "action": "pc.status", "postcondition": {"type": "success"}},
        ],
    )

    result = asyncio.run(planner.run_plan(plan["planId"], dry_run=True))
    step = result["plan"]["steps"][0]
    audit_events = [json.loads(line)["event"] for line in executor.audit_path.read_text(encoding="utf-8").splitlines()]

    assert result["success"] is True
    assert result["plan"]["state"] == "COMPLETED"
    assert step["state"] == "VERIFIED"
    assert step["evidence"]["verificationPassed"] is True
    assert step["evidence"]["postconditionPassed"] is True
    assert "ACTION_DRY_RUN" in audit_events
    assert "PLAN_STEP_VERIFIED" in [json.loads(line)["event"] for line in planner.plan_path.read_text(encoding="utf-8").splitlines()]
