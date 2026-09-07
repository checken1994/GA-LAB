"""
Empirical verification and adversarial stress test for TaskKernel concurrency flaws.
Tests:
1. Multi-process lock contention with synchronized barrier/event: Does SQLiteKernelStorage.begin() crash with OperationalError?
2. Multi-thread Rogue Worker hijack: Does threading bypass _LEASE_CONTEXT?
3. Multi-process Rogue Worker hijack: Does a separate process bypass _LEASE_CONTEXT?
4. Expired lease bypass via separate process.
5. Missing optimistic lock: Race condition causing lost update / phantom transition under concurrent execution.
"""
import multiprocessing
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

# Add project root
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scp.task_kernel import TaskKernel, InvalidTransition, StaleLease, KernelError
from scp.kernel_storage import SQLiteKernelStorage, StorageIntegrityError


def proc_hold_lock(db_path, start_event, acquired_event, hold_time):
    k = TaskKernel(db_path)
    start_event.wait()
    try:
        k._begin()
        acquired_event.set()
        time.sleep(hold_time)
        k._commit()
    finally:
        k.close()


def proc_attempt_lock(db_path, acquired_event, result_queue):
    k = TaskKernel(db_path)
    acquired_event.wait()
    # Small delay to ensure proc_hold_lock is definitely inside its sleep
    time.sleep(0.05)
    try:
        t0 = time.time()
        k._begin()
        duration = time.time() - t0
        k._commit()
        result_queue.put(("SUCCESS", duration))
    except Exception as exc:
        result_queue.put(("EXCEPTION", type(exc).__name__, str(exc)))
    finally:
        k.close()


def test_multiprocess_lock_contention():
    print("\n--- TEST 1: Synchronized Multi-Process Lock Contention ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kernel.sqlite3"
        init_k = TaskKernel(db_path)
        init_k.close()

        start_event = multiprocessing.Event()
        acquired_event = multiprocessing.Event()
        result_queue = multiprocessing.Queue()

        # Process 1 will hold lock for 1.0s (> 0.3s retry budget in SQLiteKernelStorage.begin)
        p1 = multiprocessing.Process(
            target=proc_hold_lock, args=(db_path, start_event, acquired_event, 1.0)
        )
        p2 = multiprocessing.Process(
            target=proc_attempt_lock, args=(db_path, acquired_event, result_queue)
        )

        p1.start()
        p2.start()

        time.sleep(0.2)
        start_event.set()

        p1.join(timeout=5)
        p2.join(timeout=5)

        if not result_queue.empty():
            res = result_queue.get()
            print(f"Result from competing process: {res}")
            return res
        else:
            print("Result queue empty (process timed out or died)")
            return ("TIMEOUT",)


def test_multithread_lease_context_bypass():
    print("\n--- TEST 2: Multi-Thread Rogue Worker Hijack (Same TaskKernel Object) ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kernel.sqlite3"
        kernel = TaskKernel(db_path)
        kernel.create_task("task-thread-1", "service_A", "spec", "R2")
        for s in ("PLANNING", "READY", "QUEUED"):
            kernel.transition("task-thread-1", s)
        lease = kernel.claim("task-thread-1", "worker_legit", ttl_seconds=300)
        kernel.start("task-thread-1", lease.lease_id)
        print(f"Legitimate worker started task in MainThread: state={kernel.get_task('task-thread-1')['state']}")

        # Now spawn a worker thread that shares the SAME kernel instance:
        def rogue_thread():
            try:
                kernel.transition("task-thread-1", "HUMAN_REVIEW", actor="rogue_thread")
                print("Rogue thread successfully hijacked task to HUMAN_REVIEW!")
            except Exception as exc:
                print(f"Rogue thread blocked with {type(exc).__name__}: {exc}")

        t = threading.Thread(target=rogue_thread)
        t.start()
        t.join()

        final_state = kernel.get_task("task-thread-1")["state"]
        print(f"Task state after rogue thread: {final_state}")

        # Try to transition from main thread (which had the lease)
        try:
            kernel.transition("task-thread-1", "VERIFYING", actor="worker_legit")
            print("Main thread transition unexpectedly succeeded!")
        except InvalidTransition as exc:
            print(f"Main thread crashed: {exc}")
        kernel.close()


def proc_rogue_worker(db_path, task_id, res_queue):
    kernel = TaskKernel(db_path)
    try:
        kernel.transition(task_id, "HUMAN_REVIEW", actor="rogue_subproc")
        res_queue.put(("SUCCESS", kernel.get_task(task_id)["state"]))
    except Exception as exc:
        res_queue.put(("EXCEPTION", type(exc).__name__, str(exc)))
    finally:
        kernel.close()


def test_multiprocess_rogue_worker():
    print("\n--- TEST 3: Multi-Process Rogue Worker Hijack ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kernel.sqlite3"
        kernel = TaskKernel(db_path)
        kernel.create_task("task-mp-1", "service_A", "spec", "R2")
        for s in ("PLANNING", "READY", "QUEUED"):
            kernel.transition("task-mp-1", s)
        lease = kernel.claim("task-mp-1", "worker_proc1", ttl_seconds=300)
        kernel.start("task-mp-1", lease.lease_id)
        print(f"Proc1 started task: state={kernel.get_task('task-mp-1')['state']}")

        res_q = multiprocessing.Queue()
        p = multiprocessing.Process(target=proc_rogue_worker, args=(db_path, "task-mp-1", res_q))
        p.start()
        p.join(timeout=5)

        res = res_q.get()
        print(f"Proc2 rogue transition result: {res}")

        try:
            kernel.transition("task-mp-1", "VERIFYING", actor="worker_proc1")
            print("Proc1 unexpectedly succeeded!")
        except InvalidTransition as exc:
            print(f"Proc1 legitimate worker crashed: {exc}")
        kernel.close()


def test_concurrent_occ_race():
    print("\n--- TEST 4: Concurrent OCC Lost Update Race ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kernel.sqlite3"
        kernel = TaskKernel(db_path)
        kernel.create_task("task-occ-1", "service_X", "concurrent OCC test", "R1")
        # task is in CREATED (version 1)
        # Allowed transitions from CREATED: PLANNING, CANCELLED

        def worker_plan(k_inst, barrier, res):
            barrier.wait()
            try:
                k_inst.transition("task-occ-1", "PLANNING", actor="planner")
                res.append(("PLANNING_SUCCESS", k_inst.get_task("task-occ-1")["version"]))
            except Exception as e:
                res.append(("PLANNING_FAIL", type(e).__name__, str(e)))

        def worker_cancel(k_inst, barrier, res):
            barrier.wait()
            try:
                k_inst.transition("task-occ-1", "CANCELLED", actor="canceller")
                res.append(("CANCEL_SUCCESS", k_inst.get_task("task-occ-1")["version"]))
            except Exception as e:
                res.append(("CANCEL_FAIL", type(e).__name__, str(e)))

        k1 = TaskKernel(db_path)
        k2 = TaskKernel(db_path)
        barrier = threading.Barrier(2)
        res1, res2 = [], []

        t1 = threading.Thread(target=worker_plan, args=(k1, barrier, res1))
        t2 = threading.Thread(target=worker_cancel, args=(k2, barrier, res2))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        print(f"Worker 1 result: {res1}")
        print(f"Worker 2 result: {res2}")
        final_task = kernel.get_task("task-occ-1")
        print(f"Final task state: {final_task['state']}, version={final_task['version']}")

        events = kernel.conn.execute("SELECT * FROM events WHERE task_id='task-occ-1' ORDER BY seq ASC").fetchall()
        print(f"Event journal count: {len(events)}")
        for ev in events:
            print(f"  Seq {ev['seq']}: {ev['from_state']} -> {ev['to_state']} by {ev['actor']}")

        k1.close()
        k2.close()
        kernel.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    print("RUNNING EMPIRICAL STRESS TESTS")
    test_multiprocess_lock_contention()
    test_multithread_lease_context_bypass()
    test_multiprocess_rogue_worker()
    test_concurrent_occ_race()
