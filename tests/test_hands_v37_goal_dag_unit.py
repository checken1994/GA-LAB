from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from scp.hands.goal_parser import GoalParser
from scp.hands.planner import HandsPlanner
from test_hands_v36_planner_unit import make_executor


class GoalParserDagV37Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.planner = HandsPlanner(make_executor(self.root))

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_goal_parser_fallback_is_proposal_only_and_allowlisted(self) -> None:
        parser = GoalParser(self.planner)
        result = await parser.parse("Tìm các nguồn công khai về SCP self correcting process", prefer_local=False)
        self.assertTrue(result["success"])
        self.assertTrue(result["proposalOnly"])
        self.assertFalse(result["approved"])
        self.assertEqual(result["lineage"], "deterministic_fallback")
        self.assertEqual(result["plan"]["version"], "3.7")
        self.assertEqual(result["plan"]["steps"][0]["action"], "web.search_public")
        self.assertIn(result["plan"]["steps"][0]["action"], {item["name"] for item in self.planner.executor.registry.list()})

    async def test_dag_runs_independent_steps_in_parallel_then_dependency(self) -> None:
        active = 0
        max_active = 0

        async def fake_execute(action: str, params: dict, capability_level: int, approved: bool, dry_run: bool) -> dict:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.08)
            active -= 1
            return {"success": True, "evidence": {"action": action}, "verification": {"passed": True, "rule": "fake"}}

        self.planner.executor.execute = fake_execute
        plan = self.planner.create_plan("Parallel evidence", [
            {"stepId": "a", "action": "pc.status"},
            {"stepId": "b", "action": "web.tab_snapshot"},
            {"stepId": "c", "action": "pc.status", "dependsOn": ["a", "b"]},
        ])
        result = await self.planner.run_dag(plan["planId"], max_parallel=2)
        self.assertTrue(result["success"])
        self.assertEqual(result["plan"]["version"], "3.7")
        self.assertEqual(result["plan"]["scheduler"], "dag")
        self.assertEqual([step["state"] for step in result["plan"]["steps"]], ["VERIFIED", "VERIFIED", "VERIFIED"])
        self.assertGreaterEqual(max_active, 2)

    async def test_dag_risky_node_waits_for_approval(self) -> None:
        plan = self.planner.create_plan("Approval DAG", [{"stepId": "open", "action": "web.open_public_tab", "params": {"url": "https://example.com"}, "capabilityLevel": 2}])
        result = await self.planner.run_dag(plan["planId"], capability_level=2, approved=False, max_parallel=2)
        self.assertFalse(result["success"])
        self.assertTrue(result["waitingApproval"])
        self.assertEqual(result["plan"]["state"], "WAITING_APPROVAL")
        self.assertEqual(result["plan"]["steps"][0]["state"], "WAITING_APPROVAL")

    async def test_dag_rejects_forward_dependency_at_plan_creation(self) -> None:
        with self.assertRaises(ValueError):
            self.planner.create_plan("Bad DAG", [{"stepId": "a", "action": "pc.status", "dependsOn": ["b"]}, {"stepId": "b", "action": "pc.status"}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
