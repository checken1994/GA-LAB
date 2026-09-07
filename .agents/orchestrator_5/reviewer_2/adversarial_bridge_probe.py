#!/usr/bin/env python3
"""
Adversarial Verification & Exploit Probe — Reviewer 2
Target: scp/hands/task_kernel_bridge.py line 451
Finding: Double-lease release in TaskKernelHandsBridge._policy_blocked_before_dispatch path
         causes OptimisticLockError, crashing into unknown/recovery exception handler.

Demonstrates:
- EXPLOIT: Current TaskKernelHandsBridge.execute() with missing/rejected capability token
  fails with "Hands bridge could not persist unknown state: OptimisticLockError"
  and requiresRecovery=True (violating the requirement that policy rejections transition
  cleanly to FAILED and never cascade into UNKNOWN).
- ROOT CAUSE: task_kernel.transition(task_id, 'FAILED') already atomically releases the lease.
  Calling task_kernel.release(task_id, lease_id) immediately after raises OptimisticLockError.
"""

import asyncio
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scp.pc_control.pc_controller import PCController
from scp.hands.hands_executor import HandsExecutor
from scp.hands.task_kernel_bridge import TaskKernelHandsBridge
from scp.security.capability_epoch import CapabilityAuthority
from scp.task_kernel import TaskKernel


def test_exploit_policy_rejection_cascades_to_recovery_unknown():
    """Reproduces the critical defect where line 451 triggers an unhandled OptimisticLockError."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        w = p / "workspace"
        w.mkdir()
        ca = CapabilityAuthority(p / "cap.json")
        ex = HandsExecutor(controller=PCController(working_dir=w), capability_authority=ca, data_dir=p / "hands")
        bridge = TaskKernelHandsBridge(ex, db_path=p / "kernel.sqlite3")

        # Call mutating action without capability token (Zero-Trust PEP rejection)
        res = asyncio.run(
            bridge.execute(
                action="pc.write_file",
                params={"path": str(w / "exploit.txt"), "content": "payload"},
                capability_level=3,
                approved=True,
                request_key=f"exploit-{uuid.uuid4().hex}",
                capability_token=None,
            )
        )

        print("[EXPLOIT REPRODUCTION RESULT]")
        print("  res.success:", res.get("success"))
        print("  res.error:", res.get("error"))
        print("  res.requiresRecovery:", res.get("requiresRecovery"))
        print("  res.kernel.state:", res.get("kernel", {}).get("state"))

        bridge.kernel.close()

        # Evidence assertions proving the defect:
        assert res.get("requiresRecovery") is True, "Expected requiresRecovery=True from unhandled cascade"
        assert "OptimisticLockError" in res.get("error", ""), "Expected OptimisticLockError in error message"
        print(">> Exploit reproduction CONFIRMED: Policy rejection cascaded into recovery exception handler.")


if __name__ == "__main__":
    test_exploit_policy_rejection_cascades_to_recovery_unknown()
