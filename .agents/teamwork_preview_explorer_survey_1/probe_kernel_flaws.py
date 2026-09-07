"""
Probe Script for Task Kernel Concurrency, Locking, and Durability Flaws (FA-09).
Demonstrates reproducible vulnerabilities in TaskKernel:
1. In-Memory Lease Context Bypass (Rogue Worker Hijacking an active running leased task).
2. Expired Lease Bypass via Fresh Context (Unfenced Transition on Expired Task).
3. Multi-Process Contention Crash (OperationalError: database is locked after 300ms timeout).
4. Blind Version Increment (Missing Optimistic Lock Precondition WHERE version=?).
"""
import multiprocessing
import os
import sys
import tempfile
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scp.task_kernel import TaskKernel, InvalidTransition, StaleLease, KernelError


def test_flaw_1_rogue_worker_hijack():
    print("=" * 70)
    print("PROBE 1: Rogue Worker Hijack via In-Memory _LEASE_CONTEXT Bypass")
    print("=" * 70)
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kernel.sqlite3"
        worker_a = TaskKernel(db_path)
        worker_a.create_task("task-omega-1", "service_A", "critical database migration", "R2")
        for s in ("PLANNING", "READY", "QUEUED"):
            worker_a.transition("task-omega-1", s)
        lease_a = worker_a.claim("task-omega-1", "worker_legitimate", ttl_seconds=300)
        worker_a.start("task-omega-1", lease_a.lease_id)
        print(f"[Worker A] Claimed lease {lease_a.lease_id} (token={lease_a.fencing_token}).")
        print(f"[Worker A] Current task state: {worker_a.get_task('task-omega-1')['state']}")

        # Rogue Worker B opens the same SQLite file
        worker_b = TaskKernel(db_path)
        print("[Worker B] Connected to same database without lease.")
        # Worker B attempts to hijack state to HUMAN_REVIEW
        try:
            worker_b.transition("task-omega-1", "HUMAN_REVIEW", actor="rogue_unleased_actor")
            print(f"[Worker B HIJACK SUCCESS - FLAW NOT FIXED] State: {worker_b.get_task('task-omega-1')['state']}")
        except StaleLease as exc:
            print(f"[Worker B BLOCKED BY INV-01] StaleLease: {exc}")

        # Legitimate Worker A now proceeds with verification
        try:
            worker_a.transition("task-omega-1", "VERIFYING", actor="worker_legitimate")
            print(f"[Worker A SUCCESS] Legitimate worker transitioned to: {worker_a.get_task('task-omega-1')['state']}")
        except Exception as exc:
            print(f"[Worker A FAILED] {type(exc).__name__}: {exc}")

        worker_a.close()
        worker_b.close()


def test_flaw_2_expired_lease_bypass():
    print("\n" + "=" * 70)
    print("PROBE 2: Expired Lease Bypass via Fresh Context (Unfenced Transition)")
    print("=" * 70)
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kernel.sqlite3"
        k1 = TaskKernel(db_path)
        k1.create_task("task-omega-2", "service_B", "financial transaction", "R3")
        for s in ("PLANNING", "READY", "QUEUED"):
            k1.transition("task-omega-2", s)
        lease = k1.claim("task-omega-2", "worker_short", ttl_seconds=1.0)
        k1.start("task-omega-2", lease.lease_id)
        print(f"[k1] Task started with 1.0s TTL lease (token={lease.fencing_token}).")

        time.sleep(1.2)
        print("[k1] 1.2 seconds elapsed. Lease has expired on wall-clock.")

        # In k1 (where lease is bound), transition is blocked:
        try:
            k1.transition("task-omega-2", "VERIFYING")
            print("[k1] Unexpectedly succeeded!")
        except StaleLease as exc:
            print(f"[k1 correctly blocked on expired lease] StaleLease: {exc}")

        # Fresh instance k2 attempts unfenced bypass:
        k2 = TaskKernel(db_path)
        try:
            k2.transition("task-omega-2", "VERIFYING", actor="unfenced_bypasser")
            print(f"[k2 BYPASS SUCCESS - FLAW NOT FIXED] Task transitioned to: {k2.get_task('task-omega-2')['state']}")
        except StaleLease as exc:
            print(f"[k2 BLOCKED BY INV-01] StaleLease: {exc}")

        k1.close()
        k2.close()


def _contention_subproc(db_path, name, delay):
    kernel = TaskKernel(db_path)
    try:
        kernel._begin()
        print(f"[{name}] BEGIN IMMEDIATE acquired. Holding for {delay}s...")
        time.sleep(delay)
        kernel._commit()
        print(f"[{name}] COMMIT completed.")
    except Exception as exc:
        print(f"[{name} CRASHED] {type(exc).__name__}: {exc}")
    finally:
        kernel.close()


def test_flaw_3_multiprocess_lockout():
    print("\n" + "=" * 70)
    print("PROBE 3: Multi-Process SQLite BEGIN IMMEDIATE Lockout Contention")
    print("=" * 70)
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kernel.sqlite3"
        init_k = TaskKernel(db_path)
        init_k.close()

        # Proc 1 holds lock for 0.5s (> 0.30s retry budget in SQLiteKernelStorage.begin)
        p1 = multiprocessing.Process(target=_contention_subproc, args=(db_path, "Process-1 (Long TX)", 0.5))
        p2 = multiprocessing.Process(target=_contention_subproc, args=(db_path, "Process-2 (Quick TX)", 0.05))

        p1.start()
        time.sleep(0.08)  # Ensure p1 acquires write lock first
        p2.start()

        p1.join()
        p2.join()


def test_flaw_4_missing_optimistic_version_lock():
    print("\n" + "=" * 70)
    print("PROBE 4: Missing Optimistic Lock (Blind Version Increment Overwrite)")
    print("=" * 70)
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kernel.sqlite3"
        k = TaskKernel(db_path)
        k.create_task("task-omega-4", "service_C", "concurrent mutation", "R1")
        print(f"[Initial] Task created with version={k.get_task('task-omega-4')['version']}")

        # Simulate two concurrent threads/workers that both read the task at version 1:
        # Worker 1 transitions to PLANNING with expected_version=1:
        k.transition("task-omega-4", "PLANNING", actor="worker_1", expected_version=1)
        t_after_1 = k.get_task("task-omega-4")
        print(f"[After Worker 1] State: {t_after_1['state']}, Version: {t_after_1['version']}")

        # Worker 2 attempts to transition using stale expected_version=1:
        try:
            k.transition("task-omega-4", "CANCELLED", actor="worker_2", expected_version=1)
            print(f"[Worker 2 OVERWRITE SUCCESS - FLAW NOT FIXED] Version: {k.get_task('task-omega-4')['version']}")
        except StaleLease as exc:
            print(f"[Worker 2 BLOCKED BY OCC] StaleLease: {exc}")
        k.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    print("STARTING TASK KERNEL CONCURRENCY & DURABILITY PROBE (FA-09)")
    test_flaw_1_rogue_worker_hijack()
    test_flaw_2_expired_lease_bypass()
    test_flaw_3_multiprocess_lockout()
    test_flaw_4_missing_optimistic_version_lock()
    print("\nALL PROBES COMPLETED.")
