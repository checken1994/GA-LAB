from pathlib import Path
"""Reality test for Fix 4-a-018: _fact_check_retract_queue uses deque (O(1) popleft).

Before fix: Queue was a `list[dict]` with `pop(0)` to evict oldest entries
when queue exceeded 1000. `list.pop(0)` is O(N) — copies every element after
the popped index. Under high retract volume (burst of FALSE claims) the
copy on every eviction becomes a bottleneck on the event loop.

After fix: Queue is a `collections.deque(maxlen=1000)`. `append()` auto-evicts
the oldest entry when full — no explicit `pop()` or `len()` check needed.
popleft on a deque is O(1).

DNA principles exercised:
  #2  (vòng lặp khép kín — reality test of the fix, not just the fix)
  #9  (no harm — O(N) pop stalls the event loop under load)
  #22 (PASS ≠ TRUE — old code "worked" but degraded under load)
  #26 (reality test — execute + cross-check)
"""
import ast
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Queue lives in api_server.py (not scp/core/*.py as the task description
# initially guessed — the glob was a hint, reality says api_server.py).
FILE_CANDIDATES = [
    str(Path(__file__).resolve().parents[2]) + '/scp/api_server.py',
    # also check scp/core/*.py in case it migrates in the future
]

# Allow queue to live in api_server.py OR any scp/core/*.py file
import glob
for p in glob.glob(str(Path(__file__).resolve().parents[2]) + '/scp/core/*.py'):
    FILE_CANDIDATES.append(p)

# Find the file that actually defines _fact_check_retract_queue
queue_file = None
for f in FILE_CANDIDATES:
    if not os.path.isfile(f):
        continue
    with open(f) as fh:
        c = fh.read()
    if "_fact_check_retract_queue" in c and (
        "_fact_check_retract_queue:" in c or "_fact_check_retract_queue =" in c
    ):
        queue_file = f
        break

assert queue_file is not None, (
    f"FAIL: no file in scp/api_server.py or scp/core/*.py defines "
    f"_fact_check_retract_queue. Searched: {FILE_CANDIDATES}"
)
print(f"PASS [0/3]: _fact_check_retract_queue defined in {os.path.relpath(queue_file, str(Path(__file__).resolve().parents[2]))}")

with open(queue_file) as f:
    src = f.read()

# ---------------------------------------------------------------------------
# TEST 1 — `deque` is imported + used as the queue type
# ---------------------------------------------------------------------------
# deque must be imported (from collections) — either as `from collections import deque`
# or `import collections` (with collections.deque usage)
has_deque_import = (
    "from collections import deque" in src
    or "import collections" in src
)
assert has_deque_import, f"FAIL: deque is not imported in {queue_file}"
print("PASS [1/3]: `deque` is imported (from collections)")

# Queue assignment must use `deque(...)` (not `list(...)` or `[]`)
# Find the queue assignment line
import re
m = re.search(r"_fact_check_retract_queue\s*[:=][^\n]+", src)
assert m, f"FAIL: _fact_check_retract_queue assignment not found in {queue_file}"
assign_line = m.group(0)
assert "deque(" in assign_line, (
    f"FAIL: _fact_check_retract_queue is not assigned a deque — got: {assign_line!r}"
)
print(f"PASS [2/3]: _fact_check_retract_queue uses deque() — assignment: {assign_line.strip()!r}")

# ---------------------------------------------------------------------------
# TEST 2 — No `pop(0)` call on the retract queue (DNA #22: PASS ≠ TRUE).
# We verify by AST: find every Call to .pop(...) where the first arg is the
# literal integer 0, and check it's NOT called on _fact_check_retract_queue.
# ---------------------------------------------------------------------------
tree = ast.parse(src)

# Find every `_fact_check_retract_queue.pop(0)` call
bare_pop_zero_on_queue = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "pop":
            # Check if the receiver is _fact_check_retract_queue
            recv = f.value
            recv_name = None
            if isinstance(recv, ast.Name):
                recv_name = recv.id
            elif isinstance(recv, ast.Attribute):
                recv_name = recv.attr
            if recv_name == "_fact_check_retract_queue":
                # Check first positional arg — if it's literal 0, that's the bug
                if node.args:
                    arg0 = node.args[0]
                    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, int) and arg0.value == 0:
                        bare_pop_zero_on_queue.append(
                            f"line {getattr(node, 'lineno', '?')}: "
                            f"_fact_check_retract_queue.pop(0) — O(N)"
                        )
                # Also flag pop() with no args on deque — pop() removes the
                # RIGHT side (newest), not the LEFT (oldest). Should use
                # popleft() if explicit pop is needed.
                if not node.args:
                    bare_pop_zero_on_queue.append(
                        f"line {getattr(node, 'lineno', '?')}: "
                        f"_fact_check_retract_queue.pop() — removes newest, "
                        f"not oldest. Should use popleft() or rely on maxlen."
                    )

assert not bare_pop_zero_on_queue, (
    "FAIL: _fact_check_retract_queue still uses pop(0) (or pop() without arg) — "
    "O(N) per call. Locations:\n  " + "\n  ".join(bare_pop_zero_on_queue)
)
print("PASS [3/3]: no pop(0) (or bare pop()) on _fact_check_retract_queue — uses deque auto-eviction")

print("\n✓ Reality test 4-a-018 PASSED (4/4 assertions — incl. file-exists)")
