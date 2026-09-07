# Handoff Report — Reviewer P2-1: TaskKernel OCC Code Review & Adversarial Challenge

## 1. Observation
- **Reviewed Files**:
  - `scp/task_kernel.py`
  - `scp/task_kernel_parts/taskkernel.py`
  - `tests/T04_kernel/test_satellite_occ_anti_placebo.py`
- **Exception Definition & Exports**:
  - `scp/task_kernel.py` (lines 57-79): Defined `class OptimisticLockError(StaleLease)` with attributes `table`, `entity_id`, and `expected_version`.
  - `scp/task_kernel_parts/taskkernel.py` (lines 14-18): Defined placeholder `class OptimisticLockError(RuntimeError)` which is replaced upon package load via `_taskkernel_part.__dict__.update(globals())`.
  - Exported in `__all__` in both modules.
- **Dynamic Schema Migration**:
  - `scp/task_kernel_parts/taskkernel.py` (lines 99-162): Added `version INTEGER NOT NULL DEFAULT 1` to `CREATE TABLE IF NOT EXISTS` for `leases`, `idempotency`, and `queue_accounts`.
  - In `_schema()`: Added dynamic migration via `PRAGMA table_info` and `ALTER TABLE ... ADD COLUMN version INTEGER NOT NULL DEFAULT 1` for legacy databases.
- **Fenced OCC Implementation**:
  - `heartbeat` (lines 488-530): Conditional update `UPDATE leases SET heartbeat_at=?,expires_at=?,version=version+1 WHERE lease_id=? AND released=0 AND version=?` enforcing `cur.rowcount == 1`.
  - `release` (lines 564-609): Conditional update `UPDATE leases SET released=1,version=version+1 WHERE lease_id=? AND released=0 AND version=?` enforcing `cur.rowcount == 1`.
  - `idempotency_claim` (`task_kernel.py` lines 174-248): Fresh insert sets `version=1`; `RETRYABLE` claim executes `UPDATE idempotency SET status='CLAIMED',result_ref=NULL,version=version+1 WHERE logical_key=? AND status='RETRYABLE' AND version=?`.
  - `idempotency_complete` (`task_kernel.py` lines 250-306): Conditional update `UPDATE idempotency SET status='COMPLETED',result_ref=?,version=version+1 WHERE logical_key=? AND status='CLAIMED' AND version=?` checking `cur.rowcount == 1`.
  - `claim_next` deadline task fail (lines 400-407): Fenced update `UPDATE tasks SET state='FAILED',version=version+1,active_lease_id=NULL,active_fencing_token=0,updated_at=? WHERE task_id=? AND version=?` checking `cur.rowcount == 1`.
  - All satellite updates across `leases` (10 instances) and `queue_accounts` (10 instances) atomically increment `version=version+1`.
- **Test Executions**:
  - `pytest tests/T04_kernel/test_satellite_occ_anti_placebo.py -v`: 7 passed in 0.74s.
  - `pytest tests/T04_kernel -v`: 42 passed in 5.07s.
  - `python tools/t00_meta_audit.py`: 0 new regressions, all integrity checks passed.
- **Integrity Checks**:
  - Zero hardcoded test outputs, zero fake/facade implementations, zero test deletions/skips/xfails, zero assertion weakenings.

## 2. Logic Chain
1. **Subclassing StaleLease Ensures Zero Regressions**: Because `OptimisticLockError` subclasses `StaleLease`, existing callers in SCP that catch `StaleLease` or `KernelError` continue to handle concurrency errors without any breaking change.
2. **Database-Level Boundaries (Invariant INV-01)**: The OCC version checks are executed directly inside SQL transactions (`WHERE ... AND version=?` with `cur.rowcount == 1`). This guarantees that concurrent processes in separate threads/processes cannot corrupt state or perform blind overwrites, even under multi-connection WAL concurrency.
3. **Dynamic Schema Migration Preserves Data**: `PRAGMA table_info` checks ensure that existing databases are upgraded transparently without data loss or recreate operations, while new databases are created with `version` columns directly.
4. **Anti-Placebo Tests Kill Concurrency Mutants**: The 7 tests in `test_satellite_occ_anti_placebo.py` explicitly verify failure cases: stale idempotency completions, stale heartbeats, racing multi-threaded workers, and concurrent retryable claims.

## 3. Caveats
- Bounded scope: Review was scoped to `scp/task_kernel.py`, `scp/task_kernel_parts/taskkernel.py`, and `tests/T04_kernel/test_satellite_occ_anti_placebo.py`. Storage layer DAO review is covered by complementary review agents.
- The pre-existing test failure in `tests/T00_integrity/test_scp_future_target.py` on `main` (`missing=['scp-delta-audit']`) is an inventory sync item handled in parallel work streams.

## 4. Conclusion
- **Verdict: APPROVE**.
- The Phase 2 GAP-02 implementation by Worker P2-1 is complete, verified, compliant with Zero-Trust / Fail-Closed principles and FA-01 to FA-10, and ready for merge gate.

## 5. Verification Method
To independently reproduce the review verification:
1. Anti-placebo suite:
   ```bash
   pytest tests/T04_kernel/test_satellite_occ_anti_placebo.py -v
   ```
2. Full T04 kernel test suite:
   ```bash
   pytest tests/T04_kernel -v
   ```
3. Meta-audit guardrail:
   ```bash
   python tools/t00_meta_audit.py
   ```
4. Verify exception export and hierarchy in Python:
   ```python
   from scp.task_kernel import OptimisticLockError, StaleLease, KernelError
   assert issubclass(OptimisticLockError, StaleLease)
   assert issubclass(OptimisticLockError, KernelError)
   ```
