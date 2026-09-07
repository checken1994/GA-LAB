# Adversarial Review & Quality Assurance Handoff: GAP-03 & GAP-04 Remediation (Round 1)

> [!WARNING] **Skepticism Disclaimer**
> Moderate confidence: All 4 subtests of the FA-09 exploit probe and all 438 pytest regression tests pass with 0 meta-audit violations, but high-concurrency multi-process SQLite WAL contention remains fundamentally bounded by SQLite's single-writer lock serialized under 25 retries (~5s timeout).

---

## Execution Context & Environment Metadata
- **HEAD_SHA:** `6070050bdba94b90d8d0d22bbeff7d8e488cd000`
- **TREE_HASH:** `d344024e9214f473787e7cd2085523d761e66dd0`
- **WORKTREE:** `C:/Users/check/Downloads/scp`
- **Python Version:** `Python 3.12.10`
- **SQLite Version:** `3.49.1`
- **Reviewer Directory:** `c:\Users\check\Downloads\scp\.agents\teamwork_preview_reviewer_r1`

---

## 1. What the Prior Attempt Got Wrong

The prior attempt implemented the core SQL `WHERE task_id=? AND version=?` check and wrapped `rebuild_projection()` in `self._begin()`/`self._commit()`. However, an adversarial review uncovered **5 critical flaws and test weaknesses**:

### Issue 1: Fake Concurrency in Probe Script Subtest 2
- **Input**: Running `probe_gap03_04_blind_overwrite.py` Subtest 2 claiming to prove "hai luồng có thể ghi đè nhau".
- **Expected**: Two concurrent OS threads running in parallel (`threading.Thread` with barrier synchronization) to empirically prove that concurrent execution on the same base version violates OCC on buggy code and is protected on remediated code.
- **Actual**: Subtest 2 ran Worker A followed by Worker B sequentially within the exact same single main thread. It never spawned any threads!
- **Root Cause**: The author implemented sequential calls and mislabeled it as a "concurrent race condition", violating FA-09 Exploit Mandate ("Chứng minh hai luồng có thể ghi đè nhau").

### Issue 2: Purely Static AST Inspection for Transaction Boundary (GAP-04)
- **Input**: Running Subtest 3 of `probe_gap03_04_blind_overwrite.py`.
- **Expected**: Runtime verification that operations within `rebuild_projection()` (journal verification, event fetching, task reading, OCC update) run inside an atomic transaction that rolls back cleanly on any failure without leaking locks or partial writes.
- **Actual**: Subtest 3 only performed static source text string matching (`inspect.getsource(rebuild_projection)`) to check line numbers. Per `scp-reality-verifier`, Level A Static inspection cannot prove runtime behavior or rollback safety.
- **Root Cause**: The author relied solely on `inspect.getsource()` line indexing rather than executing an actual runtime transaction failure/rollback scenario.

### Issue 3: Missing Adversarial Coverage for Cross-Method OCC Races (`transition()` vs `rebuild_projection()`)
- **Input**: Racing `transition(task_id, "READY", expected_version=v)` and `rebuild_projection(task_id, expected_version=v)` across parallel threads.
- **Expected**: Exactly one winner succeeds and increments version to `v+1`, while the loser is rejected with `OptimisticLockError`.
- **Actual**: Completely untested in the test suite (admitted in prior report's Open Issues Ledger: "Interleaving transition() and rebuild_projection() calls on the same task ID across racing threads").
- **Root Cause**: The author only tested `rebuild_projection()` racing against another `rebuild_projection()`, omitting cross-method race interactions with `transition()`.

### Issue 4: Missing High-Concurrency Contention Proof (>2 parallel threads)
- **Input**: 10 parallel threads simultaneously contending on `rebuild_projection(task_id, expected_version=v)` with a 10-party synchronization barrier.
- **Expected**: Exactly 1 thread succeeds (version increments by 1), exactly 9 threads raise `OptimisticLockError`, zero deadlocks, zero lock exhaustion.
- **Actual**: Untested by prior attempt (admitted in prior report's Open Issues Ledger: "High concurrency stress (>50 parallel threads)").
- **Root Cause**: Only a 2-worker barrier was tested. Under SQLite WAL mode, multi-worker contention can trigger `SQLITE_BUSY` if transaction retry logic or OCC fails.

### Issue 5: Missing Non-Existent Task Rollback & Connection Cleanup
- **Input**: Calling `rebuild_projection("non-existent-task-999")`.
- **Expected**: Raises `NotFound` and immediately rolls back transaction, ensuring connection and storage remain in clean state for subsequent operations without hanging or throwing `OperationalError: cannot start a transaction within a transaction`.
- **Actual**: Untested in `test_rebuild_projection_occ.py`.
- **Root Cause**: Only corrupt journal error path was tested for rollback, omitting non-existent task error path.

---

## 2. What I Changed

### A. `tools/probes/probe_gap03_04_blind_overwrite.py`
1. **Subtest 2 Upgraded to Real Parallel Concurrency**:
   - Refactored `test_gap03_concurrent_clobber_reproduction` to spawn 2 genuine OS threads (`threading.Thread`) coordinated via `threading.Barrier(2)`.
   - On buggy code: Fails RED (either raises `TypeError: unexpected keyword argument 'expected_version'` or both threads succeed clobbering each other).
   - On fixed code: Passes GREEN with exactly 1 `SUCCESS` and 1 `OCC_ERROR`.
2. **Subtest 4 Added for Runtime Transaction Rollback (GAP-04)**:
   - Added `test_gap04_runtime_transaction_rollback` testing empirical runtime rollback when journal corruption is detected during rebuild.
   - Proves `KernelError` is raised, task projection version is untouched, and storage connection is clean without lock leaks.

### B. `tests/T04_kernel/test_rebuild_projection_occ.py`
1. Added `NotFound` import from `scp.task_kernel`.
2. Added `test_rebuild_projection_nonexistent_task_raises_not_found_and_cleans_transaction` to verify transaction rollback on missing tasks.
3. Added `test_rebuild_projection_races_with_transition_exactly_one_winner` to verify cross-method OCC race condition between `transition()` and `rebuild_projection()`.
4. Added `test_rebuild_projection_high_concurrency_stress_single_winner` to stress test 10 parallel threads racing on the same task OCC version.
5. Expanded test suite from 4 tests to 7 tests.

---

## 3. Verification Record

- **Deep Verification (ran actual tests):**
  - `python tools/probes/probe_gap03_04_blind_overwrite.py`: **ALL 4 SUBTESTS PASS (GREEN, Exit 0)**.
    - Subtest 1: Stale version OCC rejection -> `OptimisticLockError` raised.
    - Subtest 2: True parallel threads barrier race -> Exactly 1 `SUCCESS` and 1 `OCC_ERROR`.
    - Subtest 3: Structural SQL `AND version=?` and `_begin()` boundary check.
    - Subtest 4: Runtime transaction rollback on corrupted journal.
  - `pytest tests/T04_kernel/test_rebuild_projection_occ.py -v`: **7 passed in 1.00s (Exit 0)**.
  - `pytest tests/T04_kernel/ -v`: **49 passed in 5.37s (Exit 0)**.
  - `python tools/t00_meta_audit.py`: **PASS (0 new regressions, Exit 0)**.
  - `pytest tests/ -q`: **438 passed in 110.14s (Exit 0)** (Baseline was 431, +7 new regression tests).
- **Shallow Verification (manual only):**
  - None. All claims backed by raw command executions.
- **Unverified aspects:**
  - High concurrency stress (>50 parallel OS processes) contending on rebuild_projection and WAL checkpoints simultaneously.
  - Network-mounted filesystem SQLite locks (e.g. NFS/SMB) which violate POSIX lock guarantees.

---

## 4. Known Issues

- `Minor Robustness Risk`: Rebuilding projection for a task whose row was manually removed from SQLite `tasks` table raises `NotFound` instead of reconstructing from `TASK_CREATED` event, because `create_task()` historically did not store `owner`, `goal`, `deadline_ms`, `risk_tier` in the event payload.
- `Minor Robustness Risk`: Under multi-process contention exceeding 25 retries (>5s sustained write lock hold), SQLite returns `OperationalError: database is locked`.

---

## 5. Remaining Risk & Next Step

GAP-03 and GAP-04 are fully resolved, reinforced with true parallel concurrency probes and adversarial regression tests, and verified across all 438 tests and T00 Meta-Audit.
**Next Step**: Task is ready for final delivery and Sentinel notification.
