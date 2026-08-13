from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.hands.hands_executor import HandsExecutor


class FakeController:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.working_dir = self.root
        self.backup_dir = self.root / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def kill_switch_engaged(self) -> bool:
        return False

    async def execute(self, command: str, capability_level: int, approved: bool, timeout: int) -> dict:
        return {"returnCode": 0, "stdout": "ok", "stderr": ""}


class FakeBrowser:
    def __init__(self) -> None:
        self.pages = [
            {"id": "chat-1", "type": "page", "title": "ChatGPT", "url": "https://chatgpt.com/"},
            {"id": "docs-1", "type": "page", "title": "Public Docs", "url": "https://example.com/docs"},
        ]
        self.body = "Dashboard Ready SCP_BROWSER_TEST_TEXT"

    async def targets(self) -> list[dict]:
        return list(self.pages)

    @staticmethod
    def validate_url(url: str) -> str:
        if not url.startswith(("http://", "https://")) or "@" in url:
            raise ValueError("Only public http/https URLs are allowed")
        return url

    async def evaluate(self, expression: str, target: dict | None = None):
        if "document.title" in expression:
            return target.get("title", "") if target else ""
        if "document.body" in expression:
            return self.body
        return True

    async def navigate_and_read(self, url: str, target: dict | None = None) -> dict:
        return {"success": True, "url": url, "title": "Public Page", "text": "Public content"}


class FakeNavigator:
    def __init__(self) -> None:
        self.browser = FakeBrowser()

    async def search_public(self, query: str, max_results: int = 10) -> dict:
        return {"success": True, "results": []}

    async def browse_public(self, url: str, max_chars: int = 100_000) -> dict:
        return {"success": True, "url": url, "text": "public"}

    async def browse_logged_in(self, url: str) -> dict:
        return {"success": True, "url": url, "text": "local"}


class BrowserAutomationV35Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.executor = HandsExecutor(FakeController(root), FakeNavigator())
        self.executor.data_dir = root / "hands"
        self.executor.data_dir.mkdir(parents=True, exist_ok=True)
        self.executor.audit_path = self.executor.data_dir / "audit.jsonl"
        self.executor.checkpoint_path = self.executor.data_dir / "checkpoints.jsonl"
        self.executor.backup_dir = self.executor.data_dir / "backups"
        self.executor.backup_dir.mkdir(parents=True, exist_ok=True)

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_tab_snapshot_lists_bounded_pages(self) -> None:
        result = await self.executor.execute("web.tab_snapshot")
        self.assertTrue(result["success"])
        self.assertEqual(result["evidence"]["pageCount"], 2)
        self.assertEqual(result["pages"][0]["id"], "chat-1")

    async def test_dom_snapshot_requires_approval_and_selects_hostname(self) -> None:
        blocked = await self.executor.execute("web.dom_snapshot", {"hostname": "chatgpt.com"}, capability_level=1, approved=False)
        self.assertFalse(blocked["success"])
        allowed = await self.executor.execute("web.dom_snapshot", {"hostname": "chatgpt.com"}, capability_level=1, approved=True)
        self.assertTrue(allowed["success"])
        self.assertIn("SCP_BROWSER_TEST_TEXT", allowed["text"])
        self.assertEqual(allowed["url"], "https://chatgpt.com/")

    async def test_open_public_tab_requires_approval_and_uses_target_id(self) -> None:
        blocked = await self.executor.execute("web.open_public_tab", {"url": "https://example.com", "targetId": "docs-1"}, capability_level=2, approved=False)
        self.assertFalse(blocked["success"])
        allowed = await self.executor.execute("web.open_public_tab", {"url": "https://example.com", "targetId": "docs-1"}, capability_level=2, approved=True)
        self.assertTrue(allowed["success"])
        self.assertEqual(allowed["verification"]["passed"], True)

    async def test_follow_public_link_requires_approval(self) -> None:
        result = await self.executor.execute("web.follow_public_link", {"url": "https://example.com/docs", "hostname": "example.com"}, capability_level=2, approved=True)
        self.assertTrue(result["success"])
        self.assertEqual(result["url"], "https://example.com/docs")

    async def test_wait_for_text_verifies_dom_evidence(self) -> None:
        blocked = await self.executor.execute("web.wait_for_text", {"text": "SCP_BROWSER_TEST_TEXT", "hostname": "example.com"}, capability_level=1, approved=False)
        self.assertFalse(blocked["success"])
        allowed = await self.executor.execute("web.wait_for_text", {"text": "SCP_BROWSER_TEST_TEXT", "hostname": "example.com", "timeoutSeconds": 2}, capability_level=1, approved=True)
        self.assertTrue(allowed["success"])
        self.assertTrue(allowed["verification"]["passed"])

    async def test_invalid_navigation_url_is_not_executed(self) -> None:
        result = await self.executor.execute("web.open_public_tab", {"url": "javascript:alert(1)", "targetId": "docs-1"}, capability_level=2, approved=True)
        self.assertFalse(result["success"])
        self.assertFalse(result["verification"]["passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
