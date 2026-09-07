# GAP-02 Deep Survey: Satellite Schema & Concurrency Architecture (INV-01)

**Agent**: Explorer P2-2 (`teamwork_preview_explorer`)  
**Parent**: `orchestrator_3` (Conv ID: `4aab71c9-e6ee-472b-8c41-c64e48735a24`)  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\explorer_p2_2`  
**Date**: 2026-09-07T00:00:00Z  
**Governing Invariants**: INV-01 (Atomic OCC Fencing), Zero-Trust, DNA #1 (Reality > Model), DNA #20 (Cryptographic Provenance), DNA #22 (PASS ≠ TRUE), FA-01 through FA-10.

---

## 1. Executive Summary

In Phase 1 of the Evolution Path, Optimistic Concurrency Control (OCC) was introduced for the primary `tasks` projection table in `scp/task_kernel.py` and `scp/task_kernel_parts/taskkernel.py`. However, an exhaustive audit reveals **GAP-02 (OCC Blind Overwrites)**:
1. **Conceptual vs. Concrete Schema Discrepancy**: The requirement specification mentions conceptual entities (`artifacts`, `task_events`, `journals`, `idempotency_keys`, `leases`). In reality, the database schema managed by `TaskKernel` consists of 7 concrete tables: `control`, `tasks`, `events`, `leases`, `checkpoints`, `idempotency`, and `queue_accounts`.
2. **Satellite Tables Lack OCC**: Both `leases` and `idempotency` are repeatedly updated via unversioned SQL `UPDATE` statements (`WHERE lease_id=?` and `WHERE logical_key=?`), making them vulnerable to race conditions, lost updates, and blind overwrites between concurrent workers and kernel recovery routines.
3. **Missing `version` Columns**: Satellite tables (`leases`, `idempotency`, `queue_accounts`) currently lack a `version` column entirely.
4. **Residual Blind Overwrites on `tasks`**: Even on the `tasks` table where OCC was added in Phase 1, two residual blind overwrite statements exist:
   - `taskkernel.py:293`: `UPDATE tasks SET state='FAILED',version=version+1... WHERE task_id=?` (missing `AND version=?`)
   - `taskkernel.py:1005`: `UPDATE tasks SET state=?,version=version+1... WHERE task_id=?` (missing `AND version=?`)
5. **Exception Hierarchy Gap**: Phase 1 raised `StaleLease` with `"concurrency conflict..."` when `cur.rowcount != 1`. There is no dedicated `OptimisticLockError` class in the codebase.
6. **Append-Only vs. Updatable Boundary**: Cryptographic event journals (`events`) and side-effect state checkpoints (`checkpoints`) are strictly **append-only**. Any attempt to mutate them via `UPDATE` violates audit provenance (DNA #20) and payload hash integrity.

---

## 2. Table Schema Survey (`scp/task_kernel_parts/taskkernel.py`)

The SQLite persistence boundary is managed via `KernelStorage` (`scp/kernel_storage.py`), while table DDL is declared and executed in `TaskKernel._schema()` (`scp/task_kernel_parts/taskkernel.py:53-63`).

### 2.1 Inventory of All Kernel Tables

| Table Name | Conceptual Domain Reference | Mutation Mode | Current Schema Overview | Version Column Present? |
|---|---|---|---|---|
| `control` | Global Kill Switch | Updatable | `id` (PK, CHECK id=1), `global_kill`, `global_kill_epoch` | ❌ (Uses `global_kill_epoch`) |
| `tasks` | Primary Task Projection | Updatable | `task_id` (PK), `owner`, `goal`, `risk_tier`, `deadline_ms`, `max_attempts`, `input_hash`, `priority`, `state`, `version`, `active_lease_id`, `active_fencing_token`, `created_at`, `updated_at` | ✅ (`version INTEGER NOT NULL DEFAULT 1`) |
| `events` | `task_events` / `journals` | **Strictly Append-Only** | `event_id` (PK), `task_id`, `seq`, `type`, `from_state`, `to_state`, `actor`, `reason`, `payload_json`, `policy_hash`, `prev_event_hash`, `event_hash`, `created_at`, `UNIQUE(task_id, seq)` | ❌ (N/A — Append-only event journal) |
| `leases` | Worker Leases | Updatable | `lease_id` (PK), `task_id`, `attempt_id`, `worker_id`, `issued_at`, `expires_at`, `heartbeat_at`, `fencing_token`, `global_kill_epoch`, `released` | ❌ **VULNERABLE** |
| `checkpoints` | Step Checkpoints | **Strictly Append-Only** | `checkpoint_id` (PK), `task_id`, `attempt_id`, `step_id`, `state`, `planned_action_hash`, `capability_epoch`, `idempotency_key`, `pre_observation_ref`, `post_observation_ref`, `tool_result_json`, `verifier_verdict`, `payload_hash`, `created_at` | ❌ (N/A — Immutable state snapshots) |
| `idempotency` | `idempotency_keys` | Updatable | `logical_key` (PK), `task_id`, `step_id`, `action_type`, `resource_identity`, `status`, `result_ref`, `created_at` | ❌ **VULNERABLE** |
| `queue_accounts` | Queue Fairness Accounts | Updatable | `owner` (PK), `active`, `dispatch_count`, `last_dispatch_at` | ❌ **VULNERABLE** |

### 2.2 Status of "Artifacts"
The project prompt references `artifacts`. In the current implementation:
- There is no separate `artifacts` SQL table.
- Artifacts and external blobs are referenced via URI/hashes: `checkpoints.pre_observation_ref`, `checkpoints.post_observation_ref`, and `idempotency.result_ref` (e.g. `evidence://...`, `content_blobs`).
- If an `artifacts` table is introduced in future phases, it must follow Content-Addressable Storage (CAS) semantics: write-once, immutable, keyed by SHA256, strictly append-only.

---

## 3. Phase 1 OCC Implementation Analysis (`tasks` Table)

In Phase 1, OCC was implemented for the `tasks` table as follows:

### 3.1 Schema Definition
In `TaskKernel._schema()` (`taskkernel.py:54`):
```sql
CREATE TABLE IF NOT EXISTS tasks (
    ...
    version INTEGER NOT NULL DEFAULT 1,
    ...
);
```

### 3.2 Caller Interface & Verification
In `TaskKernel.transition(...)` (`taskkernel.py:122-151`):
- Accepts optional `expected_version: int | None = None`.
- Pre-checks version before processing:
  ```python
  task = self._task(task_id)
  if expected_version is not None and int(task["version"]) != expected_version:
      raise StaleLease(
          f"concurrency conflict on task {task_id}: expected version {expected_version}, found {task['version']}"
      )
  cur_version = int(task["version"])
  ```

### 3.3 Atomic Update & Concurrency Verification
At line 222-227:
```python
cur = self.conn.execute(
    "UPDATE tasks SET state=?,version=version+1,active_lease_id=?,active_fencing_token=?,updated_at=? WHERE task_id=? AND version=?",
    (to_state, new_lease_id, new_fencing_token, now_iso(), task_id, cur_version),
)
if cur.rowcount != 1:
    raise StaleLease(f"concurrency conflict transitioning task {task_id}: expected version {cur_version}")
```

### 3.4 Identified Deficiencies in Phase 1
1. **Missing `OptimisticLockError`**:
   The code raises `StaleLease` instead of `OptimisticLockError`. While `StaleLease` works for lease-bound transitions, raising `StaleLease` for unleased tasks or satellite updates (like idempotency keys) violates domain semantics.
2. **Residual Blind Overwrite at `taskkernel.py:293`**:
   In `claim_next()`:
   ```python
   self.conn.execute(
       "UPDATE tasks SET state='FAILED',version=version+1,active_lease_id=NULL,active_fencing_token=0,updated_at=? WHERE task_id=?",
       (now_iso(), task['task_id']),
   )
   ```
   This executes an unconditional update without checking `WHERE version=?`.
3. **Residual Blind Overwrite at `taskkernel.py:1005`**:
   In `rebuild_projection()`:
   ```python
   self.conn.execute(
       'UPDATE tasks SET state=?,version=version+1,active_lease_id=?,active_fencing_token=?,updated_at=? WHERE task_id=?',
       ...
   )
   ```
   Missing `WHERE version=?`.
4. **Missing Migration for `tasks.version`**:
   While `TaskKernel._schema()` has migration logic for `priority`, `active_lease_id`, and `active_fencing_token` using `PRAGMA table_info(tasks)`, it does NOT verify whether `version` exists on legacy databases.

---

## 4. Schema Evolution & SQLite Migration Requirements

In SQLite, `CREATE TABLE IF NOT EXISTS` is a no-op if the table already exists. Consequently, adding columns to an existing SQLite database requires dynamic migration inspection.

### 4.1 Required DDL Changes

1. **`leases` Table**:
   - DDL: Add `version INTEGER NOT NULL DEFAULT 1`
   - Initial DDL script:
     ```sql
     CREATE TABLE IF NOT EXISTS leases (
         lease_id TEXT PRIMARY KEY,
         task_id TEXT NOT NULL,
         attempt_id TEXT NOT NULL,
         worker_id TEXT NOT NULL,
         issued_at REAL NOT NULL,
         expires_at REAL NOT NULL,
         heartbeat_at REAL NOT NULL,
         fencing_token INTEGER NOT NULL,
         global_kill_epoch INTEGER NOT NULL,
         released INTEGER NOT NULL DEFAULT 0,
         version INTEGER NOT NULL DEFAULT 1
     );
     ```
   - Migration logic in `TaskKernel._schema()`:
     ```python
     lease_cols = {row['name'] for row in self.conn.execute('PRAGMA table_info(leases)').fetchall()}
     if 'version' not in lease_cols:
         self.conn.execute('ALTER TABLE leases ADD COLUMN version INTEGER NOT NULL DEFAULT 1')
     ```

2. **`idempotency` Table**:
   - DDL: Add `version INTEGER NOT NULL DEFAULT 1`
   - Initial DDL script:
     ```sql
     CREATE TABLE IF NOT EXISTS idempotency (
         logical_key TEXT PRIMARY KEY,
         task_id TEXT NOT NULL,
         step_id TEXT NOT NULL,
         action_type TEXT NOT NULL,
         resource_identity TEXT NOT NULL,
         status TEXT NOT NULL,
         result_ref TEXT,
         created_at TEXT NOT NULL,
         version INTEGER NOT NULL DEFAULT 1
     );
     ```
   - Migration logic in `TaskKernel._schema()`:
     ```python
     idempotency_cols = {row['name'] for row in self.conn.execute('PRAGMA table_info(idempotency)').fetchall()}
     if 'version' not in idempotency_cols:
         self.conn.execute('ALTER TABLE idempotency ADD COLUMN version INTEGER NOT NULL DEFAULT 1')
     ```

3. **`queue_accounts` Table**:
   - DDL: Add `version INTEGER NOT NULL DEFAULT 1`
   - Migration logic:
     ```python
     queue_cols = {row['name'] for row in self.conn.execute('PRAGMA table_info(queue_accounts)').fetchall()}
     if 'version' not in queue_cols:
         self.conn.execute('ALTER TABLE queue_accounts ADD COLUMN version INTEGER NOT NULL DEFAULT 1')
     ```

4. **`tasks` Table (Defense-in-depth migration)**:
   - Migration logic:
     ```python
     if 'version' not in task_columns:
         self.conn.execute('ALTER TABLE tasks ADD COLUMN version INTEGER NOT NULL DEFAULT 1')
     ```

---

## 5. Append-Only vs. Updatable Boundary Analysis

In accordance with SCP DNA principles and the Task Kernel architecture:

```
                      ┌─────────────────────────────────────────┐
                      │             STORAGE TABLES              │
                      └────────────────────┬────────────────────┘
                                           │
                 ┌─────────────────────────┴─────────────────────────┐
                 ▼                                                   ▼
     ┌───────────────────────┐                           ┌───────────────────────┐
     │   UPDATABLE TABLES    │                           │  APPEND-ONLY TABLES   │
     │  (OCC Strict Fencing) │                           │  (Immutable History)  │
     ├───────────────────────┤                           ├───────────────────────┤
     │ • tasks               │                           │ • events              │
     │ • leases              │                           │   (Cryptographic Merkle│
     │ • idempotency         │                           │    Journal; seq+hash) │
     │ • queue_accounts      │                           │ • checkpoints         │
     │ • control (Epoch)     │                           │   (Step State Hashes) │
     └───────────────────────┘                           │ • artifacts (CAS)     │
                                                         └───────────────────────┘
```

### 5.1 Strictly Append-Only Tables
1. **`events` (`task_events` / `journals`)**:
   - Each event contains `seq` (strictly monotonic per task) and `event_hash` (computed over `prev_event_hash`, `seq`, `type`, `payload_json`, etc.).
   - Modifying an event breaks the hash chain, corrupts audit replay, and invalidates verification.
   - **Architectural Rule**: `UPDATE events` is strictly FORBIDDEN. If any layer attempts an UPDATE on `events`, it must fail-closed.
2. **`checkpoints`**:
   - Stores pre/post observation references and `payload_hash = stable_hash(...)`.
   - Modifying a checkpoint invalidates the hash and permits unauthorized side-effect tampering.
   - **Architectural Rule**: `UPDATE checkpoints` is strictly FORBIDDEN.
3. **`artifacts` (CAS)**:
   - Must be write-once, immutable, content-addressed by SHA256.

### 5.2 Updatable Satellite Tables Requiring OCC
1. **`leases`**:
   - Mutated by `heartbeat()`, `release()`, `expire_leases()`, `cancel()`, `reconcile_unknown()`.
   - Vulnerability: A heartbeat on a released or expired lease will resurrect the lease if not fenced.
2. **`idempotency`**:
   - Mutated by `idempotency_claim()`, `idempotency_complete()`, `reconcile_unknown()`.
   - Vulnerability: Concurrent workers claiming or completing the same logical key can overwrite each other without atomic version checks.
3. **`queue_accounts`**:
   - Mutated on claim and release. Concurrent dispatches or sweeps can suffer from lost updates if not protected.

---

## 6. Unified OCC Architecture & Interface Contracts (INV-01)

### 6.1 Exception Hierarchy
To satisfy both backward compatibility with Phase 1 tests (which assert `pytest.raises(StaleLease)`) and strict semantic naming:

```python
class KernelError(RuntimeError):
    """Base exception for all Task Kernel errors."""
    pass

class StaleLease(KernelError):
    """Raised when lease authority is missing, expired, or invalid."""
    pass

class OptimisticLockError(StaleLease):
    """Raised when an atomic OCC check fails (0 rows matched WHERE version=?).
    
    Subclasses StaleLease so existing Phase 1 tests and handlers catching StaleLease
    remain 100% green without test loosening (FA-01).
    """
    pass
```

### 6.2 The Unified Invariant INV-01 Contract
For EVERY update operation on an updatable table:
1. **Pre-check**: Caller passes `expected_version: int | None`. If provided, compare against current in-database version; if mismatched, immediately raise `OptimisticLockError`.
2. **Atomic Execution**: Execute the UPDATE statement with `SET ..., version = version + 1 WHERE <pk> = ? AND version = ?`.
3. **Rowcount Verification**: Check `cur.rowcount`.
   - If `cur.rowcount == 1`: Success. Return updated version or entity.
   - If `cur.rowcount == 0`: Raise `OptimisticLockError(f"concurrency conflict on {table} {pk}: expected version {expected_version}")`. Transaction rolls back automatically (`_rollback()`).

### 6.3 Detailed Interface Contracts for Satellite Entities

#### Contract 1: `idempotency` OCC
```python
def idempotency_claim(
    self,
    task_id: str,
    step_id: str,
    action_type: str,
    resource_identity: str,
    expected_version: int | None = None,
) -> tuple[str, bool, int]:
    """Returns (logical_key, is_claimed, version).
    
    If status is RETRYABLE, updates to CLAIMED with:
        UPDATE idempotency
        SET status='CLAIMED', result_ref=NULL, version=version+1
        WHERE logical_key=? AND status='RETRYABLE' AND version=?
    Raises OptimisticLockError if rowcount != 1.
    """

def idempotency_complete(
    self,
    logical_key: str,
    result_ref: str,
    expected_version: int | None = None,
) -> int:
    """Updates status from CLAIMED to COMPLETED.
    
    Executes:
        UPDATE idempotency
        SET status='COMPLETED', result_ref=?, version=version+1
        WHERE logical_key=? AND status='CLAIMED' AND version=?
    Raises OptimisticLockError if rowcount != 1.
    Returns new version.
    """
```

#### Contract 2: `leases` OCC
```python
def heartbeat(
    self,
    lease_id: str,
    ttl_seconds: float = 30.0,
    expected_version: int | None = None,
) -> Lease:
    """Renews active lease with atomic OCC check.
    
    Executes:
        UPDATE leases
        SET heartbeat_at=?, expires_at=?, version=version+1
        WHERE lease_id=? AND released=0 AND version=?
    Raises:
        NotFound: if lease_id does not exist.
        StaleLease: if lease exists but released == 1.
        OptimisticLockError: if version != expected_version or rowcount != 1.
    """

def release(
    self,
    task_id: str,
    lease_id: str,
    expected_version: int | None = None,
) -> None:
    """Releases active lease with atomic OCC check.
    
    Executes:
        UPDATE leases
        SET released=1, version=version+1
        WHERE lease_id=? AND released=0 AND version=?
    """
```

---

## 7. Next Steps for Implementation (Milestones M2 - M4)

1. **M2 (Explorer P2-3)**: Construct independent exploit probe demonstrating blind overwrite on unversioned `idempotency` and `leases` tables (FA-09 compliance).
2. **M3 (Implementer)**:
   - Add `OptimisticLockError(StaleLease)` to `scp/task_kernel.py`.
   - Update `_schema()` with `version INTEGER NOT NULL DEFAULT 1` and `PRAGMA table_info` migrations.
   - Implement `WHERE version=?` on all satellite UPDATE queries (`leases`, `idempotency`, and residual `tasks` lines 293, 1005).
3. **M4 (Verifier)**:
   - Run Anti-Placebo mutation tests.
   - Run full regression test suite `pytest tests/ -q`.
   - Run `python tools/t00_meta_audit.py`.
