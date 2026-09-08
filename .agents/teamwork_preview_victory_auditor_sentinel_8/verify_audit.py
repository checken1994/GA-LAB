import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tempfile
import os
import time
import sqlite3

# Ensure fallback test secret exists for capability token validation
if not os.environ.get("SCP_CAPABILITY_SECRET"):
    os.environ["SCP_CAPABILITY_SECRET"] = "gap13-audit-cryptographic-secret-32b-ok!"

from scp.task_kernel import TaskKernel, InvalidTransition, OptimisticLockError
from scp.core.capability_token import (
    CapabilityToken,
    compute_token_signature,
    get_capability_secret,
    InvalidTokenSignatureError,
)

def run_physical_audit():
    tmp_fd, db_path = tempfile.mkstemp(suffix="_audit_sqlite.db")
    os.close(tmp_fd)
    try:
        kernel = TaskKernel(db_path)
        task_id = "auditor-task-1"
        kernel.create_task(task_id, "auditor", "test audit", "R3")
        kernel.transition(task_id, "PLANNING")
        kernel.transition(task_id, "WAITING_APPROVAL")
        print("[1] Task in WAITING_APPROVAL created and gated.")

        # Test 1: Direct unauthenticated transition blocked
        try:
            kernel.transition(task_id, "READY")
            raise AssertionError("FAIL: Direct transition should have raised InvalidTransition!")
        except InvalidTransition as e:
            print("[2] PASS: Direct transition blocked:", e)

        # Test 2: Forged token blocked
        forged = CapabilityToken("approval:grant", 0, "tok-forged", time.time(), "0" * 64)
        try:
            kernel.commit_approval(task_id, forged, actor="attacker")
            raise AssertionError("FAIL: Forged token should have raised InvalidTokenSignatureError!")
        except InvalidTokenSignatureError as e:
            print("[3] PASS: Forged token blocked:", e)

        # Test 3: Verify physical SQLite state unchanged
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        assert row["state"] == "WAITING_APPROVAL"
        assert row["version"] == 3
        print("[4] PASS: Physical SQLite row unchanged: WAITING_APPROVAL, version=3")

        # Test 4: OCC version conflict check
        secret = get_capability_secret()
        now_ts = time.time()
        sig = compute_token_signature(secret, "approval:grant", 0, "tok-legit", now_ts)
        valid_token = CapabilityToken("approval:grant", 0, "tok-legit", now_ts, sig)

        try:
            kernel.commit_approval(task_id, valid_token, actor="approver", expected_version=99)
            raise AssertionError("FAIL: Stale version should have raised OptimisticLockError!")
        except OptimisticLockError as e:
            print("[5] PASS: OCC mismatch blocked:", e)

        # Test 5: Legitimate approval commit
        res = kernel.commit_approval(task_id, valid_token, actor="approver", expected_version=3)
        assert res["state"] == "READY"
        assert res["version"] == 4

        # Test 6: Verify physical SQLite state and event journal
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        assert row["state"] == "READY"
        assert row["version"] == 4

        evt = conn.execute("SELECT * FROM events WHERE task_id=? AND type='TASK_APPROVED'", (task_id,)).fetchone()
        assert evt is not None
        assert evt["from_state"] == "WAITING_APPROVAL"
        assert evt["to_state"] == "READY"
        print("[6] PASS: Physical SQLite verified: state=READY, version=4, event=TASK_APPROVED logged")

        conn.close()
        kernel.close()
        print("\nALL DIRECT PHYSICAL SQLITE AUDIT CHECKS PASSED.")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

if __name__ == "__main__":
    run_physical_audit()
