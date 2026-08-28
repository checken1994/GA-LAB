from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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

    def _resolve_path(self, path: str) -> Path:
        candidate = Path(path)
        return (candidate if candidate.is_absolute() else self.root / candidate).resolve()

    def _inside_root(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.root)
            return True
        except ValueError:
            return False

    def _sensitive(self, path: Path) -> bool:
        return any(part.lower() in {".env", "credentials", "secrets"} for part in path.parts)

    def status(self) -> dict:
        return {"controller": "online"}

    async def execute(self, command: str, capability_level: int, approved: bool, timeout: int) -> dict:
        return {"returnCode": 0, "stdout": "## main\n", "stderr": ""}


class FakeNavigator:
    async def browse_public(self, url: str, max_chars: int = 100_000) -> dict:
        return {"success": True, "url": url, "text": '<html><a href="/one">One</a><a href="https://example.org/two">Two</a></html>'}

    async def search_public(self, query: str, max_results: int = 10) -> dict:
        return {"success": True, "results": []}

    async def browse_logged_in(self, url: str) -> dict:
        return {"success": True, "url": url, "text": "local"}


class HandsV33ActionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.controller = FakeController(self.root)
        self.navigator = FakeNavigator()
        self.executor = HandsExecutor(self.controller, self.navigator)
        self.executor.data_dir = self.root / "hands"
        self.executor.data_dir.mkdir(parents=True, exist_ok=True)
        self.executor.audit_path = self.executor.data_dir / "audit.jsonl"
        self.executor.checkpoint_path = self.executor.data_dir / "checkpoints.jsonl"
        self.executor.backup_dir = self.executor.data_dir / "backups"
        self.executor.backup_dir.mkdir(parents=True, exist_ok=True)

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_file_hash(self) -> None:
        path = self.root / "sample.txt"
        path.write_text("hash-me", encoding="utf-8")
        result = await self.executor.execute("pc.file_hash", {"path": "sample.txt"})
        self.assertTrue(result["success"])
        self.assertEqual(result["verification"]["passed"], True)
        self.assertEqual(result["bytes"], 7)
        self.assertEqual(len(result["sha256"]), 64)

    async def test_search_workspace(self) -> None:
        workspace = self.root / "workspace"
        workspace.mkdir()
        (workspace / "a.txt").write_text("SCP_V33_UNIT_TOKEN\n", encoding="utf-8")
        result = await self.executor.execute("pc.search_workspace", {"path": "workspace", "query": "SCP_V33_UNIT_TOKEN"})
        self.assertTrue(result["success"])
        self.assertEqual(result["verification"]["passed"], True)
        self.assertEqual(result["evidence"]["matchCount"], 1)

    async def test_directory_tree(self) -> None:
        nested = self.root / "tree" / "nested"
        nested.mkdir(parents=True)
        (nested / "file.txt").write_text("x", encoding="utf-8")
        result = await self.executor.execute("pc.directory_tree", {"path": "tree", "maxDepth": 3})
        self.assertTrue(result["success"])
        self.assertEqual(result["verification"]["passed"], True)
        self.assertIn("nested", result["entries"])

    async def test_git_status(self) -> None:
        result = await self.executor.execute("pc.git_status")
        self.assertTrue(result["success"])
        self.assertEqual(result["verification"]["passed"], True)
        self.assertEqual(result["evidence"]["returnCode"], 0)

    async def test_validate_jsonl(self) -> None:
        path = self.root / "events.jsonl"
        path.write_text('{"event":"ok"}\n{"event":"next"}\n', encoding="utf-8")
        result = await self.executor.execute("pc.validate_jsonl", {"path": "events.jsonl"})
        self.assertTrue(result["success"])
        self.assertEqual(result["verification"]["passed"], True)
        self.assertEqual(result["validLines"], 2)
        self.assertEqual(result["invalidLines"], 0)

    async def test_extract_links(self) -> None:
        result = await self.executor.execute("web.extract_links", {"url": "https://example.com"})
        self.assertTrue(result["success"])
        self.assertEqual(result["verification"]["passed"], True)
        self.assertEqual(result["links"], ["https://example.com/one", "https://example.org/two"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
