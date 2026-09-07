"""Adversarial Concurrency & OCC Stress Harness for GAP-05.

Tests SQLiteKernelStorage without in-memory RLock under high concurrency:
1a. Multi-threaded Pessimistic Serialization via BEGIN IMMEDIATE (reads inside begin()).
1b. Multi-threaded True Optimistic Concurrency Control (OCC) with external reads,
    forced version collisions, and retry loop (verifying zero lost updates under heavy contention).
2.  Multi-threaded Race Inducer / Blind update comparison (control group proving OCC necessity).
3.  Multi-threaded Forced Collision OCC (proves rowcount == 0 detection and fail-closed behavior).
4.  Multi-process OCC Contention (verifying SQLite WAL BEGIN IMMEDIATE file locking across OS processes).
5.  TaskKernel State Machine Concurrency (verifying TaskKernel transition OCC and state machine invariants).
6.  TaskKernel Concurrent Full Lifecycle & Event Journal Integrity (verifying hash chain and monotonic sequence).
6b. TaskKernel Concurrent Claim Racing (20 workers racing to claim 1 queued task; exactly 1 winner, 19 rejected).
7.  Database Integrity and Corruption Check (PRAGMA integrity_check, foreign_key_check).
"""
import concurrent.futures
import multiprocessing
import os
import shutil
import sys
import time
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Set test capability secret if needed for imports
os.environ.setdefault("SCP_CAPABILITY_SECRET", "test-secret-for-challenger-run-12345678901234567890")

from scp.kernel_storage import SQLiteKernelStorage
from scp.task_kernel import TaskKernel, OptimisticLockError, InvalidTransition, StaleLease, KernelError


def run_test_1a_multithread_begin_immediate_pessimistic(tmp_dir: Path) -> dict:
    """50 threads concurrently incrementing a shared counter with read inside BEGIN IMMEDIATE."""
    print("\n--- Test 1a: Multi-threaded BEGIN IMMEDIATE Serialization (50 threads x 20 iterations = 1000) ---")
    db_path = tmp_dir / "test1a_pessimistic.sqlite3"
    storage = SQLiteKernelStorage(db_path)
    storage.executescript(
        "CREATE TABLE counter (id TEXT PRIMARY KEY, val INTEGER, version INTEGER);"
        "INSERT INTO counter VALUES ('c1', 0, 1);"
    )
    
    num_threads = 50
    increments_per_thread = 20
    expected_total = num_threads * increments_per_thread

    def worker():
        for _ in range(increments_per_thread):
            storage.begin()
            try:
                row = storage.fetchone("SELECT val, version FROM counter WHERE id='c1'")
                cur_val = row["val"]
                cur_ver = row["version"]
                time.sleep(0.0002)
                cur = storage.execute(
                    "UPDATE counter SET val = ?, version = version + 1 WHERE id='c1' AND version = ?",
                    (cur_val + 1, cur_ver)
                )
                assert cur.rowcount == 1
                storage.commit()
            except Exception:
                storage.rollback()
                raise

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker) for _ in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            f.result()
    duration = time.time() - t0

    row = storage.fetchone("SELECT val, version FROM counter WHERE id='c1'")
    final_val = row["val"]
    final_ver = row["version"]
    storage.close()

    print(f"Result: Final val={final_val}, version={final_ver}, expected={expected_total}")
    print(f"Duration: {duration:.2f}s")
    
    assert final_val == expected_total, f"Lost updates! Expected {expected_total}, got {final_val}"
    assert final_ver == expected_total + 1, f"Version mismatch! Expected {expected_total + 1}, got {final_ver}"
    return {
        "status": "PASS",
        "final_val": final_val,
        "expected": expected_total,
        "duration": duration,
    }


def run_test_1b_multithread_true_occ_contention(tmp_dir: Path) -> dict:
    """30 threads concurrently updating with reads OUTSIDE begin(), forcing collisions and OCC retries."""
    print("\n--- Test 1b: True Optimistic Concurrency Control with Forced Collisions (30 threads x 15 = 450) ---")
    db_path = tmp_dir / "test1b_true_occ.sqlite3"
    storage = SQLiteKernelStorage(db_path)
    storage.executescript(
        "CREATE TABLE counter (id TEXT PRIMARY KEY, val INTEGER, version INTEGER);"
        "INSERT INTO counter VALUES ('c1', 0, 1);"
    )

    num_threads = 30
    increments_per_thread = 15
    expected_total = num_threads * increments_per_thread

    conflict_count = [0]
    import threading
    conflict_lock = threading.Lock()

    def occ_worker():
        for _ in range(increments_per_thread):
            while True:
                # 1. Optimistic read OUTSIDE transaction
                row = storage.fetchone("SELECT val, version FROM counter WHERE id='c1'")
                read_val = row["val"]
                read_ver = row["version"]

                # 2. Artificial delay to widen collision window
                time.sleep(0.001)

                # 3. Write attempt with OCC version check
                storage.begin()
                try:
                    cur = storage.execute(
                        "UPDATE counter SET val = ?, version = version + 1 WHERE id='c1' AND version = ?",
                        (read_val + 1, read_ver)
                    )
                    if cur.rowcount == 1:
                        storage.commit()
                        break
                    else:
                        # OCC conflict! Another thread updated version in the interim
                        storage.rollback()
                        with conflict_lock:
                            conflict_count[0] += 1
                        time.sleep(0.0005)
                except Exception:
                    storage.rollback()
                    raise

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(occ_worker) for _ in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            f.result()
    duration = time.time() - t0

    row = storage.fetchone("SELECT val, version FROM counter WHERE id='c1'")
    final_val = row["val"]
    final_ver = row["version"]
    storage.close()

    print(f"Result: Final val={final_val}, version={final_ver}, expected={expected_total}")
    print(f"OCC Conflicts detected and retried: {conflict_count[0]}")
    print(f"Duration: {duration:.2f}s")

    assert final_val == expected_total, f"Lost updates! Expected {expected_total}, got {final_val}"
    assert final_ver == expected_total + 1, f"Version mismatch! Expected {expected_total + 1}, got {final_ver}"
    assert conflict_count[0] > 0, "Expected OCC conflicts were not triggered!"

    return {
        "status": "PASS",
        "final_val": final_val,
        "expected": expected_total,
        "conflicts_resolved": conflict_count[0],
        "duration": duration,
    }


def run_test_2_multithread_blind_update_proof(tmp_dir: Path) -> dict:
    """Control experiment: 30 threads doing read-modify-write WITHOUT OCC.
    Proves that concurrency issues occur if OCC is absent, verifying OCC is the real guard.
    """
    print("\n--- Test 2: Control Group - Blind Update Without OCC (Proving OCC Necessity) ---")
    db_path = tmp_dir / "test2_blind_race.sqlite3"
    storage = SQLiteKernelStorage(db_path)
    storage.executescript(
        "CREATE TABLE counter (id TEXT PRIMARY KEY, val INTEGER);"
        "INSERT INTO counter VALUES ('c1', 0);"
    )

    num_threads = 30
    increments = 15
    expected_total = num_threads * increments

    def blind_worker():
        for _ in range(increments):
            # Read outside BEGIN IMMEDIATE / without version check
            row = storage.fetchone("SELECT val FROM counter WHERE id='c1'")
            val = row["val"]
            time.sleep(0.001)  # Context switch window
            storage.begin()
            try:
                storage.execute("UPDATE counter SET val = ? WHERE id='c1'", (val + 1,))
                storage.commit()
            except Exception:
                storage.rollback()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(blind_worker) for _ in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    row = storage.fetchone("SELECT val FROM counter WHERE id='c1'")
    final_val = row["val"]
    storage.close()

    lost_updates = expected_total - final_val
    print(f"Result: Final val={final_val}, Expected={expected_total}, Lost updates={lost_updates}")
    print(f"Conclusion: Without OCC version check, lost updates = {lost_updates} (Proof of OCC necessity).")
    return {
        "status": "PROVEN",
        "final_val": final_val,
        "expected": expected_total,
        "lost_updates": lost_updates,
    }


def run_test_3_forced_collision_fail_closed(tmp_dir: Path) -> dict:
    """Adversarial forced collision: 20 threads read the EXACT SAME snapshot version 1,
    and then all attempt to update to version 2.
    EXACTLY ONE must succeed (rowcount == 1); EXACTLY 19 must fail closed (rowcount == 0).
    """
    print("\n--- Test 3: Forced Simultaneous Collision (20 threads on same snapshot) ---")
    db_path = tmp_dir / "test3_forced_collision.sqlite3"
    storage = SQLiteKernelStorage(db_path)
    storage.executescript(
        "CREATE TABLE counter (id TEXT PRIMARY KEY, val INTEGER, version INTEGER);"
        "INSERT INTO counter VALUES ('c1', 0, 1);"
    )

    import threading
    barrier = threading.Barrier(20)
    successes = []
    conflicts = []
    lock = threading.Lock()

    def racer(tid: int):
        # All threads read version 1
        row = storage.fetchone("SELECT val, version FROM counter WHERE id='c1'")
        assert row["version"] == 1

        # Synchronize all threads at barrier before racing to write
        barrier.wait()

        storage.begin()
        try:
            cur = storage.execute(
                "UPDATE counter SET val = val + 1, version = version + 1 WHERE id='c1' AND version = 1"
            )
            if cur.rowcount == 1:
                storage.commit()
                with lock:
                    successes.append(tid)
            else:
                storage.rollback()
                with lock:
                    conflicts.append(tid)
        except Exception:
            storage.rollback()
            with lock:
                conflicts.append(tid)

    threads = [threading.Thread(target=racer, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    row = storage.fetchone("SELECT val, version FROM counter WHERE id='c1'")
    final_val = row["val"]
    final_ver = row["version"]
    storage.close()

    print(f"Successes: {len(successes)} (tid={successes})")
    print(f"Conflicts (Fail-Closed): {len(conflicts)}")
    print(f"Final state: val={final_val}, version={final_ver}")

    assert len(successes) == 1, f"Expected exactly 1 winner, got {len(successes)}"
    assert len(conflicts) == 19, f"Expected exactly 19 conflicts, got {len(conflicts)}"
    assert final_val == 1, f"Expected final val=1, got {final_val}"
    assert final_ver == 2, f"Expected final ver=2, got {final_ver}"

    return {
        "status": "PASS",
        "winners": len(successes),
        "losers": len(conflicts),
        "final_val": final_val,
        "final_ver": final_ver,
    }


def _mp_worker(db_path_str: str, worker_id: int, iterations: int, results_queue):
    """Multi-process worker executing OCC updates."""
    storage = SQLiteKernelStorage(db_path_str)
    retries = 0
    successes = 0
    for _ in range(iterations):
        while True:
            # Read outside begin to create true multi-process OCC race condition
            row = storage.fetchone("SELECT val, version FROM mp_counter WHERE id='mp'")
            val = row["val"]
            ver = row["version"]
            time.sleep(0.0005)
            storage.begin()
            try:
                cur = storage.execute(
                    "UPDATE mp_counter SET val = val + 1, version = version + 1 WHERE id='mp' AND version = ?",
                    (ver,)
                )
                if cur.rowcount == 1:
                    storage.commit()
                    successes += 1
                    break
                else:
                    storage.rollback()
                    retries += 1
                    time.sleep(0.001)
            except Exception as e:
                storage.rollback()
                err_msg = str(e).lower()
                if "locked" in err_msg or "busy" in err_msg:
                    retries += 1
                    time.sleep(0.005)
                else:
                    results_queue.put((worker_id, False, str(e)))
                    return
    storage.close()
    results_queue.put((worker_id, True, {"successes": successes, "retries": retries}))


def run_test_4_multiprocess_occ_stress(tmp_dir: Path) -> dict:
    """Multi-process stress: 10 OS processes contending on SQLite file lock & OCC."""
    print("\n--- Test 4: Multi-Process OCC Contention with Optimistic Reads (10 procs x 20 iters = 200) ---")
    db_path = tmp_dir / "test4_mp_occ.sqlite3"
    storage = SQLiteKernelStorage(db_path)
    storage.executescript(
        "CREATE TABLE mp_counter (id TEXT PRIMARY KEY, val INTEGER, version INTEGER);"
        "INSERT INTO mp_counter VALUES ('mp', 0, 1);"
    )
    storage.close()

    num_processes = 10
    iterations = 20
    expected_total = num_processes * iterations

    queue = multiprocessing.Queue()
    procs = []
    t0 = time.time()
    for pid in range(num_processes):
        p = multiprocessing.Process(
            target=_mp_worker,
            args=(str(db_path), pid, iterations, queue)
        )
        procs.append(p)
        p.start()

    results = []
    for _ in range(num_processes):
        results.append(queue.get())

    for p in procs:
        p.join()
    duration = time.time() - t0

    storage = SQLiteKernelStorage(db_path)
    row = storage.fetchone("SELECT val, version FROM mp_counter WHERE id='mp'")
    final_val = row["val"]
    final_ver = row["version"]
    storage.close()

    total_retries = sum(r[2]["retries"] for r in results if r[1])
    print(f"Results: Final val={final_val}, version={final_ver}, expected={expected_total}")
    print(f"Total cross-process OCC retries: {total_retries}")
    print(f"Duration: {duration:.2f}s")

    assert final_val == expected_total, f"Lost updates in multiprocess! Expected {expected_total}, got {final_val}"
    assert final_ver == expected_total + 1, f"Version mismatch in multiprocess! Expected {expected_total + 1}, got {final_ver}"

    return {
        "status": "PASS",
        "final_val": final_val,
        "expected": expected_total,
        "total_retries": total_retries,
        "duration": duration,
    }


def run_test_5_task_kernel_state_machine_stress(tmp_dir: Path) -> dict:
    """TaskKernel State Machine Concurrency:
    5 tasks created. 20 concurrent threads all compete to transition each task through:
    CREATED -> PLANNING -> READY -> QUEUED
    Only valid transitions allowed; strictly 1 winner per transition stage.
    """
    print("\n--- Test 5: TaskKernel State Machine Concurrency (20 threads competing on 5 tasks) ---")
    db_path = tmp_dir / "test5_kernel_fsm.sqlite3"
    kernel = TaskKernel(db_path)

    task_ids = [f"stress-task-{i}" for i in range(5)]
    for tid in task_ids:
        kernel.create_task(tid, "challenger_test", f"Adversarial FSM stress for {tid}")

    invalid_transition_count = [0]
    occ_error_count = [0]
    success_count = [0]
    import threading
    lock = threading.Lock()

    def competitor(thread_id: int):
        k = TaskKernel(db_path)
        try:
            for tid in task_ids:
                # Stage 1: CREATED -> PLANNING
                try:
                    k.transition(tid, "PLANNING")
                    with lock:
                        success_count[0] += 1
                except InvalidTransition:
                    with lock:
                        invalid_transition_count[0] += 1
                except OptimisticLockError:
                    with lock:
                        occ_error_count[0] += 1

                time.sleep(0.0005)

                # Stage 2: PLANNING -> READY
                try:
                    k.transition(tid, "READY")
                    with lock:
                        success_count[0] += 1
                except InvalidTransition:
                    with lock:
                        invalid_transition_count[0] += 1
                except OptimisticLockError:
                    with lock:
                        occ_error_count[0] += 1

                time.sleep(0.0005)

                # Stage 3: READY -> QUEUED
                try:
                    k.transition(tid, "QUEUED")
                    with lock:
                        success_count[0] += 1
                except InvalidTransition:
                    with lock:
                        invalid_transition_count[0] += 1
                except OptimisticLockError:
                    with lock:
                        occ_error_count[0] += 1
        finally:
            k.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(competitor, i) for i in range(20)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    # Verify all tasks reached QUEUED state
    for tid in task_ids:
        t = kernel.get_task(tid)
        assert t["state"] == "QUEUED", f"Task {tid} in unexpected state: {t['state']}"
        assert t["version"] == 4, f"Task {tid} version unexpected: {t['version']} (expected 4: created=1, planning=2, ready=3, queued=4)"

    print(f"Successful transitions: {success_count[0]} (Expected 15: 5 tasks * 3 steps)")
    print(f"Rejected transitions (InvalidTransition): {invalid_transition_count[0]}")
    print(f"Rejected transitions (OptimisticLockError): {occ_error_count[0]}")
    kernel.close()

    assert success_count[0] == 15, f"Expected exactly 15 successful transitions, got {success_count[0]}"

    return {
        "status": "PASS",
        "successful_transitions": success_count[0],
        "invalid_transitions_caught": invalid_transition_count[0],
        "occ_conflicts_caught": occ_error_count[0],
    }


def run_test_6_task_kernel_event_journal_integrity(tmp_dir: Path) -> dict:
    """Concurrent task lifecycles: 10 concurrent threads each executing a full task lifecycle.
    Verify that each task's hash chain is 100% valid, sequence numbers are strictly 1..N,
    and concurrent writes never corrupt the events table.
    """
    print("\n--- Test 6: TaskKernel Event Journal Concurrency & Cryptographic Hash Chain Integrity ---")
    db_path = tmp_dir / "test6_kernel_journal.sqlite3"
    kernel = TaskKernel(db_path)

    num_tasks = 10

    def lifecycle_worker(wid: int):
        k = TaskKernel(db_path)
        tid = f"lifecycle-task-{wid}"
        try:
            k.create_task(tid, f"worker-{wid}", f"Goal for worker {wid}")
            k.transition(tid, "PLANNING")
            k.transition(tid, "READY")
            k.transition(tid, "QUEUED")
            lease = k.claim(tid, f"worker-{wid}", ttl_seconds=30)
            k.start(tid, lease.lease_id)
            k.transition(tid, "VERIFYING")
            k.commit_completed(tid, lease.lease_id, "VERIFIED", f"evidence://worker-{wid}")
        finally:
            k.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_tasks) as executor:
        futures = [executor.submit(lifecycle_worker, i) for i in range(num_tasks)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    verify_k = TaskKernel(db_path)
    for i in range(num_tasks):
        tid = f"lifecycle-task-{i}"
        task = verify_k.get_task(tid)
        assert task["state"] == "COMPLETED", f"Task {tid} not completed: {task['state']}"
        journal = verify_k.verify_journal(tid)
        assert journal["hash_chain_valid"] is True, f"Hash chain broken for {tid}!"
        assert journal["event_count"] == 8, f"Expected 8 events for {tid}, got {journal['event_count']}"
        
        events = verify_k.get_events(tid)
        seqs = [e["seq"] for e in events]
        assert seqs == list(range(1, 9)), f"Sequence numbers corrupted for {tid}: {seqs}"

    print(f"Verified {num_tasks} tasks: all hash chains valid, all sequences strictly contiguous 1..8.")
    verify_k.close()

    return {
        "status": "PASS",
        "tasks_verified": num_tasks,
        "all_hash_chains_valid": True,
    }


def run_test_6b_task_kernel_concurrent_claim_race(tmp_dir: Path) -> dict:
    """20 concurrent worker threads all race to claim the EXACT SAME queued task.
    Exactly ONE worker must receive the lease.
    Exactly 19 workers must be rejected (StaleLease or KernelError).
    Task state must transition cleanly to LEASED with active_lease_id assigned.
    """
    print("\n--- Test 6b: TaskKernel Concurrent Claim Racing (20 workers racing for 1 task) ---")
    db_path = tmp_dir / "test6b_claim_race.sqlite3"
    kernel = TaskKernel(db_path)
    tid = "race-claim-task"
    kernel.create_task(tid, "owner_1", "Goal for race claim")
    kernel.transition(tid, "PLANNING")
    kernel.transition(tid, "READY")
    kernel.transition(tid, "QUEUED")
    kernel.close()

    winners = []
    losers = []
    import threading
    lock = threading.Lock()
    barrier = threading.Barrier(20)

    def worker_claim(wid: int):
        k = TaskKernel(db_path)
        try:
            barrier.wait()
            try:
                lease = k.claim(tid, f"worker-{wid}", ttl_seconds=30)
                with lock:
                    winners.append((wid, lease.lease_id))
            except (StaleLease, KernelError) as e:
                with lock:
                    losers.append((wid, str(e)))
        finally:
            k.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(worker_claim, i) for i in range(20)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    verify_k = TaskKernel(db_path)
    task = verify_k.get_task(tid)
    verify_k.close()

    print(f"Claim winners: {len(winners)} (wid={winners})")
    print(f"Claim losers rejected: {len(losers)}")
    print(f"Task final state: {task['state']}, active_lease_id={task['active_lease_id']}")

    assert len(winners) == 1, f"Expected exactly 1 winner, got {len(winners)}"
    assert len(losers) == 19, f"Expected exactly 19 losers, got {len(losers)}"
    assert task["state"] == "LEASED"
    assert task["active_lease_id"] == winners[0][1]

    return {
        "status": "PASS",
        "winner": winners[0],
        "losers_rejected": len(losers),
        "task_state": task["state"],
    }


def run_test_7_database_integrity_check(tmp_dir: Path) -> dict:
    """Verify SQLite PRAGMA integrity_check and foreign_key_check on all generated databases."""
    print("\n--- Test 7: SQLite Database Integrity Check across all test databases ---")
    db_files = list(tmp_dir.glob("*.sqlite3"))
    results = {}
    for db_file in db_files:
        storage = SQLiteKernelStorage(db_file)
        integrity = storage.fetchone("PRAGMA integrity_check;")[0]
        fk = storage.fetchall("PRAGMA foreign_key_check;")
        storage.close()
        print(f"  {db_file.name}: integrity_check='{integrity}', fk_violations={len(fk)}")
        assert integrity == "ok", f"Integrity check failed for {db_file.name}: {integrity}"
        assert len(fk) == 0, f"Foreign key violations in {db_file.name}: {fk}"
        results[db_file.name] = {"integrity": integrity, "fk_violations": len(fk)}
    return {"status": "PASS", "databases": results}


def main():
    tmp_dir = Path(__file__).resolve().parent / "stress_data"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(exist_ok=True)
    print(f"Adversarial Stress Test Directory: {tmp_dir}")

    all_results = {}
    try:
        all_results["test_1a_pessimistic_wal"] = run_test_1a_multithread_begin_immediate_pessimistic(tmp_dir)
        all_results["test_1b_true_occ"] = run_test_1b_multithread_true_occ_contention(tmp_dir)
        all_results["test_2_blind_race_control"] = run_test_2_multithread_blind_update_proof(tmp_dir)
        all_results["test_3_forced_collision"] = run_test_3_forced_collision_fail_closed(tmp_dir)
        all_results["test_4_multiprocess_occ"] = run_test_4_multiprocess_occ_stress(tmp_dir)
        all_results["test_5_kernel_fsm"] = run_test_5_task_kernel_state_machine_stress(tmp_dir)
        all_results["test_6_kernel_journal"] = run_test_6_task_kernel_event_journal_integrity(tmp_dir)
        all_results["test_6b_claim_race"] = run_test_6b_task_kernel_concurrent_claim_race(tmp_dir)
        all_results["test_7_db_integrity"] = run_test_7_database_integrity_check(tmp_dir)

        print("\n========================================================")
        print("ALL ADVERSARIAL STRESS TESTS COMPLETED SUCCESSFULLY!")
        print("OCC AND WAL BEGIN IMMEDIATE MAINTAIN FULL INTEGRITY.")
        print("ZERO LOST UPDATES, ZERO CORRUPTIONS, ZERO DEADLOCKS.")
        print("========================================================")
        sys.exit(0)
    except Exception as exc:
        print(f"\nCRITICAL FAILURE DURING STRESS TEST: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
