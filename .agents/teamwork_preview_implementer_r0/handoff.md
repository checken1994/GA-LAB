# Handoff Report: Phase 1 Evolution - GAP-01 Fix & INV-01 Atomic Fencing

## 1. Executive Summary
- **Task**: Eliminate vulnerability **GAP-01** (ContextVar Leak & In-Memory Lease Bypass in `scp/task_kernel.py`) and enforce **INV-01** (Atomic Lease Fencing & Database-Level Boundary in `scp/task_kernel_parts/taskkernel.py`).
- **Worker**: implementer@swe_light
- **Status**: COMPLETE & VERIFIED.
- **Compliance**: Adheres strictly to Zero-Trust, Fail-Closed, and FA-01 through FA-10. No tests skipped, deleted, or assertions loosened.

---

## 2. Root Cause Analysis (GAP-01)
Previously, `scp/task_kernel.py` wrapped `TaskKernel.transition` with `_transition_fenced_by_bound_lease`, which checked:
```python
lease_id = _bound_lease_id(self, task_id)
if not lease_id:
    return _original_transition(self, task_id, to_state, actor, reason, payload, event_id)
```
Where `_bound_lease_id` inspected an in-memory `contextvars.ContextVar _LEASE_CONTEXT`. This violated fundamental system security principles:
1. **Context Boundary Leak**: Any caller from another thread, a fresh process, or a subtask where `_LEASE_CONTEXT` was empty received `lease_id = None`. The system then quietly defaulted to `_original_transition`, executing a blind state update without any lease verification.
2. **Missing Database-Level Invariants**: The underlying `tasks` SQLite table had no columns tracking `active_lease_id` or `active_fencing_token`. The database could not enforce that a task in `RUNNING`, `LEASED`, `WAITING_TOOL`, `VERIFYING`, or `CHECKPOINTED` state was only mutable by its current valid leaseholder.
3. **Blind Overwrites (Lost Updates)**: State transitions in `_original_transition` executed `UPDATE tasks SET state=?, version=version+1 WHERE task_id=?` without checking the expected version, allowing concurrent stale workers to overwrite newer transitions.
4. **SQLite Concurrency Starvation**: Storage lock retry was capped at 5 attempts * 0.05s = 0.25s, causing fast `OperationalError: database is locked` failures when multiple processes attempted transactions concurrently.

---

## 3. Changes Implemented

### A. `scp/task_kernel_parts/taskkernel.py`
1. **Schema & Migration**:
   - Added `active_lease_id TEXT` and `active_fencing_token INTEGER NOT NULL DEFAULT 0` columns to `tasks` table in `_schema()`.
   - Idempotently adds these columns to existing databases on initialization.
2. **In-Kernel Lease Authority Tracking**:
   - Initialized `self._bound_leases: dict[str, str]` and `self._system_authority: bool = False` in `TaskKernel.__init__`.
   - `claim()` and `claim_next()` record `active_lease_id` and `active_fencing_token` into `tasks` table with OCC (`WHERE task_id=? AND version=?`) and store in `self._bound_leases`.
   - `start()` checks and records lease into DB with OCC and updates `self._bound_leases`.
3. **Database-Level Transition Gating & OCC**:
   - Integrated WHY Gate validation directly into `TaskKernel.transition`.
   - Enforced database lease boundary: If task is in `{LEASED, RUNNING, WAITING_TOOL, VERIFYING, CHECKPOINTED}` or `task['active_lease_id']` is set in DB:
     - If not running under `self._system_authority`: caller MUST have active lease authority in `self._bound_leases` matching the database row. If not, raises `StaleLease`.
     - Revalidates lease via `self._assert_lease()` against wall-clock expiry, task kill switch, and fencing token.
   - Added Optimistic Concurrency Control (OCC): Transition updates execute `UPDATE tasks SET state=?, version=version+1, active_lease_id=?, active_fencing_token=?, updated_at=? WHERE task_id=? AND version=?`. If version does not match, `cur.rowcount != 1` raises `StaleLease`.
   - If transitioning to a terminal state (`COMPLETED`, `FAILED`, `CANCELLED`) or idle state (`QUEUED`, `WAITING_APPROVAL`, `HUMAN_REVIEW`, `RECOVERING`), clears `active_lease_id` and `active_fencing_token` to `NULL`/0 and clears `self._bound_leases`.
4. **Consistent Kernel Operations**:
   - Updated `expire_leases()`, `release()`, `record_action_dispatched()`, `enter_reconciling()`, `reconcile_unknown()`, `commit_completed()`, `set_task_kill()`, `auto_reconcile_orphans()` to maintain `active_lease_id`, `active_fencing_token`, and OCC atomically.
   - `recover_on_boot()` runs with `self._system_authority = True`, releases dead worker leases in DB, and safely cleans in-flight tasks without needing stale worker context.
   - `rebuild_projection()` now runs inside a transaction with `version = version + 1`.

### B. `scp/task_kernel.py`
1. **Eliminated `ContextVar` Leak**:
   - Completely removed `contextvars` import and eliminated `_LEASE_CONTEXT`, `_bind_lease_context`, `_bound_lease_id`, `_without_kernel_lease_context`, `_claim_with_lease_context`, `_claim_next_with_lease_context`, `_transition_fenced_by_bound_lease`, `_recover_on_boot_with_system_authority`, `_close_with_lease_context_cleanup`.
   - Removed monkey-patching of `TaskKernel.claim`, `TaskKernel.claim_next`, `TaskKernel.transition`, `TaskKernel.recover_on_boot`, `TaskKernel.close`.
2. **Idempotency Lease Fencing**:
   - Updated `_idempotency_claim_fenced` and `_idempotency_complete_fenced` to inspect `getattr(self, '_bound_leases', {})` and verify against DB rows.
   - Updated `_reconcile_unknown_complete_outcomes` to enforce OCC `WHERE task_id=? AND version=?` and clear `active_lease_id`.

### C. `scp/kernel_storage.py`
- Upgraded `SQLiteKernelStorage.begin()` retry count to 25 with exponential backoff (`0.05 * min(attempt + 1, 4)`), allowing multi-process SQLite transactions up to 5 seconds of lock contention without raising `OperationalError: database is locked`.

---

## 4. Verification Record

### Verification 1: Concurrency & Flaws Probe (`probe_kernel_flaws.py`)
Ran `python .agents/teamwork_preview_explorer_survey_1/probe_kernel_flaws.py`:
- **Probe 1 (Rogue Worker Hijack)**: Worker B connected to same DB without lease attempted `transition('task-omega-1', 'HUMAN_REVIEW')`.
  - **Result**: BLOCKED BY INV-01: `StaleLease: transition requires active lease authority for task task-omega-1`.
- **Probe 2 (Expired Lease Bypass)**: Expired lease attempted transition from fresh context without lease.
  - **Result**: BLOCKED BY INV-01: `StaleLease: transition requires active lease authority for task task-omega-2`.
- **Probe 3 (Multi-Process SQLite Lockout)**: Two concurrent OS processes with 0.5s write lock and 0.05s lock.
  - **Result**: PASSED. Both processes acquired locks and committed without collision or crash.
- **Probe 4 (Missing Optimistic Version Lock)**: Worker 2 attempted transition with stale expected version.
  - **Result**: BLOCKED BY OCC: `StaleLease: concurrency conflict on task task-omega-4: expected version 1, found 2`.

### Verification 2: Full Test Suite (`pytest tests/`)
Ran `pytest tests/`:
- **Result**: **411 passed in 105.19s** (100% of collected tests passed).
- Zero failures, zero crashes across all test suites (T00 through T11).

### Verification 3: Meta-Audit (`tools/t00_meta_audit.py`)
Ran `python tools/t00_meta_audit.py`:
- **Result**: **All integrity checks passed (0 new regressions)**.
- Baseline debt was unchanged (5 historical items in external audit and sandbox).
- No assertions loosened, no tests deleted or skipped.

---

## 5. Known Limitations & Next Steps
- **Next Phase (Phase 2)**:
  - Extend lease fencing into `TaskKernelAdapter` and distributed worker heartbeat loops to handle long-running tool execution with fine-grained lease renewals.
  - Benchmark OCC throughput under heavy multi-threaded stress testing.
