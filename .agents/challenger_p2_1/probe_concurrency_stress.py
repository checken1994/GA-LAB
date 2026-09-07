"""
Independent Concurrency Stress & OCC Adversarial Probe
======================================================
Author: Challenger P2-1 (Empirical Challenger)
Milestone: M5 (Adversarial Review & Concurrency Gate)

Mandates:
- FA-08: Real terminal execution only (no forged logs).
- FA-09: Exploit & concurrency stress testing with empirical assertions.
- INV-01: Atomic OCC fencing across all satellite tables. Every update must condition on version
  and raise OptimisticLockError on conflict.
"""

from __future__ import annotations

import concurrent.futures
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scp.task_kernel import (
    KernelError,
    OptimisticLockError,
    StaleLease,
    TaskKernel,
    now_iso,
)


def _setup_task(kernel: TaskKernel, task_id: str, worker_id: str = "worker-main"):
    kernel.create_task(task_id, "stress-service", "concurrency stress test", "R1")
    for s in ("PLANNING", "READY", "QUEUED"):
        kernel.transition(task_id, s, actor="stress-setup")
    lease = kernel.claim(task_id, worker_id, ttl_seconds=300)
    kernel.start(task_id, lease.lease_id)
    return lease


def test_vector1_idempotency_api_occ():
    """Vector 1: Verify TaskKernel idempotency API raises OptimisticLockError on stale completion."""
    print("  [Stress Test 1] Testing Idempotency API OCC fencing...")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_kernel.sqlite3"
        kernel = TaskKernel(db_path)
        task_id = "task-v1"
        lease = _setup_task(kernel, task_id, "worker-1")

        key, claimed = kernel.idempotency_claim(task_id, "step-1", "write_file", "doc.txt")
        assert claimed is True
        status_init = kernel.idempotency_status(key)
        assert status_init["version"] == 1
        assert status_init["status"] == "CLAIMED"

        # Worker 1 completes key at version 1
        kernel.idempotency_complete(key, "evidence://worker-1-result", expected_version=1)
        status_after_w1 = kernel.idempotency_status(key)
        assert status_after_w1["status"] == "COMPLETED"
        assert status_after_w1["version"] == 2
        assert status_after_w1["result_ref"] == "evidence://worker-1-result"

        # Stale Worker 2 attempts completion with expected_version=1 -> MUST raise OptimisticLockError
        occ_caught = False
        try:
            kernel.idempotency_complete(key, "evidence://stale-w2-corrupt", expected_version=1)
        except OptimisticLockError as exc:
            occ_caught = True
            assert exc.table == "idempotency"
            assert exc.entity_id == key
            assert exc.expected_version == 1
        except Exception as exc:
            raise AssertionError(f"Expected OptimisticLockError, got {type(exc).__name__}: {exc}")

        assert occ_caught is True, "CRITICAL: Stale idempotency completion did NOT raise OptimisticLockError!"

        # Ensure DB content was not corrupted
        status_final = kernel.idempotency_status(key)
        assert status_final["result_ref"] == "evidence://worker-1-result"
        assert status_final["version"] == 2
        kernel.close()
    print("  [Stress Test 1] PASS: Idempotency OCC fencing verified.")


def test_vector2_lease_heartbeat_and_release_api_occ():
    """Vector 2: Verify TaskKernel Lease heartbeat and release fail-closed with OptimisticLockError."""
    print("  [Stress Test 2] Testing Lease Heartbeat & Release API OCC fencing...")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_kernel.sqlite3"
        kernel = TaskKernel(db_path)
        task_id = "task-v2"
        lease = _setup_task(kernel, task_id, "worker-1")
        lease_id = lease.lease_id

        # 1. Stale heartbeat with wrong version
        occ_caught = False
        try:
            kernel.heartbeat(task_id, lease_id, expected_version=99)
        except OptimisticLockError as exc:
            occ_caught = True
            assert exc.table == "leases"
            assert exc.entity_id == lease_id
            assert exc.expected_version == 99

        assert occ_caught is True, "Stale heartbeat did not raise OptimisticLockError on version mismatch!"

        # 2. Watchdog releases lease
        kernel.release(task_id, lease_id, expected_version=1)

        # 3. Late heartbeat on released lease must raise OptimisticLockError
        occ_caught_released = False
        try:
            kernel.heartbeat(task_id, lease_id)
        except OptimisticLockError as exc:
            occ_caught_released = True
            assert exc.table == "leases"
            assert exc.entity_id == lease_id

        assert occ_caught_released is True, "Heartbeat on released lease did not raise OptimisticLockError!"
        kernel.close()
    print("  [Stress Test 2] PASS: Lease Heartbeat & Release OCC fencing verified.")


def test_vector3_multi_threaded_idempotency_race():
    """Vector 3: 20 concurrent threads racing to complete the same idempotency key with expected_version=1."""
    print("  [Stress Test 3] Running 20-thread concurrency race on Idempotency completion...")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_kernel.sqlite3"
        main_kernel = TaskKernel(db_path)
        task_id = "task-race-idem"
        lease = _setup_task(main_kernel, task_id, "worker-leader")

        key, claimed = main_kernel.idempotency_claim(task_id, "step-race", "api_call", "endpoint_data")
        assert claimed is True
        assert main_kernel.idempotency_status(key)["version"] == 1

        barrier = threading.Barrier(20)
        results = []
        errors = []

        def worker_task(thread_id: int):
            # Each thread opens its own kernel instance on the shared WAL database
            k = TaskKernel(db_path)
            k._bound_leases[task_id] = lease.lease_id
            barrier.wait()  # synchronize release of all threads simultaneously
            try:
                k.idempotency_complete(
                    key,
                    f"evidence://thread-{thread_id}-result",
                    expected_version=1,
                )
                results.append(thread_id)
            except OptimisticLockError as exc:
                errors.append((thread_id, exc))
            except Exception as exc:
                errors.append((thread_id, exc))
            finally:
                k.close()

        threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        print(f"  [Stress Test 3] Results: {len(results)} winner(s), {len(errors)} OptimisticLockError(s)")
        assert len(results) == 1, f"Expected exactly 1 winner, but got {len(results)}: {results}"
        assert len(errors) == 19, f"Expected exactly 19 errors, but got {len(errors)}"
        for tid, err in errors:
            assert isinstance(err, OptimisticLockError), f"Thread {tid} raised unexpected error: {type(err)}: {err}"
            assert err.table == "idempotency"
            assert err.expected_version == 1

        # Check final DB state
        final_row = main_kernel.idempotency_status(key)
        assert final_row["status"] == "COMPLETED"
        assert final_row["version"] == 2
        assert final_row["result_ref"] == f"evidence://thread-{results[0]}-result"
        main_kernel.close()
    print("  [Stress Test 3] PASS: Exactly 1 winner in 20-thread race; 19 failed-closed with OptimisticLockError.")


def test_vector4_multi_threaded_retryable_claim_race():
    """Vector 4: 20 concurrent threads racing to re-claim a RETRYABLE idempotency key."""
    print("  [Stress Test 4] Running 20-thread concurrency race on RETRYABLE claim...")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_kernel.sqlite3"
        main_kernel = TaskKernel(db_path)
        task_id = "task-race-retry"
        lease = _setup_task(main_kernel, task_id, "worker-leader")

        key, claimed = main_kernel.idempotency_claim(task_id, "step-retry", "api_call", "endpoint_data")
        assert claimed is True

        # Manually transition to RETRYABLE at version 1
        main_kernel.conn.execute("UPDATE idempotency SET status='RETRYABLE', version=1 WHERE logical_key=?", (key,))
        assert main_kernel.idempotency_status(key)["status"] == "RETRYABLE"
        assert main_kernel.idempotency_status(key)["version"] == 1

        barrier = threading.Barrier(20)
        claims = []
        errors = []

        def worker_claim(thread_id: int):
            k = TaskKernel(db_path)
            k._bound_leases[task_id] = lease.lease_id
            barrier.wait()
            try:
                _, was_claimed = k.idempotency_claim(
                    task_id, "step-retry", "api_call", "endpoint_data", expected_version=1
                )
                if was_claimed:
                    claims.append(thread_id)
            except OptimisticLockError as exc:
                errors.append((thread_id, exc))
            except Exception as exc:
                errors.append((thread_id, exc))
            finally:
                k.close()

        threads = [threading.Thread(target=worker_claim, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        print(f"  [Stress Test 4] Claims: {len(claims)} claim(s), {len(errors)} OptimisticLockError(s)")
        assert len(claims) == 1, f"Expected exactly 1 claim winner, got {len(claims)}: {claims}"
        assert len(errors) == 19, f"Expected 19 OptimisticLockError, got {len(errors)}"
        for tid, err in errors:
            assert isinstance(err, OptimisticLockError)

        final_row = main_kernel.idempotency_status(key)
        assert final_row["status"] == "CLAIMED"
        assert final_row["version"] == 2
        main_kernel.close()
    print("  [Stress Test 4] PASS: Exactly 1 claimer in 20-thread race; 19 failed-closed with OptimisticLockError.")


def test_vector5_multi_threaded_lease_release_race():
    """Vector 5: 10 concurrent threads racing to release the same lease."""
    print("  [Stress Test 5] Running 10-thread concurrency race on Lease release...")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_kernel.sqlite3"
        main_kernel = TaskKernel(db_path)
        task_id = "task-race-release"
        lease = _setup_task(main_kernel, task_id, "worker-leader")
        lease_id = lease.lease_id

        barrier = threading.Barrier(10)
        releases = []
        errors = []

        def worker_release(thread_id: int):
            k = TaskKernel(db_path)
            k._bound_leases[task_id] = lease_id
            barrier.wait()
            try:
                k.release(task_id, lease_id, expected_version=1)
                releases.append(thread_id)
            except (OptimisticLockError, StaleLease) as exc:
                errors.append((thread_id, exc))
            except Exception as exc:
                errors.append((thread_id, exc))
            finally:
                k.close()

        threads = [threading.Thread(target=worker_release, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        print(f"  [Stress Test 5] Releases: {len(releases)} winner(s), {len(errors)} conflict error(s)")
        assert len(releases) == 1, f"Expected exactly 1 release winner, got {len(releases)}: {releases}"
        assert len(errors) == 9, f"Expected 9 conflict errors, got {len(errors)}"
        for tid, err in errors:
            assert isinstance(err, (OptimisticLockError, StaleLease))

        row = main_kernel.conn.execute("SELECT version, released FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
        assert row["released"] == 1
        assert row["version"] == 2
        main_kernel.close()
    print("  [Stress Test 5] PASS: Exactly 1 release winner; 9 failed-closed.")


def test_vector6_concurrent_heartbeat_and_expire_race():
    """Vector 6: Worker heartbeats racing against system expire_leases."""
    print("  [Stress Test 6] Running race between Lease Heartbeat and expire_leases...")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_kernel.sqlite3"
        main_kernel = TaskKernel(db_path)
        task_id = "task-race-expire"
        lease = _setup_task(main_kernel, task_id, "worker-leader")
        lease_id = lease.lease_id

        # Set lease to expire in the past
        past_time = time.time() - 10.0
        main_kernel.conn.execute(
            "UPDATE leases SET expires_at=?, version=1 WHERE lease_id=?",
            (past_time, lease_id),
        )

        barrier = threading.Barrier(2)
        events = []

        def worker_heartbeat():
            k = TaskKernel(db_path)
            k._bound_leases[task_id] = lease_id
            barrier.wait()
            try:
                k.heartbeat(task_id, lease_id, expected_version=1)
                events.append("heartbeat_won")
            except OptimisticLockError:
                events.append("heartbeat_rejected_occ")
            except StaleLease:
                events.append("heartbeat_rejected_stale")
            finally:
                k.close()

        def system_expirer():
            k = TaskKernel(db_path)
            k._system_authority = True
            barrier.wait()
            expired = k.expire_leases(now=time.time())
            if lease_id in expired:
                events.append("expire_won")
            else:
                events.append("expire_missed")
            k.close()

        t1 = threading.Thread(target=worker_heartbeat)
        t2 = threading.Thread(target=system_expirer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        print(f"  [Stress Test 6] Events observed: {events}")
        # One of two valid atomic outcomes must occur:
        # Either heartbeat won before expire, or expire won and heartbeat was rejected
        assert ("heartbeat_won" in events and "expire_missed" in events) or \
               ("expire_won" in events and ("heartbeat_rejected_occ" in events or "heartbeat_rejected_stale" in events))

        # Check DB consistency
        row = main_kernel.conn.execute("SELECT version, released FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
        assert row["version"] >= 2
        main_kernel.close()
    print("  [Stress Test 6] PASS: Atomic resolution between heartbeat and expiry verified.")


if __name__ == "__main__":
    print("=" * 80)
    print("ADVERSARIAL CONCURRENCY & STRESS PROBE — CHALLENGER P2-1")
    print("=" * 80)
    tests = [
        test_vector1_idempotency_api_occ,
        test_vector2_lease_heartbeat_and_release_api_occ,
        test_vector3_multi_threaded_idempotency_race,
        test_vector4_multi_threaded_retryable_claim_race,
        test_vector5_multi_threaded_lease_release_race,
        test_vector6_concurrent_heartbeat_and_expire_race,
    ]

    for test_fn in tests:
        test_fn()

    print("\n" + "=" * 80)
    print("ALL 6 ADVERSARIAL CONCURRENCY & OCC STRESS PROBES PASSED CLEANLY.")
    print("=" * 80)
