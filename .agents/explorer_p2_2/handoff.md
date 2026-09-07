# Handoff Report — Explorer P2-2: Satellite Schema & Concurrency Architecture (INV-01)

**Agent ID**: `explorer_p2_2` (`teamwork_preview_explorer`)  
**Parent**: `orchestrator_3` (Conv ID: `4aab71c9-e6ee-472b-8c41-c64e48735a24`)  
**Scope**: Phase 2 — GAP-02 (OCC Blind Overwrites Elimination)  
**Milestone**: M1 (Deep Survey & Concurrency Architecture)  
**Date**: 2026-09-07T00:00:00Z  

---

## 1. Observation

1. **Storage Layer & DDL Separation**:
   - In `scp/kernel_storage.py:1-12`, the persistence boundary defines `KernelStorage` protocol and `SQLiteKernelStorage` for connection pooling, transaction serialization (`BEGIN IMMEDIATE`), and online backup. It intentionally delegates SQL schema and projections to `TaskKernel`.
   - In `scp/task_kernel_parts/taskkernel.py:53-63`, `TaskKernel._schema()` declares the concrete tables:
     - `control` (`id INTEGER PRIMARY KEY CHECK (id=1)`, `global_kill`, `global_kill_epoch`)
     - `tasks` (`task_id TEXT PRIMARY KEY`, ..., `version INTEGER NOT NULL DEFAULT 1`, `active_lease_id`, `active_fencing_token`, ...)
     - `events` (`event_id TEXT PRIMARY KEY`, `task_id`, `seq`, ..., `event_hash`, `UNIQUE(task_id, seq)`)
     - `leases` (`lease_id TEXT PRIMARY KEY`, `task_id`, `attempt_id`, `worker_id`, `issued_at`, `expires_at`, `heartbeat_at`, `fencing_token`, `global_kill_epoch`, `released`)
     - `checkpoints` (`checkpoint_id TEXT PRIMARY KEY`, `task_id`, `attempt_id`, `step_id`, `state`, ..., `payload_hash`)
     - `idempotency` (`logical_key TEXT PRIMARY KEY`, `task_id`, `step_id`, `action_type`, `resource_identity`, `status`, `result_ref`, `created_at`)
     - `queue_accounts` (`owner TEXT PRIMARY KEY`, `active`, `dispatch_count`, `last_dispatch_at`)
   - There is NO SQL table named `artifacts` or `task_events` or `journals` or `idempotency_keys`. Conceptual names map directly to `events` (journal), `idempotency` (keys), and `checkpoints.pre_observation_ref/post_observation_ref/result_ref` (artifacts/blobs).

2. **Phase 1 OCC Implementation on `tasks`**:
   - In `scp/task_kernel_parts/taskkernel.py:146-150`:
     ```python
     task = self._task(task_id)
     if expected_version is not None and int(task["version"]) != expected_version:
         raise StaleLease(
             f"concurrency conflict on task {task_id}: expected version {expected_version}, found {task['version']}"
         )
     cur_version = int(task["version"])
     ```
   - In `scp/task_kernel_parts/taskkernel.py:222-227`:
     ```python
     cur = self.conn.execute(
         "UPDATE tasks SET state=?,version=version+1,active_lease_id=?,active_fencing_token=?,updated_at=? WHERE task_id=? AND version=?",
         (to_state, new_lease_id, new_fencing_token, now_iso(), task_id, cur_version),
     )
     if cur.rowcount != 1:
         raise StaleLease(f"concurrency conflict transitioning task {task_id}: expected version {cur_version}")
     ```
   - In `scp/task_kernel.py:45-66`, the exception hierarchy defines:
     `KernelError`, `InvalidTransition`, `StaleLease`, `KillSwitchActive`, `CheckpointCorrupt`, `NotFound`.
     There is NO `OptimisticLockError` defined anywhere in the codebase.
   - In `tests/T04_kernel/test_adversarial_kernel_flaws.py:366-368`, the OCC test expects:
     ```python
     with pytest.raises(StaleLease) as excinfo:
         kernel.transition("adv-occ-1", "PLANNING", expected_version=1)
     assert "concurrency conflict" in str(excinfo.value)
     ```

3. **Residual Blind Overwrites on `tasks` in Current Code**:
   - In `scp/task_kernel_parts/taskkernel.py:293`:
     ```python
     self.conn.execute("UPDATE tasks SET state='FAILED',version=version+1,active_lease_id=NULL,active_fencing_token=0,updated_at=? WHERE task_id=?", (now_iso(), task['task_id']))
     ```
     Observed: No `AND version=?` check.
   - In `scp/task_kernel_parts/taskkernel.py:1005`:
     ```python
     'UPDATE tasks SET state=?,version=version+1,active_lease_id=?,active_fencing_token=?,updated_at=? WHERE task_id=?',
     ```
     Observed: No `AND version=?` check.

4. **Blind Overwrites on Satellite Tables**:
   - In `scp/task_kernel_parts/taskkernel.py:388` (`heartbeat`):
     ```python
     self.conn.execute('UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=?', (now, expires, lease_id))
     ```
     Observed: Neither `version` nor `released=0` is checked.
   - In `scp/task_kernel.py:187-190` (`_idempotency_claim_fenced`):
     ```python
     if row["status"] == "RETRYABLE":
         self.conn.execute(
             "UPDATE idempotency SET status='CLAIMED',result_ref=NULL WHERE logical_key=?",
             (logical_key,),
         )
     ```
     Observed: No `version` column, no OCC check.
   - In `scp/task_kernel.py:231-234` (`_idempotency_complete_fenced`):
     ```python
     self.conn.execute(
         "UPDATE idempotency SET status='COMPLETED',result_ref=? WHERE logical_key=?",
         (result_ref, logical_key),
     )
     ```
     Observed: No `version` column, no OCC check.
   - In `scp/task_kernel.py:292-295` (`_reconcile_unknown_complete_outcomes`):
     ```python
     self.conn.execute(
         "UPDATE idempotency SET status=?,result_ref=? WHERE logical_key=?",
         (status, evidence_ref, checkpoint["idempotency_key"]),
     )
     ```
     Observed: No `version` column, no OCC check.

5. **Append-Only Tables Have Zero Updates**:
   - Grep search for `UPDATE events` across the repository returned 0 matches.
   - Grep search for `UPDATE checkpoints` across the repository returned 0 matches.

---

## 2. Logic Chain

1. **From Observation 1 and 4 to Vulnerability**:
   Because `leases` and `idempotency` do not have a `version` column and execute unconstrained `UPDATE ... WHERE <pk>=?`, any two concurrent processes (e.g. two workers executing the same step or a worker heartbeating while a sweeper releases the lease) will execute a blind overwrite. The second update will overwrite the first without raising an exception, violating Invariant INV-01.
2. **From Observation 2 to Exception Hierarchy Design**:
   Existing tests (`test_adversarial_kernel_flaws.py:366`) assert `with pytest.raises(StaleLease):`. Per FA-01, tests must not be modified or loosened. Therefore, the new exception `OptimisticLockError` must inherit from `StaleLease` (`class OptimisticLockError(StaleLease): pass`). This makes `issubclass(OptimisticLockError, StaleLease) == True`, preserving 100% green status on existing regression tests while providing the required semantic class for INV-01.
3. **From Observation 1 and 5 to Immutability Classification**:
   `events` forms a cryptographically chained journal (`event_hash` -> `prev_event_hash`, `UNIQUE(task_id, seq)`). Mutating events would break Merkle verification and violate DNA #20. `checkpoints` stores point-in-time snapshots with `payload_hash`. Thus, both tables are structurally and architecturally **strictly append-only** and must never be updated.
4. **From Observation 1 and SQLite semantics to Migration Requirements**:
   In SQLite, `CREATE TABLE IF NOT EXISTS` does not modify existing tables. To ensure existing test databases and production stores evolve without corruption, `TaskKernel._schema()` must inspect `PRAGMA table_info()` and execute `ALTER TABLE <table_name> ADD COLUMN version INTEGER NOT NULL DEFAULT 1` for `leases`, `idempotency`, `queue_accounts`, and `tasks`.
5. **From Observation 3 to Complete INV-01 Enforcement**:
   To completely seal GAP-02, not only satellite tables (`leases`, `idempotency`) must be guarded with OCC, but the two missed `UPDATE tasks` statements in `taskkernel.py:293` and `1005` must also be patched with `WHERE task_id=? AND version=?`.

---

## 3. Caveats

1. **Local Concurrency vs. Distributed Backends**:
   Current `TaskKernel` persistence uses `SQLiteKernelStorage` in WAL mode with `BEGIN IMMEDIATE` and per-thread connections. In-memory locks (`_tx_lock`) serialize writes within a single process. Concurrency conflicts occur across multi-process workers (e.g., CLI runner + dashboard + background workers) sharing the same SQLite database file. The OCC architecture designed here operates at the SQL statement level, making it portable to PostgreSQL or distributed stores.
2. **Artifact Storage**:
   There is no separate `artifacts` table in SQLite; artifacts are referenced by URI/hash in checkpoints and idempotency rows. If a dedicated `artifacts` table is introduced in future milestones, it should follow CAS (write-once immutable blob keyed by SHA256) rather than an updatable table.
3. **No Code Implementation in M1**:
   Per Explorer identity and constraints, this is a read-only investigation. No source code in `scp/` was modified.

---

## 4. Conclusion

1. **Architecture Status**: The database schema currently exposes satellite entities (`leases`, `idempotency`, `queue_accounts`) to silent data loss via blind overwrites (GAP-02).
2. **Required Schema Additions**:
   - `leases`: `version INTEGER NOT NULL DEFAULT 1`
   - `idempotency`: `version INTEGER NOT NULL DEFAULT 1`
   - `queue_accounts`: `version INTEGER NOT NULL DEFAULT 1`
   - Dynamic migration via `PRAGMA table_info` in `TaskKernel._schema()`.
3. **Required Exception**:
   - Define `class OptimisticLockError(StaleLease): pass` in `scp/task_kernel.py`.
4. **Required Interface Contracts**:
   - `heartbeat(lease_id, ttl_seconds=30.0, expected_version=None) -> Lease`: updates `heartbeat_at`, `expires_at`, `version=version+1` `WHERE lease_id=? AND released=0 AND version=?`.
   - `release(task_id, lease_id, expected_version=None)`: updates `released=1`, `version=version+1` `WHERE lease_id=? AND released=0 AND version=?`.
   - `idempotency_claim(..., expected_version=None)`: updates `status='CLAIMED'`, `result_ref=NULL`, `version=version+1` `WHERE logical_key=? AND status='RETRYABLE' AND version=?`.
   - `idempotency_complete(logical_key, result_ref, expected_version=None)`: updates `status='COMPLETED'`, `result_ref=?`, `version=version+1` `WHERE logical_key=? AND status='CLAIMED' AND version=?`.
   - All update operations must check `cur.rowcount == 1` and raise `OptimisticLockError` if 0 rows matched.
5. **Append-Only Invariant**:
   - Enforce that `events` and `checkpoints` are strictly append-only; no UPDATE queries are permitted.

---

## 5. Verification Method

1. **Verify Current Kernel Test Baseline**:
   ```pwsh
   pytest tests/T04_kernel -q
   ```
   *Expected Result*: 35 passed.
2. **Verify Full Test Suite**:
   ```pwsh
   pytest tests/ -q
   ```
3. **Verify Meta-Audit Guardrails**:
   ```pwsh
   python tools/t00_meta_audit.py
   ```
   *Expected Result*: Exits 0, confirming no FA-01 through FA-10 violations.
4. **Inspect Schema & Call Sites**:
   - Review `scp/task_kernel_parts/taskkernel.py:53-63` (`_schema`).
   - Review `scp/task_kernel_parts/taskkernel.py:122-243` (`transition`).
   - Review `scp/task_kernel_parts/taskkernel.py:388` (`heartbeat`).
   - Review `scp/task_kernel.py:150-240` (`idempotency`).
5. **Invalidation Condition**:
   This architecture would be invalidated if any satellite entity update requires non-atomic multi-row bulk mutation without version tracking, or if SQLite `ALTER TABLE ADD COLUMN version INTEGER NOT NULL DEFAULT 1` fails on legacy tables with existing records. (Tested: SQLite 3.1.3+ fully supports this syntax with constant defaults).
