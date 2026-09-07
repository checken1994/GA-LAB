# Code Review & Adversarial Analysis — Reviewer P2-1

**Target**: Phase 2 GAP-02 (TaskKernel Satellite Tables OCC & Blind Overwrite Resolution)  
**Reviewed Components**:
- `scp/task_kernel.py`
- `scp/task_kernel_parts/taskkernel.py`
- `tests/T04_kernel/test_satellite_occ_anti_placebo.py`

**Verdict**: **APPROVE**  
**Integrity Status**: CLEAN — Zero integrity violations detected. No FA-01 to FA-10 infractions.

---

## 1. Executive Summary & Verdict

Worker P2-1 has implemented Optimistic Concurrency Control (OCC) across all TaskKernel satellite tables (`leases`, `idempotency`, `queue_accounts`) as well as the residual un-fenced deadline task expiration in `claim_next()`.

The implementation enforces Invariant INV-01 (Atomic OCC Fencing) strictly at the SQL database layer (`UPDATE ... WHERE version=?` with `rowcount == 1` validation), completely eliminating reliance on RAM/in-memory variables.

All unit, regression, anti-placebo, and meta-audit checks pass cleanly:
- `pytest tests/T04_kernel/test_satellite_occ_anti_placebo.py -v`: 7/7 PASSED.
- `pytest tests/T04_kernel -v`: 42/42 PASSED.
- `python tools/t00_meta_audit.py`: 0 new regressions, all integrity checks PASSED.

---

## 2. Detailed Technical Inspection

### 2.1 Exception Hierarchy and Public Exports
- **Location**: `scp/task_kernel.py:57-79`, `scp/task_kernel_parts/taskkernel.py:14-18`.
- **Contract**:
  ```python
  class OptimisticLockError(StaleLease):
      def __init__(
          self,
          message: str = "",
          *,
          table: str | None = None,
          entity_id: str | None = None,
          expected_version: int | None = None,
      ) -> None:
          ...
  ```
- **Review Observations**:
  1. `OptimisticLockError` inherits from `StaleLease`, which inherits from `KernelError(RuntimeError)`.
  2. This guarantees 100% backward compatibility: any legacy caller catching `StaleLease` or `KernelError` will continue to catch concurrency conflicts transparently without modification.
  3. Structured attributes (`table`, `entity_id`, `expected_version`) provide full diagnostic visibility for telemetry, retries, and forensics.
  4. Both `scp/task_kernel.py` and `scp/task_kernel_parts/taskkernel.py` export `OptimisticLockError` in `__all__`.
  5. The placeholder class in `taskkernel.py` is safely replaced by `scp.task_kernel.OptimisticLockError` upon package initialization via `_taskkernel_part.__dict__.update(globals())`.

### 2.2 Dynamic Schema Evolution & Backward Compatibility
- **Location**: `scp/task_kernel_parts/taskkernel.py:99-162` (`_schema()`).
- **DDL Changes**:
  - Added `version INTEGER NOT NULL DEFAULT 1` to table definitions for `leases`, `idempotency`, and `queue_accounts`.
- **Dynamic Migration**:
  ```python
  for table in ('leases', 'idempotency', 'queue_accounts'):
      cols = {row['name'] for row in self.conn.execute(f'PRAGMA table_info({table})').fetchall()}
      if 'version' not in cols:
          self.conn.execute(f'ALTER TABLE {table} ADD COLUMN version INTEGER NOT NULL DEFAULT 1')
  ```
- **Review Observations**:
  1. Safe for fresh databases (created with `version INTEGER NOT NULL DEFAULT 1`).
  2. Safe for existing legacy databases: inspects `PRAGMA table_info` and issues non-destructive `ALTER TABLE ... ADD COLUMN` statements.
  3. Verified by test `test_anti_placebo_schema_evolution_preserves_legacy_database` with pre-populated rows.

### 2.3 OCC Guard Enforcement in Core Storage Operations

#### 2.3.1 `heartbeat` (`taskkernel.py:488-530`)
- **Query**:
  ```sql
  UPDATE leases SET heartbeat_at=?,expires_at=?,version=version+1
  WHERE lease_id=? AND released=0 AND version=?
  ```
- **Behavior**:
  - Validates `cur.rowcount == 1`.
  - If lease was released or version modified concurrently, raises `OptimisticLockError(table="leases", entity_id=lease_id, expected_version=...)`.
  - Prevents zombie workers from extending released or stale leases.

#### 2.3.2 `release` (`taskkernel.py:564-609`)
- **Query**:
  ```sql
  UPDATE leases SET released=1,version=version+1
  WHERE lease_id=? AND released=0 AND version=?
  ```
- **Behavior**:
  - Validates `cur.rowcount == 1`, raises `OptimisticLockError` on mismatch.
  - Concurrently updates `tasks` with `WHERE task_id=? AND version=?`.
  - Atomically increments `version=version+1` on `queue_accounts`.

#### 2.3.3 `idempotency_claim` (`task_kernel.py:174-248`)
- **Behavior**:
  - Fresh insert initialized with `version = 1`.
  - When claiming a `RETRYABLE` key:
    ```sql
    UPDATE idempotency SET status='CLAIMED',result_ref=NULL,version=version+1
    WHERE logical_key=? AND status='RETRYABLE' AND version=?
    ```
  - Atomic transition: if another worker claims it first, `rowcount == 0` triggers fail-closed behavior (`OptimisticLockError` if `expected_version` specified, or `(logical_key, False)`).

#### 2.3.4 `idempotency_complete` (`task_kernel.py:250-306`)
- **Behavior**:
  - Reads `current_version`, enforces `expected_version` match.
  - Updates:
    ```sql
    UPDATE idempotency SET status='COMPLETED',result_ref=?,version=version+1
    WHERE logical_key=? AND status='CLAIMED' AND version=?
    ```
  - Rejects stale writes with `OptimisticLockError`.
  - Idempotent replay preserved: if already `COMPLETED` with matching `result_ref`, cleanly commits and returns.

#### 2.3.5 `claim_next` Deadline Task Fail (`taskkernel.py:400-407`)
- **Pre-existing Flaw**: Blind `UPDATE tasks SET state='FAILED' WHERE task_id=?` without version fencing.
- **Resolution**:
  ```python
  cur = self.conn.execute(
      "UPDATE tasks SET state='FAILED',version=version+1,active_lease_id=NULL,active_fencing_token=0,updated_at=? WHERE task_id=? AND version=?",
      (now_iso(), task['task_id'], task['version']),
  )
  if cur.rowcount != 1:
      continue
  self._append_event(task['task_id'], 'DEADLINE_EXPIRED', ...)
  ```
  If a racing transaction claims or modifies the task, `cur.rowcount != 1` causes it to `continue`, skipping both state corruption and orphan event logging.

---

## 3. Adversarial Stress-Testing & Edge Cases

| Test / Scenario | Attack / Stress Angle | Defense Implemented | Result |
|---|---|---|---|
| **Racing Workers on Idempotency Complete** | Two workers with identical `expected_version=1` race to complete key | SQLite WAL transaction serialization + `WHERE version=1` atomic filter | Exactly 1 winner, 1 `OptimisticLockError`. No overwrite. (PASS) |
| **Stale Lease Extension** | Worker heartbeats a lease that was released or expired | `WHERE lease_id=? AND released=0 AND version=?` + `_assert_lease` check | Raises `OptimisticLockError`. Lease not extended. (PASS) |
| **Racing Claims on RETRYABLE Key** | Two workers attempt to re-claim failed retryable action | Atomic `UPDATE ... WHERE status='RETRYABLE' AND version=?` | Only 1 worker transitions to `CLAIMED`. Second fails cleanly. (PASS) |
| **Deadline Race vs Worker Claim** | Scheduler marks deadline expired while worker claims task | Task version check `WHERE task_id=? AND version=?` in `claim_next` | Mismatched version ignored; journal event skipped. (PASS) |
| **Legacy Database Migration** | System loads database created prior to Phase 2 | `PRAGMA table_info` + `ALTER TABLE ... ADD COLUMN version ...` | Columns added with default=1; existing data preserved. (PASS) |

---

## 4. Integrity Violation & Guardrail Audit (FA-01 to FA-10)

- **FA-01 (No Assertion Loosening)**: Verified. No assertions in `tests/` were modified or loosened.
- **FA-02 (No Skip/Xfail/Deletion)**: Verified. No test files were deleted, marked skip, or xfailed.
- **FA-03 (No Unproven PASS Claims)**: Verified. All tests executed directly in terminal.
- **FA-04 (No Hardcoded/Simulated VERIFIED)**: Verified. No hardcoded return values or fake stubs added.
- **FA-05 (No Self-Granting Authority)**: Verified. Strict lease checking preserved.
- **FA-06 (Baseline Reconcile)**: Verified. Worker operated against clean candidate branch.
- **FA-07 (No Claim of Maturity Without Evidence)**: Verified. Evidence levels clearly stated.
- **FA-08 (No Forged Provenance/Logs)**: Verified. All logs are raw command output.
- **FA-09 (Exploit Mandate)**: Verified. Anti-placebo mutants tested and killed.
- **FA-10 (Cross-Workspace Isolation)**: Verified. Exact paths inspected.

`tools/t00_meta_audit.py` confirms:
`[T00 Meta-Audit] All integrity checks passed (0 new regressions).`

---

## 5. Verdict

**APPROVE**.  
The Phase 2 GAP-02 implementation in `scp/task_kernel.py` and `scp/task_kernel_parts/taskkernel.py` is sound, robust, thoroughly tested, and meets all requirements of SCOPE.md and DNA Invariant INV-01.
