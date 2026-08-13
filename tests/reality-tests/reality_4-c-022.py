#!/usr/bin/env python3
"""Reality test for Fix 4-c-022: SA-4 finding corrected as FALSE (R7-2 fix IS real).

DNA #22 (PASS ≠ TRUE, recursion level 3 — the auditor's auditor was wrong)
+ #14 (evidence must match cited file:line) + #26 (reality test — grep the
actual file).

Before fix:
  - dashboard/src/lib/audit-data/self-audit.ts SA-4 reality field said:
    "The `beforeCode` shown in `bugs-critical.ts`... is a fictional paraphrase
    — the real wiring stores the task. The dashboard's central R7-2 narrative
    ('task GC'd → is_tor always False') is unsupported by the code."
  - This claim was itself FALSE: scp/api/_lifespan.py:393-445 actually
    contains `_tor_refresh_tasks: set = set()` + `_tor_refresh_tasks.add(
    _tor_task)` + `task.add_done_callback(_tor_refresh_tasks.discard)` —
    exactly the R7-2 fix shown in bugs-critical.ts afterCode.
  - DNA #22 recursion level 3: R7 (claimed a bug) → R8 SA-4 (claimed the
    fix was fictional) → R20 verifies R8 was wrong.

After fix:
  - SA-4's reality field is updated to record that the finding was FALSE:
    R7-2 fix IS real, verified at scp/api/_lifespan.py:393-445.
  - The dashboard's display of SA-4 is retained for traceability of the
    recursion (R7 → R8 → R20), but the verdict is now CORRECT.

Reality-test checks:
  1. SA-4 entry in self-audit.ts mentions "FALSE" / "incorrect" / "corrected".
  2. SA-4 entry references R7-2 being real (the R7-2 fix IS applied, not
     "fictional" or "unsupported").
  3. SA-4 entry references scp/api/_lifespan.py:393 (or :393-445).
  4. The actual file scp/api/_lifespan.py contains the _tor_refresh_tasks
     pattern (the fix is genuinely present — DNA #26 reality test).

Run:
    python3 tests/reality-tests/reality_4-c-022.py
"""

import re
import sys
from pathlib import Path

SELF_AUDIT_PATH = Path(
    str(Path(__file__).resolve().parents[2]) + '/dashboard/src/lib/audit-data/self-audit.ts'
)
LIFESPAN_PATH = Path(
    str(Path(__file__).resolve().parents[2]) + '/scp/api/_lifespan.py'
)


def main() -> int:
    assert SELF_AUDIT_PATH.exists(), f"FAIL: self-audit.ts not found at {SELF_AUDIT_PATH}"
    sa_src = SELF_AUDIT_PATH.read_text(encoding="utf-8")

    # Find the SA-4 entry (between `id: "SA-4"` and the next `id: "SA-5"` or
    # the closing `]`).
    sa4_start = sa_src.find('"SA-4"')
    if sa4_start == -1:
        sa4_start = sa_src.find("'SA-4'")
    assert sa4_start >= 0, "FAIL: SA-4 entry not found in self-audit.ts"

    # Look ahead 5000 chars for the SA-4 entry body.
    sa4_end = sa_src.find('"SA-5"', sa4_start)
    if sa4_end == -1:
        sa4_end = sa4_start + 5000
    sa4_block = sa_src[sa4_start:sa4_end]

    # -------------------------------------------------------------------------
    # TEST 1 — SA-4 entry mentions FALSE / incorrect / corrected.
    # -------------------------------------------------------------------------
    has_false_marker = (
        "FALSE" in sa4_block.upper()
        or "incorrect" in sa4_block.lower()
        or "corrected" in sa4_block.lower()
        or "CORRECTION" in sa4_block.upper()
    )
    assert has_false_marker, (
        "FAIL: SA-4 entry in self-audit.ts does not mention FALSE / incorrect / "
        "corrected / CORRECTION — the finding has not been flipped to FALSE."
    )
    print("PASS [1/4]: SA-4 entry mentions FALSE / corrected / CORRECTION")

    # -------------------------------------------------------------------------
    # TEST 2 — SA-4 entry references R7-2 being real (the fix IS applied,
    # not "fictional" or "unsupported").
    # -------------------------------------------------------------------------
    # Must contain a phrase indicating R7-2 is real.
    reality_indicators = [
        "R7-2 fix IS real",
        "R7-2 was a real bug",
        "fix IS applied",
        "fix IS present",
        "fix is real",
        "fix was actually applied",
        "R7-2 IS real",
    ]
    has_real_marker = any(ind.lower() in sa4_block.lower() for ind in reality_indicators)
    assert has_real_marker, (
        "FAIL: SA-4 entry does not state that the R7-2 fix IS real/applied. "
        f"Looked for indicators like: {reality_indicators}"
    )
    print("PASS [2/4]: SA-4 entry states R7-2 fix IS real/applied")

    # -------------------------------------------------------------------------
    # TEST 3 — SA-4 entry references scp/api/_lifespan.py:393 (the verified
    # location of the _tor_refresh_tasks fix).
    # -------------------------------------------------------------------------
    has_lifespan_ref = (
        "_lifespan.py:393" in sa4_block
        or "_lifespan.py:180" in sa4_block
        or "scp/api/_lifespan.py" in sa4_block
    )
    assert has_lifespan_ref, (
        "FAIL: SA-4 entry does not reference scp/api/_lifespan.py — the "
        "verified location of the R7-2 fix. Must cite the file:line."
    )
    print("PASS [3/4]: SA-4 entry references scp/api/_lifespan.py (the verified file)")

    # -------------------------------------------------------------------------
    # TEST 4 — REALITY TEST (DNA #26): the actual file scp/api/_lifespan.py
    # contains the _tor_refresh_tasks pattern (the fix is genuinely present).
    # This is the cross-lineage check: the dashboard's claim is verified
    # against the actual Python backend code.
    # -------------------------------------------------------------------------
    assert LIFESPAN_PATH.exists(), (
        f"FAIL: scp/api/_lifespan.py not found at {LIFESPAN_PATH} — cannot "
        "reality-test the SA-4 correction against the actual file."
    )
    lifespan_src = LIFESPAN_PATH.read_text(encoding="utf-8")
    has_tor_refresh_tasks = (
        "_tor_refresh_tasks" in lifespan_src
        or "tor_refresh_tasks" in lifespan_src
    )
    has_add_done_callback = "add_done_callback" in lifespan_src
    assert has_tor_refresh_tasks, (
        "FAIL: scp/api/_lifespan.py does NOT contain `_tor_refresh_tasks` — "
        "the R7-2 fix is NOT present in the actual backend code. The SA-4 "
        "correction (claiming the fix IS real) would itself be FALSE. DNA #22 "
        "recursion level 4 — verify the verifier."
    )
    print("PASS [4/4]: scp/api/_lifespan.py contains _tor_refresh_tasks (fix IS real)")
    if has_add_done_callback:
        print("  (add_done_callback also present — confirms GC-prevention pattern)")

    print("\n✓ Reality test 4-c-022 PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
