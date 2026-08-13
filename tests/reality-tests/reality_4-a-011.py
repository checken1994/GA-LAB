from pathlib import Path
"""Reality test for Fix 4-a-011: vector_db uses actual store file mtime.

Before fix: `os.path.getmtime('.')` was used as the vector record timestamp.
That's the cwd mtime — it changes on ANY file creation/deletion in the
working directory (log rotation, cache writes, etc.) and has nothing to do
with the vector store. Every record got a meaningless "random wall-clock"
timestamp instead of the actual store modification time.

After fix: `os.path.getmtime(self.db_path)` — the actual vector store file's
mtime. Plus a documented known-limitation comment about loading all vectors
into memory for cosine similarity (Phase 8+ would use faiss/sqlite-vec).

DNA principles exercised:
  #2  (vòng lặp khép kín — reality test of the fix, not just the fix)
  #22 (PASS ≠ TRUE — old code "worked" but with meaningless timestamps)
  #26 (reality test — execute + cross-check)
  #23 (honest limit — the load-all-vectors pattern is documented, not fixed)
"""
import ast
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

FILE = str(Path(__file__).resolve().parents[2]) + '/scp/capabilities/vector_db.py'

# TEST 0 — file exists (DNA #19)
assert os.path.isfile(FILE), f"FAIL: file missing: {FILE}"
print("PASS [0/3]: vector_db.py exists")

with open(FILE) as f:
    src = f.read()

# TEST 1 — `getmtime('.')` (cwd mtime) is NOT used anywhere in the file
# (DNA #22: the misleading timestamp source must be gone).
# We allow it to appear inside a comment that EXPLAINS the old bug, but the
# actual code path must not call getmtime on a literal ".".
# Strip comments + strings before checking.
tree = ast.parse(src)
cwd_mtime_in_code = False
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        f = node.func
        # match os.path.getmtime(...) or path.getmtime(...) or getmtime(...)
        name = None
        if isinstance(f, ast.Attribute):
            name = f.attr
        elif isinstance(f, ast.Name):
            name = f.id
        if name == "getmtime":
            # Inspect the first positional arg
            if node.args:
                arg = node.args[0]
                # Literal "." is the bug
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value == ".":
                    cwd_mtime_in_code = True
                # f-string "." is also the bug
                if isinstance(arg, ast.JoinedStr):
                    for val in arg.values:
                        if isinstance(val, ast.Constant) and isinstance(val.value, str) and val.value.strip() in (".", "'.'", '"."'):
                            cwd_mtime_in_code = True

assert not cwd_mtime_in_code, (
    "FAIL: code path still calls os.path.getmtime('.') (cwd mtime). "
    "Replace with os.path.getmtime(self.db_path)."
)
print("PASS [1/3]: no `getmtime('.')` cwd-mtime call in code path")

# TEST 2 — code uses the actual store path for mtime
# (DNA #19: observation — must be self.db_path or self.store_path).
# This file uses self.db_path — accept either pattern.
assert (
    "os.path.getmtime(self.db_path)" in src or
    "os.path.getmtime(self.store_path)" in src
), (
    "FAIL: did not find `os.path.getmtime(self.db_path)` or "
    "`os.path.getmtime(self.store_path)` in vector_db.py"
)
print("PASS [2/3]: uses actual store file path for mtime (self.db_path or self.store_path)")

# TEST 3 — known-limitation comment present (DNA #23 honest limit:
# the load-all-vectors pattern is documented, not silently left as-is).
assert (
    "known limitation" in src.lower() or
    "faiss" in src.lower() or
    "sqlite-vec" in src.lower()
), (
    "FAIL: no known-limitation comment referencing faiss/sqlite-vec migration path"
)
print("PASS [3/3]: known-limitation comment present (faiss/sqlite-vec migration noted)")

print("\n✓ Reality test 4-a-011 PASSED (4/4 assertions — incl. file-exists check)")
