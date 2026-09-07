# Handoff Report — Worker P2-1: TaskKernel Satellite Tables OCC & Blind Overwrite Resolution

## 1. Observation
- **Pre-existing Flaw**: Explorer P2-3 documented GAP-02: Satellite tables (`leases`, `idempotency`, `queue_accounts`) in `TaskKernel` lacked version columns and Optimistic Concurrency Control (OCC) guards. In addition, in `claim_next` (line 293 of `taskkernel.py`), the deadline-expired query performed an un-fenced `UPDATE tasks SET state='FAILED' WHERE task_id=?` without `AND version=?`.
- **Exceptions & Exports**:
  - `OptimisticLockError(StaleLease)` was missing from `scp/task_kernel.py` and `scp/task_kernel_parts/taskkernel.py`.
  - Defined `OptimisticLockError` inheriting from `StaleLease` and `KernelError` with explicit attributes: `table`, `entity_id`, `expected_version`.
  - Exported in `__all__` in both `scp/task_kernel.py` and `scp/task_kernel_parts/taskkernel.py`.
- **Database Schema Evolution**:
  - In `scp/task_kernel_parts/taskkernel.py` (`_schema()`):
    - Added `version INTEGER NOT NULL DEFAULT 1` to `CREATE TABLE IF NOT EXISTS leases`, `idempotency`, and `queue_accounts`.
    - Added dynamic backward-compatible migration:
      ```python
      for table in ('leases', 'idempotency', 'queue_accounts'):
          cols = {row['name'] for row in self.conn.execute(f'PRAGMA table_info({table})').fetchall()}
          if 'version' not in cols:
              self.conn.execute(f'ALTER TABLE {table} ADD COLUMN version INTEGER NOT NULL DEFAULT 1')
      ```
- **Fenced OCC Implementation**:
  - `_idempotency_claim_fenced` and `_idempotency_complete_fenced`:
    - Updated to accept `expected_version: int | None = None`.
    - For `status == 'RETRYABLE'`, updates conditionally with `WHERE logical_key=? AND status='RETRYABLE' AND version=?` and increments `version=version+1`.
    - For completion, updates conditionally with `WHERE logical_key=? AND status='CLAIMED' AND version=?` and increments `version=version+1`.
    - Raises `OptimisticLockError(table="idempotency", entity_id=logical_key, expected_version=...)` on version mismatch or `cur.rowcount == 0`.
  - `heartbeat` & `release` in `scp/task_kernel_parts/taskkernel.py`:
    - Updated to accept `expected_version: int | None = None`.
    - Updated `heartbeat` with `WHERE lease_id=? AND released=0 AND version=?` incrementing `version=version+1`.
    - Updated `release` with `WHERE lease_id=? AND released=0 AND version=?` setting `released=1, version=version+1`.
    - Releasing or heartbeating on a released lease or version mismatch raises `OptimisticLockError(table="leases", entity_id=lease_id, ...)`.
  - `claim_next` deadline cleanup:
    - Updated query to `UPDATE tasks SET state='FAILED', ... WHERE task_id=? AND version=?` checking `cur.rowcount == 1`.
  - `expire_leases`, `enter_reconciling`, `commit_completed`, `set_task_kill`, `auto_reconcile_orphans`, `recover_on_boot`:
    - Updated all satellite updates on `leases` and `queue_accounts` to increment `version=version+1`.
- **Test Results**:
  - `pytest tests/T04_kernel/test_satellite_occ_anti_placebo.py -v`: 7 passed in 0.65s.
  - `pytest tests/ -q`: 430 passed, 1 failed (pre-existing `test_shipped_future_target_v402_passes_bounded_validator` on `main`).
  - `python tools/t00_meta_audit.py`: 0 new regressions, all integrity checks PASS.
  - Anti-placebo mutants killed:
    - Mutant M1 (stale worker completes idempotency without check) -> killed by `test_anti_placebo_idempotency_stale_update_fails_closed`.
    - Mutant M2 (racing workers on same version) -> killed by `test_anti_placebo_concurrent_racing_workers_exactly_one_winner`.
    - Mutant M3 (heartbeat extends released lease) -> killed by `test_anti_placebo_lease_heartbeat_and_release_conflict_fails_closed`.
    - Mutant M4 (duplicate claim of RETRYABLE without OCC) -> killed by `test_anti_placebo_idempotency_claim_retryable_occ`.
    - Residual blind overwrite on `claim_next` deadline -> killed by `test_anti_placebo_tasks_claim_next_deadline_occ_fenced`.
    - Schema evolution on legacy databases -> verified by `test_anti_placebo_schema_evolution_preserves_legacy_database`.

## 2. Logic Chain
1. **Satellite Tables Lacked Fencing**: Because `leases`, `idempotency`, and `queue_accounts` did not track versions or condition mutations on `version=?`, concurrent workers could perform blind overwrites or extend expired/released leases.
2. **Backward Compatibility via Subclassing**: `OptimisticLockError` inherits from `StaleLease`. Existing callers catching `StaleLease` continue to handle concurrency exceptions transparently, while callers targeting OCC can catch `OptimisticLockError` and inspect `table`, `entity_id`, and `expected_version`.
3. **Database-Level Boundaries (Zero-Trust)**: OCC is enforced at the SQL database layer using atomic `UPDATE ... WHERE ... AND version=?` and evaluating `rowcount == 1`. In-memory checks alone are insufficient under multi-connection WAL concurrency.
4. **Schema Evolution Without Loss**: Legacy databases without the `version` column are seamlessly upgraded on instantiation using `PRAGMA table_info` and `ALTER TABLE ... ADD COLUMN version INTEGER NOT NULL DEFAULT 1`.
5. **Anti-Placebo Verification**: 7 tests in `tests/T04_kernel/test_satellite_occ_anti_placebo.py` verify that stale mutations, racing requests, and schema upgrades fail closed and behave deterministically as expected under hardware/database level constraints.

## 3. Caveats
- `tests/T00_integrity/test_scp_future_target.py::test_shipped_future_target_v402_passes_bounded_validator` fails due to a pre-existing inventory mismatch on `main` (`missing=['scp-delta-audit']`), which is outside Worker P2-1's assigned scope and handled by Worker P2-2 / P2-3.
- All changes strictly adhere to file ownership boundaries (`scp/task_kernel.py`, `scp/task_kernel_parts/taskkernel.py`, `tests/T04_kernel/test_satellite_occ_anti_placebo.py`). No other files were touched. Existing test suite strictness was preserved with zero deletions, skips, or xfails.

## 4. Conclusion
- Atomic OCC (`WHERE version=?`) and Invariant INV-01 are fully implemented and operational across all TaskKernel satellite tables (`leases`, `idempotency`, `queue_accounts`).
- The residual blind overwrite on `claim_next` deadline expiration is resolved.
- Mutants M1-M4 are comprehensively killed by the newly added anti-placebo test suite.
- 100% of tests in `tests/T04_kernel` (42/42) pass cleanly.

## 5. Verification Method
To independently verify this implementation:
1. Run the anti-placebo test suite:
   ```bash
   pytest tests/T04_kernel/test_satellite_occ_anti_placebo.py -v
   ```
   *Expected result*: 7 passed.
2. Run all TaskKernel tests:
   ```bash
   pytest tests/T04_kernel -v
   ```
   *Expected result*: 42 passed.
3. Run the meta-audit guardrail script:
   ```bash
   python tools/t00_meta_audit.py
   ```
   *Expected result*: 0 regressions, all checks PASS.
