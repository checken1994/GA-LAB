from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
TEST_DIR = ROOT / "tests" / "reality-tests"
PYTHON = os.environ.get("SCP_PYTHON_BIN") or sys.executable
if PYTHON.startswith("/c/"):
    PYTHON = "C:" + PYTHON[2:].replace("/", "\\")
results = []
env = os.environ.copy()
env.setdefault("PYTHONUTF8", "1")
env.setdefault("PYTHONIOENCODING", "utf-8")
env.setdefault("SCP_ENV_FILE", str(ROOT / ".env.test"))
env.setdefault("SCP_DEV_MODE", "0")
env.setdefault("SCP_SKIP_STARTUP_GATE", "0")
for test in sorted(TEST_DIR.glob("reality_*.py")):
    started = time.time()
    try:
        proc = subprocess.run(
            [PYTHON, str(test)], cwd=str(ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        status = "PASS" if proc.returncode == 0 else "FAIL"
        results.append({"test": test.name, "status": status, "returncode": proc.returncode,
                        "duration_sec": round(time.time() - started, 2),
                        "output_tail": proc.stdout[-4000:]})
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        results.append({"test": test.name, "status": "TIMEOUT", "returncode": None,
                        "duration_sec": round(time.time() - started, 2),
                        "output_tail": output[-4000:]})
    except Exception as exc:
        results.append({"test": test.name, "status": "ERROR", "returncode": None,
                        "duration_sec": round(time.time() - started, 2),
                        "output_tail": repr(exc)})
    print(f"{results[-1]['status']:7} {test.name} ({results[-1]['duration_sec']}s)", flush=True)
summary = {
    "root": str(ROOT), "python": PYTHON, "test_count": len(results),
    "pass": sum(r["status"] == "PASS" for r in results),
    "fail": sum(r["status"] == "FAIL" for r in results),
    "timeout": sum(r["status"] == "TIMEOUT" for r in results),
    "error": sum(r["status"] == "ERROR" for r in results),
    "results": results,
}
out = ROOT / "reality-tests-results.json"
out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: summary[k] for k in ("test_count", "pass", "fail", "timeout", "error")}, ensure_ascii=False))
raise SystemExit(0 if summary["fail"] == 0 and summary["timeout"] == 0 and summary["error"] == 0 else 1)
