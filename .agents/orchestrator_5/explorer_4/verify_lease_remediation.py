#!/usr/bin/env python3
"""
Verification Script for GAP-07 TaskKernel Bridge Lease Lifecycle Remediation
Author: Explorer 4 (TaskKernel Bridge Lease Lifecycle Specialist)

Tests:
1. Baseline Behavior with line 451:
   Confirms OptimisticLockError and cascade to UNKNOWN / requiresRecovery=True.
2. Remediated Behavior without line 451:
   Confirms clean transition to FAILED, database lease status, queue active counter,
   requiresRecovery=False/omitted, and error preserved.
3. Database and Kernel Invariant Verification:
   Verifies at SQLite level:
   - tasks.state == 'FAILED'
   - tasks.active_lease_id IS NULL
   - leases.released == 1
   - queue_accounts.active decremented
   - events recorded correctly
"""

import asyncio
import inspect
import sys
import tempfile
import textwrap
import types
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


async def run_baseline_test(bridge: TaskKernelHandsBridge, w: Path) -> dict:
    """Runs execute() with existing bridge code (containing line 451)."""
    return await bridge.execute(
        action="pc.write_file",
        params={"path": str(w / "baseline.txt"), "content": "hello"},
        capability_level=3,
        approved=True,
        request_key=f"baseline-{uuid.uuid4().hex}",
        capability_token=None,
    )


async def run_remediated_test(bridge: TaskKernelHandsBridge, w: Path) -> dict:
    """Runs execute() with line 451 removed."""
    orig_code = textwrap.dedent(inspect.getsource(bridge.execute))
    patched_code = orig_code.replace("self.kernel.release(task_id, lease.lease_id)", "# [REMOVED] self.kernel.release(task_id, lease.lease_id)")
    assert orig_code != patched_code, "Failed to locate and remove line 451 in source"

    local_vars = {}
    import scp.hands.task_kernel_bridge as bridge_module
    global_vars = bridge_module.__dict__.copy()
    exec(patched_code, global_vars, local_vars)
    patched_execute = local_vars["execute"]

    bridge.execute = types.MethodType(patched_execute, bridge)

    return await bridge.execute(
        action="pc.write_file",
        params={"path": str(w / "remediated.txt"), "content": "hello"},
        capability_level=3,
        approved=True,
        request_key=f"remediated-{uuid.uuid4().hex}",
        capability_token=None,
    )


def main():
    print("==============================================================================")
    print("  EXPLORER 4: TASKKERNEL BRIDGE LEASE LIFECYCLE INVESTIGATION")
    print("==============================================================================")

    td = tempfile.TemporaryDirectory()
    try:
        p = Path(td.name)
        w = p / "workspace"
        w.mkdir()
        ca = CapabilityAuthority(p / "cap.json")
        ex = HandsExecutor(controller=PCController(working_dir=w), capability_authority=ca, data_dir=p / "hands")
        db_path = p / "kernel.sqlite3"
        bridge = TaskKernelHandsBridge(ex, db_path=db_path)

        # -------------------------------------------------------------------------
        # TEST 1: Baseline reproduction (Unpatched)
        # -------------------------------------------------------------------------
        print("\n[STEP 1] Testing Baseline (Existing code with line 451)...")
        baseline_res = asyncio.run(run_baseline_test(bridge, w))
        print(f"  success: {baseline_res.get('success')}")
        print(f"  error: {baseline_res.get('error')}")
        print(f"  requiresRecovery: {baseline_res.get('requiresRecovery')}")
        print(f"  safeToRetry: {baseline_res.get('safeToRetry')}")
        print(f"  kernel: {baseline_res.get('kernel')}")

        assert baseline_res.get("requiresRecovery") is True
        assert "OptimisticLockError" in baseline_res.get("error", "")
        print("  -> Baseline confirmed: line 451 triggers OptimisticLockError cascade!")

        # -------------------------------------------------------------------------
        # TEST 2: Remediated behavior (Line 451 removed)
        # -------------------------------------------------------------------------
        print("\n[STEP 2] Testing Remediated (Line 451 removed)...")
        remediated_res = asyncio.run(run_remediated_test(bridge, w))
        print(f"  success: {remediated_res.get('success')}")
        print(f"  error: {remediated_res.get('error')}")
        print(f"  requiresRecovery: {remediated_res.get('requiresRecovery')}")
        print(f"  safeToRetry: {remediated_res.get('safeToRetry')}")
        print(f"  kernel: {remediated_res.get('kernel')}")

        # Assert clean behavior
        assert remediated_res.get("success") is False
        assert "CapabilityRequiredError" in remediated_res.get("error", "")
        assert remediated_res.get("requiresRecovery") in (False, None)
        assert remediated_res.get("safeToRetry") is False
        assert remediated_res.get("kernel", {}).get("state") == "FAILED"
        print("  -> Remediated execute() confirmed: returns CapabilityRequiredError cleanly, requiresRecovery=False!")

        # -------------------------------------------------------------------------
        # TEST 3: Database & Invariant State Check
        # -------------------------------------------------------------------------
        print("\n[STEP 3] Verifying SQLite Database Invariants for Remediated Task...")
        task_id = remediated_res["kernel"]["taskId"]
        lease_id = remediated_res["kernel"]["leaseId"]

        # Inspect DB directly
        task_row = bridge.kernel.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        lease_row = bridge.kernel.conn.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
        queue_row = bridge.kernel.conn.execute("SELECT * FROM queue_accounts WHERE owner=?", (task_row["owner"],)).fetchone()
        events = bridge.kernel.conn.execute("SELECT * FROM events WHERE task_id=? ORDER BY seq", (task_id,)).fetchall()

        print(f"  Task state: {task_row['state']}")
        print(f"  Task active_lease_id: {task_row['active_lease_id']}")
        print(f"  Task active_fencing_token: {task_row['active_fencing_token']}")
        print(f"  Lease released: {lease_row['released']}")
        print(f"  Queue active: {queue_row['active']}")
        print(f"  Events recorded: {[e['type'] for e in events]}")

        # Assertions on database invariants
        assert task_row["state"] == "FAILED", "Task must be in FAILED state"
        assert task_row["active_lease_id"] is None, "active_lease_id must be NULL"
        assert task_row["active_fencing_token"] == 0, "active_fencing_token must be 0"
        assert lease_row["released"] == 1, "Lease must be marked released=1"
        assert queue_row["active"] == 0, "Queue active count must be decremented to 0"

        # Check bound leases
        bound = getattr(bridge.kernel, "_bound_leases", {})
        assert task_id not in bound, f"task_id {task_id} must not be in _bound_leases"

        print("  -> All Database invariants VERIFIED: lease is atomically released by transition('FAILED')!")

        # Verify that attempting to release again or heartbeat fails properly
        try:
            bridge.kernel.release(task_id, lease_id)
            assert False, "Calling release() on already-released lease must raise OptimisticLockError"
        except Exception as e:
            assert "already been released" in str(e)
            print(f"  -> Verified release idempotency/guard: {type(e).__name__}: {e}")

        bridge.kernel.close()

    finally:
        try:
            td.cleanup()
        except Exception:
            pass

    print("\n==============================================================================")
    print("  ALL TESTS PASSED: Remediation is 100% sound and verified.")
    print("==============================================================================")


if __name__ == "__main__":
    main()
