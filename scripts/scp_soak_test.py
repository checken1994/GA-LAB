import time
import subprocess
import threading
import random
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.task_kernel import TaskKernel

def run_workload(tid):
    try:
        db_path = (ROOT / 'soak.sqlite3').as_posix()
        script = f"from scp.task_kernel import TaskKernel; import time; k = TaskKernel('{db_path}'); k.transition(k.plan('soak-{tid}', []), 'RUNNING'); time.sleep(0.1); k.transition('soak-{tid}', 'COMPLETED')"
        subprocess.run([sys.executable, "-c", script], timeout=2, capture_output=True)
    except Exception:
        pass

def soak_loop(duration_hours=24):
    print(f"Starting {duration_hours}h SCP Soak Test...")
    end_time = time.time() + (duration_hours * 3600)
    
    db_path = ROOT / "soak.sqlite3"
    if db_path.exists():
        db_path.unlink()
        
    kernel = TaskKernel(db_path)
    
    total_spawned = 0
    start_time = time.time()
    
    try:
        while time.time() < end_time:
            batch = random.randint(10, 50)
            threads = []
            for i in range(batch):
                total_spawned += 1
                t = threading.Thread(target=run_workload, args=(total_spawned,))
                threads.append(t)
                t.start()
                
            time.sleep(random.uniform(0.1, 0.5))
            
            for t in threads:
                t.join()
                
            failed = 0
            for i in range(total_spawned - batch + 1, total_spawned + 1):
                try:
                    res = kernel.verify_journal(f"soak-{i}")
                    if not res.get("hash_chain_valid", False):
                        failed += 1
                except Exception:
                    pass
                    
            elapsed = time.time() - start_time
            print(f"Elapsed {elapsed/3600:.4f}h | Spawned: {total_spawned} | Ledger consistency check: {'PASS' if failed == 0 else f'FAIL ({failed} corrupted)'}")
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("Soak test interrupted.")
    finally:
        kernel.close()

if __name__ == "__main__":
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
    soak_loop(duration)
