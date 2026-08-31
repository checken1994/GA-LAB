from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.task_kernel import TaskKernel

class TestP1ChaosRecovery(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_kernel.db"
        self.kernel = TaskKernel(db_path=str(self.db_path))

    async def asyncTearDown(self):
        if hasattr(self, 'kernel') and self.kernel:
            self.kernel.close()
        if hasattr(self, 'kernel_2') and self.kernel_2:
            self.kernel_2.close()
        self.temp_dir.cleanup()

    async def test_reconcile_crash_recovery(self):
        task = self.kernel.create_task("chaos_task", "system", "Simulate a crash")
        task_id = task["task_id"]
        
        self.kernel.transition(task_id, "PLANNING", "system", "plan")
        self.kernel.transition(task_id, "READY", "system", "ready")
        self.kernel.transition(task_id, "QUEUED", "system", "enqueue")
        
        lease = self.kernel.claim(task_id, "worker1")
        self.assertIsNotNone(lease)
        
        self.kernel.transition(task_id, "RUNNING", "worker1", "start run")
        
        t_before = self.kernel.get_task(task_id)
        self.assertEqual(t_before["state"], "RUNNING")
        
        # Simulate a CRASH
        self.kernel.close()
        
        self.kernel_2 = TaskKernel(db_path=str(self.db_path))
        
        # System reboots, recovers tasks in RUNNING state
        self.kernel_2.transition(task_id, "RECOVERING", "system", "crash recovery")
        
        t_recovered = self.kernel_2.get_task(task_id)
        self.assertEqual(t_recovered["state"], "RECOVERING", "Task must be marked as RECOVERING after a crash.")

if __name__ == "__main__":
    unittest.main()