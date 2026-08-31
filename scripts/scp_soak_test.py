import random
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.task_kernel import TaskKernel


def run_workload(tid: int, results: dict[int, dict]) -> None:
    db_path = (ROOT / "soak.sqlite3").as_posix()
    script = (
        "from scp.task_kernel import TaskKernel; import time; "
        f"k = TaskKernel('{db_path}'); "
        f"task_id = k.plan('soak-{tid}', []); "
        "k.transition(task_id, 'RUNNING'); time.sleep(0.1); "
        "k.transition(task_id, 'COMPLETED'); k.close()"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            timeout=5,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        results[tid] = {
            "returncode": proc.returncode,
            "stdout": proc.stdout[-1000:],
            "stderr": proc.stderr[-1000:],
        }
    except subprocess.TimeoutExpired as exc:
        results[tid] = {"timeout": True, "error": repr(exc)}
    except Exception as exc:
        results[tid] = {"error": repr(exc)}


def soak_loop(duration_hours: float = 24) -> bool:
    print(f"Starting {duration_hours}h SCP Soak Test...")
    end_time = time.time() + (duration_hours * 3600)

    db_path = ROOT / "soak.sqlite3"
    if db_path.exists():
        db_path.unlink()

    kernel = TaskKernel(db_path)
    total_spawned = 0
    total_failed = 0
    start_time = time.time()

    try:
        while time.time() < end_time:
            batch = random.randint(10, 50)
            batch_results: dict[int, dict] = {}
            threads = []
            batch_ids = []

            for _ in range(batch):
                total_spawned += 1
                tid = total_spawned
                batch_ids.append(tid)
                t = threading.Thread(target=run_workload, args=(tid, batch_results))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            process_failures = []
            journal_failures = []
            for tid in batch_ids:
                process_result = batch_results.get(tid)
                if not process_result or process_result.get("returncode") != 0:
                    process_failures.append((tid, process_result))
                    continue
                try:
                    res = kernel.verify_journal(f"soak-{tid}")
                except Exception as exc:
                    journal_failures.append((tid, f"verify error: {exc!r}"))
                    continue
                if not res.get("hash_chain_valid", False):
                    journal_failures.append((tid, "hash_chain_valid=False"))

            batch_failed = len(process_failures) + len(journal_failures)
            total_failed += batch_failed
            elapsed = time.time() - start_time
            status = "PASS" if batch_failed == 0 else f"FAIL ({batch_failed})"
            print(
                f"Elapsed {elapsed/3600:.4f}h | Spawned: {total_spawned} | "
                f"Batch: {batch} | Ledger/workload check: {status}"
            )
            if process_failures:
                print(f"  process failures: {process_failures[:3]}")
            if journal_failures:
                print(f"  journal failures: {journal_failures[:3]}")

            if batch_failed:
                return False
            time.sleep(1)
    except KeyboardInterrupt:
        print("Soak test interrupted — not a PASS.")
        return False
    finally:
        kernel.close()

    print(f"Soak complete: spawned={total_spawned}, failures={total_failed}")
    return total_spawned > 0 and total_failed == 0


if __name__ == "__main__":
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
    raise SystemExit(0 if soak_loop(duration) else 1)
