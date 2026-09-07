# Progress Log: Phase 1 Evolution - GAP-01 ContextVar Leak & Database-Level Atomic Fencing

## Status: COMPLETE
- **Assigned Worker**: implementer@swe_light
- **Target Vulnerability**: GAP-01 (ContextVar Leak & In-Memory Lease Bypass in `scp/task_kernel.py`)
- **Target Invariant**: INV-01 (Atomic Fencing & Database-Level Boundary in `scp/task_kernel_parts/taskkernel.py`)
- **Strict Compliance**: Zero-Trust, Fail-Closed, FA-01 through FA-10.

---

## Execution Checklist
- [x] Read `GA.md` on main
- [x] Read `SKILL.md`: `scp-dna`
- [x] Read `SKILL.md`: `scp-task-kernel-review`
- [x] Analyze `DELTA_AUDIT_REPORT.md` & `probe_kernel_flaws.py`
- [x] Establish Line-by-line Call Graph / Execution Trace
- [x] Reproduce GAP-01 & Concurrency Flaws via `probe_kernel_flaws.py`
- [x] Implement Root Cause Fix in `scp/task_kernel_parts/taskkernel.py` & `scp/task_kernel.py`
- [x] Eliminate multi-process lock starvation in `scp/kernel_storage.py`
- [x] Re-run `probe_kernel_flaws.py` to verify flaw elimination (Terminal PASS)
- [x] Run full pytest suite `pytest tests/` (411/411 passed in 105s)
- [x] Run `python tools/t00_meta_audit.py` (0 new regressions)
- [x] Write `handoff.md` and send final report to caller

---

## Detailed Execution Trace & Call Graph

### 1. The Call Graph & Flaw Analysis (GAP-01)
Before our fix, lease enforcement relied entirely on an in-memory `contextvars.ContextVar`:
```
Caller A (Worker Thread) -> TaskKernel.claim() -> _claim_with_lease_context()
    -> stores (id(kernel), task_id) in _LEASE_CONTEXT

Caller B (Rogue Worker / Different Thread / Cross-Process) -> TaskKernel.transition()
    -> _transition_fenced_by_bound_lease()
    -> lease_id = _bound_lease_id(self, task_id)  <-- Returns None!
    -> if not lease_id:
           return _original_transition(self, task_id, to_state, ...)  <-- BYPASS!
```
Furthermore, the `tasks` SQLite table had no columns for lease authority (`active_lease_id`, `active_fencing_token`). State transitions simply executed:
```sql
UPDATE tasks SET state=?, version=version+1, updated_at=? WHERE task_id=?
```
This allowed:
1. **Flaw 1 (Rogue Worker Hijack)**: Any process or thread without lease context could mutate a leased running task.
2. **Flaw 2 (Expired Lease Bypass)**: Even if a lease expired on wall-clock, calling `transition()` from an unleased context bypassed `_assert_lease()`.
3. **Flaw 3 (SQLite Lock Contention)**: Concurrency retry loop was limited to 5 attempts * 0.05s = 0.25s, crashing concurrent processes.
4. **Flaw 4 (Lost Updates / Blind Overwrite)**: Missing `WHERE version=?` optimistic locking predicate allowed concurrent overwrites without conflict detection.

### 2. Implementation: Database Boundary Enforcement (INV-01)
We moved all lease gating into the database schema and atomic SQL statements in `scp/task_kernel_parts/taskkernel.py`:
1. **Schema Migration**:
   - Added `active_lease_id TEXT` and `active_fencing_token INTEGER NOT NULL DEFAULT 0` to the `tasks` table.
   - Automatically executed via `_schema()` with idempotent `ALTER TABLE` migrations.
2. **Atomic Gating in `transition()`**:
   - Gated every transition on database state: if `task['state']` is in `{LEASED, RUNNING, WAITING_TOOL, VERIFYING, CHECKPOINTED}` or `task['active_lease_id']` is present, caller MUST possess active lease authority matching the database row (or have `_system_authority=True` during boot recovery).
   - Validated lease freshness via `self._assert_lease()` against wall-clock expiry, kill switch, and fencing token.
   - Optimistic Concurrency Control (OCC): Transition SQL enforces `WHERE task_id=? AND version=?`. If version drifts or another worker committed first, `cur.rowcount != 1` raises `StaleLease`.
3. **Atomic Operations across Kernel**:
   - `claim()`, `claim_next()`, `start()`, `release()`, `expire_leases()`, `commit_completed()`, `set_task_kill()`, `enter_reconciling()`, `reconcile_unknown()` all maintain `active_lease_id`, `active_fencing_token`, and OCC atomically.
4. **Eliminated `_LEASE_CONTEXT` Leak**:
   - Removed `ContextVar` and monkey patching of `claim`, `claim_next`, `transition`, `recover_on_boot`, `close` in `scp/task_kernel.py`.
   - Idempotency checks in `scp/task_kernel.py` now reference kernel instance bound leases and verify against DB.
5. **Storage Resilience**:
   - In `scp/kernel_storage.py`, upgraded retry count to 25 with exponential backoff (`0.05 * min(attempt + 1, 4)`), allowing multi-process SQLite transactions up to 5s lock contention without crashing.

---

## Verification Records

### 1. Probe Verification (`probe_kernel_flaws.py`)
Raw execution output:
```
[Process-1 (Long TX)] BEGIN IMMEDIATE acquired. Holding for 0.5s...
[Process-1 (Long TX)] COMMIT completed.
[Process-2 (Quick TX)] BEGIN IMMEDIATE acquired. Holding for 0.05s...
[Process-2 (Quick TX)] COMMIT completed.
STARTING TASK KERNEL CONCURRENCY & DURABILITY PROBE (FA-09)
======================================================================
PROBE 1: Rogue Worker Hijack via In-Memory _LEASE_CONTEXT Bypass
======================================================================
[Worker A] Claimed lease lease_7b5672d8f052c57a8b238836 (token=1).
[Worker A] Current task state: RUNNING
[Worker B] Connected to same database without lease.
[Worker B BLOCKED BY INV-01] StaleLease: transition from RUNNING requires active lease authority
[Worker A SUCCESS] Legitimate worker transitioned to: VERIFYING

======================================================================
PROBE 2: Expired Lease Bypass via Fresh Context (Unfenced Transition)
======================================================================
[k1] Task started with 1.0s TTL lease (token=1).
[k1] 1.2 seconds elapsed. Lease has expired on wall-clock.
[k1 correctly blocked on expired lease] StaleLease: lease_2b1ffc09e65e75ac5fc3c805
[k2 BLOCKED BY INV-01] StaleLease: transition from RUNNING requires active lease authority

======================================================================
PROBE 3: Multi-Process SQLite BEGIN IMMEDIATE Lockout Contention
======================================================================

======================================================================
PROBE 4: Missing Optimistic Lock (Blind Version Increment Overwrite)
======================================================================
[Initial] Task created with version=1
[After Worker 1] State: PLANNING, Version: 2
[Worker 2 BLOCKED BY OCC] StaleLease: concurrency conflict on task task-omega-4: expected version 1, found 2

ALL PROBES COMPLETED.
```

### 2. Full Test Suite (`pytest tests/`)
Raw output:
```
======================= 411 passed in 105.19s (0:01:45) =======================
```
All 411 tests passed with 0 failures across all modules (T00 through T11).

### 3. Meta-Audit (`tools/t00_meta_audit.py`)
Raw output:
```
[T00 Meta-Audit] Starting Test-Integrity Regression Authority...
[T00 Meta-Audit] Trusted Base: origin/main
[T00 Meta-Audit] Collecting baseline pytest nodeids (origin/main)...
[T00 Meta-Audit] Collecting candidate pytest nodeids...
[T00 Meta-Audit] All integrity checks passed (0 new regressions).
```
Zero test regressions, zero loosened assertions, zero skipped tests.
