from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.hands.planner import HandsPlanner
from scp.hands.action_registry import ActionDefinition

class FakeRegistry:
    def __init__(self):
        self.mock_tool = ActionDefinition(
            name="high_privilege_tool",
            description="test",
            domain="system",
            risk="high",
            capability_level=3,
            requires_approval=True,
            mutates_state=True,
            verifier="",
            rollback=""
        )
    def require(self, action: str) -> ActionDefinition:
        return self.mock_tool
    def get(self, action: str) -> ActionDefinition | None:
        return self.mock_tool

class FakeExecutor:
    def __init__(self):
        self.registry = FakeRegistry()
        self.data_dir = ROOT / "data"
        
    async def execute(self, action: str, params: dict, capability_level: int, approved: bool, dry_run: bool) -> dict:
        return {"success": True}
        
    def _audit(self, event, payload):
        pass

class TestP1CapabilityInvariant(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.planner = HandsPlanner(FakeExecutor())

    async def test_inv06_prevent_self_escalation(self):
        plan_def = [
            {
                "action": "high_privilege_tool",
                "params": {},
                "capabilityLevel": 99,
                "approved": True
            }
        ]
        
        public_plan = self.planner.create_plan("Hack the mainframe", plan_def)
        plan_id = public_plan["planId"]
        
        result = await self.planner.run_plan(plan_id, capability_level=1, approved=True, stop_on_failure=True)
        
        self.assertFalse(result["success"])
        
        updated_plan = self.planner.get_plan(plan_id)
        step = updated_plan["steps"][0]
        
        self.assertEqual(step["state"], "FAILED", "Step must fail due to capability restriction, not wait or pass.")
        self.assertEqual(updated_plan["state"], "FAILED")
        self.assertIn("Explicit approval or higher capability is required", step["error"])

if __name__ == "__main__":
    unittest.main()