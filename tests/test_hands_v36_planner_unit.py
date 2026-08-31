from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.hands.hands_executor import HandsExecutor
from scp.hands.planner import HandsPlanner


class FakeController:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.working_dir = self.root
        self.backup_dir = self.root / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def kill_switch_engaged(self) -> bool:
        return False

    def status(self) -> dict:
        return {"controller": "online"}

    async def execute(self, command: str, capability_level: int, approved: bool, timeout: int) -> dict:
        return {"success": True, "returnCode": 0, "stdout": "ok", "stderr": ""}


class FakeBrowser:
    def __init__(self, pages: list[dict] | None = None) -> None:
        self.pages = pages if pages is not None else [{"id": "one", "type": "page", "title": "Example", "url": "https://example.com"}]

    async def targets(self) -> list[dict]:
        return list(self.pages)

    async def evaluate(self, expression: str, target: dict | None = None):
        if "document.title" in expression:
            return target.get("title", "") if target else ""
        return "Planner evidence: Example Domain"

    @staticmethod
    def validate_url(url: str) -> str:
        if not url.startswith(("http://", "https://")):
            raise ValueError("Only public http/https URLs are allowed")
        return url

    async def navigate_and_read(self, url: str, target: dict | None = None) -> dict:
        return {"success": True, "url": url, "title": "Example", "text": "Example Domain"}


class FakeNavigator:
    def __init__(self, pages: list[dict] | None = None) -> None:
        self.browser = FakeBrowser(pages)

    async def search_public(self, query: str, max_results: int = 10) -> dict:
        return {"success": True, "results": [{"title": "Example", "url": "https://example.com"}]}

    async def browse_public(self, url: str, max_chars: int = 100_000) -> dict:
        return {"success": True, "url": url, "text": "Example Domain"}

    async def browse_logged_in(self, url: str) -> dict:
        return {"success": True, "url": url, "text": "approved"}


def make_executor(root: Path, pages: list[dict] | None = None, suffix: str = "hands") -> HandsExecutor:
    executor = HandsExecutor(FakeController(root), FakeNavigator(pages))
    executor.data_dir = root / suffix
    executor.data_dir.mkdir(parents=True, exist_ok=True)
    executor.audit_path = executor.data_dir / "audit.jsonl"
    executor.checkpoint_path = executor.data_dir / "checkpoints.jsonl"
    executor.backup_dir = executor.data_dir / "backups"
    executor.backup_dir.mkdir(parents=True, exist_ok=True)
    executor.processes.data_dir = executor.data_dir
    executor.processes.ledger_path = executor.data_dir / "processes.jsonl"
    return executor


class PlannerV361Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.planner = HandsPlanner(make_executor(self.root))

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_create_rejects_unknown_duplicate_and_invalid_retry(self) -> None:
        with self.assertRaises(ValueError):
            self.planner.create_plan("bad", [{"action": "pc.not_registered"}])
        with self.assertRaises(ValueError):
            self.planner.create_plan("bad", [{"stepId": "same", "action": "pc.status"}, {"stepId": "same", "action": "pc.status"}])
        bounded = self.planner.create_plan("bounded", [{"action": "pc.status", "retryPolicy": {"maxAttempts": 9}}])
        self.assertEqual(bounded["steps"][0]["retryPolicy"]["maxAttempts"], 3)

    async def test_create_persists_conditions_and_retry_policy(self) -> None:
        plan = self.planner.create_plan("Read public evidence", [{"stepId": "a", "action": "web.search_public", "params": {"query": "SCP"}}, {"stepId": "b", "action": "web.browse_public", "params": {"url": "https://example.com"}, "dependsOn": ["a"], "precondition": {"type": "previous_steps_verified", "stepIds": ["a"]}, "postcondition": {"type": "text_contains", "value": "Example"}, "retryPolicy": {"maxAttempts": 2, "backoffSeconds": 0, "on": "verification_failed"}}])
        self.assertEqual(plan["version"], "3.7")
        self.assertEqual(plan["state"], "PLANNED")
        self.assertEqual(plan["steps"][1]["precondition"]["type"], "previous_steps_verified")
        self.assertEqual(plan["steps"][1]["retryPolicy"]["maxAttempts"], 2)
        self.assertTrue(self.planner.plan_path.exists())
        self.assertGreaterEqual(len(self.planner.plan_path.read_text(encoding="utf-8").splitlines()), 1)

    async def test_run_verifies_postcondition_and_completes(self) -> None:
        plan = self.planner.create_plan("Observe public page", [{"action": "web.tab_snapshot"}, {"action": "web.dom_snapshot", "capabilityLevel": 1, "approved": True, "postcondition": {"type": "text_contains", "value": "Example Domain"}}])
        result = await self.planner.run_plan(plan["planId"], agent_id="SCP")
        self.assertTrue(result["success"])
        self.assertEqual(result["plan"]["state"], "COMPLETED")
        self.assertEqual([step["state"] for step in result["plan"]["steps"]], ["VERIFIED", "VERIFIED"])
        self.assertTrue(result["plan"]["steps"][1]["evidence"]["postconditionPassed"])

    async def test_precondition_failure_stops_before_executor(self) -> None:
        plan = self.planner.create_plan("Wait for impossible state", [{"action": "pc.status", "precondition": {"type": "plan_state", "equals": "COMPLETED"}}])
        result = await self.planner.run_plan(plan["planId"], agent_id="SCP")
        self.assertFalse(result["success"])
        self.assertEqual(result["plan"]["state"], "FAILED")
        self.assertIn("Precondition failed", result["plan"]["steps"][0]["error"])
        self.assertFalse(result["plan"]["steps"][0]["evidence"]["preconditionPassed"])

    async def test_postcondition_failure_is_not_marked_verified(self) -> None:
        plan = self.planner.create_plan("Require missing phrase", [{"action": "web.browse_public", "params": {"url": "https://example.com"}, "postcondition": {"type": "text_contains", "value": "NOT_PRESENT"}}])
        result = await self.planner.run_plan(plan["planId"], agent_id="SCP")
        self.assertFalse(result["success"])
        self.assertEqual(result["plan"]["steps"][0]["state"], "FAILED")
        self.assertFalse(result["plan"]["steps"][0]["evidence"]["postconditionPassed"])

    async def test_retry_is_bounded_and_records_retry_event(self) -> None:
        calls = 0

        async def flaky_execute(action: str, params: dict, capability_level: int, approved: bool, dry_run: bool) -> dict:
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"success": False, "error": "transient", "verification": {"passed": False, "rule": "fake"}}
            return {"success": True, "evidence": {"ready": True}, "verification": {"passed": True, "rule": "fake"}}

        self.planner.executor.execute = flaky_execute
        plan = self.planner.create_plan("Retry transient failure", [{"action": "pc.status", "retryPolicy": {"maxAttempts": 2, "on": "execution_error"}}])
        result = await self.planner.run_plan(plan["planId"], agent_id="SCP")
        self.assertTrue(result["success"])
        self.assertEqual(calls, 2)
        self.assertEqual(result["plan"]["steps"][0]["attempts"], 2)
        events = [json.loads(line).get("event") for line in self.planner.plan_path.read_text(encoding="utf-8").splitlines()]
        self.assertIn("PLAN_STEP_RETRY", events)

    async def test_risky_step_pauses_for_approval_without_execution(self) -> None:
        plan = self.planner.create_plan("Open public tab", [{"action": "web.open_public_tab", "params": {"url": "https://example.com"}, "capabilityLevel": 2}])
        result = await self.planner.run_plan(plan["planId"], capability_level=2, approved=False, agent_id="SCP")
        self.assertFalse(result["success"])
        self.assertTrue(result["waitingApproval"])
        self.assertEqual(result["plan"]["state"], "WAITING_APPROVAL")
        self.assertEqual(result["plan"]["steps"][0]["state"], "WAITING_APPROVAL")

    async def test_missing_browser_target_becomes_failed_with_evidence(self) -> None:
        planner = HandsPlanner(make_executor(self.root, pages=[], suffix="empty-hands"))
        plan = planner.create_plan("Need a page", [{"action": "web.dom_snapshot", "capabilityLevel": 1, "approved": True}])
        result = await planner.run_plan(plan["planId"], agent_id="SCP")
        self.assertFalse(result["success"])
        self.assertEqual(result["plan"]["state"], "FAILED")
        self.assertFalse(result["plan"]["steps"][0]["evidence"]["verificationPassed"])

    async def test_status_reads_latest_plan_state(self) -> None:
        plan = self.planner.create_plan("Status probe", [{"action": "pc.status"}])
        status = self.planner.status()
        self.assertEqual(status["version"], "3.7")
        self.assertEqual(status["activePlan"]["planId"], plan["planId"])
        records = [json.loads(line) for line in self.planner.plan_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[0]["event"], "PLAN_CREATED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
