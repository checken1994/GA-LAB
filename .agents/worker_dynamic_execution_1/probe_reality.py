import sys
sys.path.insert(0, ".")
import tempfile
from pathlib import Path
from scp.autofix.runner_phases.reality_test import run_reality_test

with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    
    # Case 1: Empty file / constants only
    f1 = p / "empty.py"
    f1.write_text("# Just comments\nX = 42\n", encoding="utf-8")
    r1 = run_reality_test(file_path=str(f1))
    print("Case 1 (No callables):", r1["status"], "reason:", r1["reason"])
    
    # Case 2: Only failing callable
    f2 = p / "failing.py"
    f2.write_text("def bad_func():\n    raise ValueError('boom')\n", encoding="utf-8")
    r2 = run_reality_test(file_path=str(f2))
    print("Case 2 (All raise):", r2["status"], "reason:", r2["reason"], "exceptions:", len(r2.get("exceptions", [])))
    
    # Case 3: 1 good, 1 bad
    f3 = p / "partial.py"
    f3.write_text("def good_func():\n    return True\ndef bad_func():\n    raise RuntimeError('fail')\n", encoding="utf-8")
    r3 = run_reality_test(file_path=str(f3))
    print("Case 3 (Partial):", r3["status"], "reason:", r3["reason"], "exercised:", r3.get("callables_exercised"), "exceptions:", len(r3.get("exceptions", [])))
    
    # Case 4: sys.exit attempt
    f4 = p / "sysexit.py"
    f4.write_text("import sys\ndef killer():\n    sys.exit(42)\n", encoding="utf-8")
    r4 = run_reality_test(file_path=str(f4))
    print("Case 4 (SysExit):", r4["status"], "reason:", r4["reason"], "exceptions:", len(r4.get("exceptions", [])))
    
    # Case 5: Async callable
    f5 = p / "async_code.py"
    f5.write_text("async def async_hello():\n    return 'ok'\n", encoding="utf-8")
    r5 = run_reality_test(file_path=str(f5))
    print("Case 5 (Async):", r5["status"], "reason:", r5["reason"], "exercised:", r5.get("callables_exercised"))

    # Case 6: Top-level crash
    f6 = p / "top_level_crash.py"
    f6.write_text("raise RuntimeError('top level explosion')\n", encoding="utf-8")
    r6 = run_reality_test(file_path=str(f6))
    print("Case 6 (Top level crash):", r6["status"], "reason:", r6["reason"])
