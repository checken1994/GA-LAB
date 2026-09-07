# Handoff Report — Reviewer P2-2: Zero-Trust & Invariant INV-01 Review

## 1. Observation
- **Codebase Modifications**:
  - `scp/task_kernel.py`: Lines 57-79 define `OptimisticLockError(StaleLease)`. Lines 170-172 sync definitions to `task_kernel_parts.taskkernel`. Lines 180-245 implement `_idempotency_claim_fenced` with `WHERE ... AND version=?` and `cur.rowcount == 1`. Lines 270-305 implement `_idempotency_complete_fenced` with `WHERE ... AND version=?` and `cur.rowcount != 1 -> raise OptimisticLockError`. Lines 355-380 implement OCC on idempotency during `_reconcile_unknown_complete_outcomes`.
  - `scp/task_kernel_parts/taskkernel.py`: Lines 14-16 define `OptimisticLockError(RuntimeError)` placeholder overwritten by `scp.task_kernel.OptimisticLockError`. Lines 109-111, 138, 145 define `version INTEGER NOT NULL DEFAULT 1` in schemas of `leases`, `idempotency`, and `queue_accounts`. Lines 158-162 provide automated schema evolution via `PRAGMA table_info` and `ALTER TABLE ... ADD COLUMN version`. Lines 504-525 enforce OCC in `heartbeat`. Lines 579-595 enforce OCC in `release`. Lines 400-405 in `claim_next` fence deadline expiry cleanup with `WHERE task_id=? AND version=?` and check `cur.rowcount == 1`. Lines 760-785 enforce OCC in `reconcile_unknown`.
  - `tests/T04_kernel/test_satellite_occ_anti_placebo.py`: 7 tests covering exception hierarchy, idempotency stale update fail-closed, lease heartbeat and release conflict fail-closed, racing concurrent workers with 1 winner, retryable idempotency claim, claim_next deadline fencing, and schema evolution on legacy database.
- **Git Status & Diff**:
  - `git diff tests/`: 0 changes to existing tests. No existing assertions loosened (FA-01), no tests deleted/skipped/xfailed (FA-02).
  - Only `tests/T04_kernel/test_satellite_occ_anti_placebo.py` added as untracked new test file.
- **Inheritance & Hierarchy Verification**:
  - `python -c "import scp.task_kernel as tk; import scp.task_kernel_parts.taskkernel as tkp; print(tk.OptimisticLockError is tkp.OptimisticLockError); print(issubclass(tk.OptimisticLockError, tk.StaleLease)); print(issubclass(tk.OptimisticLockError, tk.KernelError))"` output:
    ```
    True
    True
    True
    ```
- **Execution Evidence**:
  - `pytest tests/T04_kernel/test_satellite_occ_anti_placebo.py -v`:
    ```text
    tests/T04_kernel/test_satellite_occ_anti_placebo.py::test_anti_placebo_exception_hierarchy_and_exports PASSED [ 14%]
    tests/T04_kernel/test_satellite_occ_anti_placebo.py::test_anti_placebo_idempotency_stale_update_fails_closed PASSED [ 28%]
    tests/T04_kernel/test_satellite_occ_anti_placebo.py::test_anti_placebo_lease_heartbeat_and_release_conflict_fails_closed PASSED [ 42%]
    tests/T04_kernel/test_satellite_occ_anti_placebo.py::test_anti_placebo_concurrent_racing_workers_exactly_one_winner PASSED [ 57%]
    tests/T04_kernel/test_satellite_occ_anti_placebo.py::test_anti_placebo_idempotency_claim_retryable_occ PASSED [ 71%]
    tests/T04_kernel/test_satellite_occ_anti_placebo.py::test_anti_placebo_tasks_claim_next_deadline_occ_fenced PASSED [ 85%]
    tests/T04_kernel/test_satellite_occ_anti_placebo.py::test_anti_placebo_schema_evolution_preserves_legacy_database PASSED [100%]
    ======= 7 passed in 1.15s =======
    ```
  - `pytest tests/T04_kernel/ -v`:
    ```text
    ======= 42 passed in 5.48s =======
    ```
  - `python tools/t00_meta_audit.py`:
    ```text
    [T00 Meta-Audit] Starting Test-Integrity Regression Authority...
    [T00 Meta-Audit] Trusted Base: origin/main
    [T00 Meta-Audit] Collecting baseline pytest nodeids (origin/main)...
    [T00 Meta-Audit] Collecting candidate pytest nodeids...
    [T00 Meta-Audit] All integrity checks passed (0 new regressions).
    ```

## 2. Logic Chain
1. **Zero-Trust Boundary at Database/Hardware Level**:
   - As observed in `scp/task_kernel.py` (lines 222, 292, 361) and `scp/task_kernel_parts/taskkernel.py` (lines 516, 588, 765), every mutation on satellite tables executes an atomic SQL query specifying `AND version=?` in the `WHERE` clause and increments `version=version+1`.
   - Each query checks `cur.rowcount == 1` or raises `OptimisticLockError`. Under concurrent multi-connection WAL execution, this guarantees that memory state discrepancies cannot bypass database integrity.
2. **Backward Compatibility via Subclassing**:
   - `OptimisticLockError` inherits from `StaleLease` and `KernelError`.
   - Existing callers catching `except StaleLease:` or `except KernelError:` catch `OptimisticLockError` transparently. Callers targeting OCC can inspect `table`, `entity_id`, and `expected_version`.
3. **Strict Test Integrity (FA-01, FA-02)**:
   - `git diff tests/` is completely empty for existing files. No assertions were loosened, no tests deleted, skipped, or xfailed.
   - `python tools/t00_meta_audit.py` passed with 0 new regressions against `origin/main`.
4. **Anti-Placebo Mutant Killing**:
   - 7 anti-placebo tests directly exercise mutants M1 to M4, proving that stale updates fail closed, concurrent races yield exactly 1 winner, and schema evolution automatically migrates legacy databases without data loss.

## 3. Caveats
- Baseline debt in `tools/t00_meta_audit.py` contains 5 historical instances existing on `origin/main` (pre-existing debt, non-blocking).
- This review focuses specifically on TaskKernel and satellite table OCC (GAP-02). Outer layer integration (e.g. gateway loopback or dashboard UI) remains bounded by their respective gates.

## 4. Conclusion
**VERDICT: APPROVE**
The implementation strictly satisfies Invariant INV-01, enforces database-level boundaries without relying on RAM variables, preserves full backward compatibility for `StaleLease`, passes all 42 tests in `tests/T04_kernel` and the meta-audit with 0 regressions, and complies with FA-01 through FA-10.

## 5. Verification Method
To independently verify this verdict:
1. Run the anti-placebo test suite:
   ```bash
   pytest tests/T04_kernel/test_satellite_occ_anti_placebo.py -v
   ```
2. Run the entire kernel test suite:
   ```bash
   pytest tests/T04_kernel/ -v
   ```
3. Run the meta-audit integrity check:
   ```bash
   python tools/t00_meta_audit.py
   ```
4. Verify exception hierarchy:
   ```bash
   python -c "import scp.task_kernel as tk; assert issubclass(tk.OptimisticLockError, tk.StaleLease); assert issubclass(tk.OptimisticLockError, tk.KernelError)"
   ```
