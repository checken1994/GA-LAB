# Handoff Report: Round 2 Adversarial Review & Refinement (GAP-11)

**Role:** Refinement & Adversarial Reviewer Round 2 (`teamwork_preview_implementer_swe3_r2`)  
**Parent Orchestrator:** `teamwork_preview_swe_3` (ID: `d9fda0b3-d21c-40a9-a9e6-b8512cec0a57`)  
**Date:** 2026-09-08T00:56:00+07:00  
**Target File:** `scp/task_kernel_parts/taskkernel.py` & `tests/T04_kernel/test_adversarial_kernel_flaws.py`  
**Test Suite:** `tests/T04_kernel/` (73/73 PASS, 100%)  
**Meta-Audit:** `tools/t00_meta_audit.py` (0 regressions)  
**Adversarial Probe Suite:** `tools/probes/probe_gap11_r2_watchdog_race.py` (6/6 PASS, terminal & SQLite proven)

---

## 1. Executive Summary

In Round 2, an adversarial campaign was mounted specifically targeting the **concurrent interaction between the lease expiration watchdog (`expire_leases()`) and task completion commit (`commit_completed()`)**:

1. **Passive TTL Expiry (Pre-Watchdog Commit Attempt):**  
   - An adversarial worker with an expired lease (`expires_at <= now`) attempts `commit_completed()` before the periodic watchdog runs.  
   - *Result:* `_assert_lease()` detects expired TTL and raises `StaleLease`. The task remains strictly in `VERIFYING` with zero state corruption or unauthorized `COMPLETED` events.
2. **Active Watchdog Expiry on `VERIFYING` Task (Transition to `HUMAN_REVIEW`):**  
   - The watchdog (`expire_leases()`) runs, transitions the task to `HUMAN_REVIEW`, resets `active_lease_id = NULL`, `active_fencing_token = 0`, marks `released = 1` on the lease, and appends `LEASE_EXPIRED`.  
   - The stale worker subsequently attempts `commit_completed()`.  
   - *Result:* Blocked fail-closed with `OptimisticLockError: lease ... has already been released` (subclass of `StaleLease`). The task remains in `HUMAN_REVIEW`, version count is preserved, and zero `TASK_COMPLETED` events are written.
3. **Active Watchdog Expiry on `RUNNING` Task (Transition to `RECOVERING`):**  
   - The watchdog runs on a `RUNNING` task, transitioning it to `RECOVERING`.  
   - The stale worker subsequently attempts `commit_completed()`.  
   - *Result:* Blocked fail-closed with `OptimisticLockError: lease ... has already been released`. Task remains in `RECOVERING`.
4. **Explicit Lease Revocation via `release()`:**  
   - A supervisor or caller revokes/releases the lease.  
   - The stale worker subsequently attempts `commit_completed()`.  
   - *Result:* Blocked fail-closed with `OptimisticLockError`. Task state remains unmodified.
5. **Fencing Token Staleness after Task Re-Leasing:**  
   - A task's lease expires; the task recovers and is re-queued and claimed by Worker 2 with a higher fencing token.  
   - Stale Worker 1 (with old fencing token) attempts `commit_completed()`.  
   - *Result:* Blocked fail-closed with `OptimisticLockError` / `StaleLease`. Worker 2's active lease and fencing token remain untouched in SQLite.
6. **Multithreaded Concurrent Race (Watchdog vs Worker):**  
   - 10-20 concurrent threads running across multiple tasks racing `expire_leases()` against `commit_completed()`.  
   - *Result:* Every task cleanly resolves into either `COMPLETED` (if worker won race prior to lease expiration) or `HUMAN_REVIEW` (if watchdog expired lease prior to commit). No split-brain states, no duplicate events, and `PRAGMA integrity_check` passes 100% `ok`.

Three new permanent adversarial tests were added to `tests/T04_kernel/test_adversarial_kernel_flaws.py`, raising the T04 suite count from 70 to 73 tests (100% PASS).

---

## 2. Adversarial Probe Evidence (FA-12 Empirical Proof)

Executed `python -m tools.probes.probe_gap11_r2_watchdog_race` on Windows terminal:

```text
[PROBE R2] Starting Lease Expiration Watchdog vs commit_completed() Adversarial Probe...

--- Attack 1: Passive TTL expiry before watchdog runs ---
[R2-1] Passive TTL expiry commit_completed() BLOCKED with StaleLease: lease_7b1a1c16ab656a3f44ec91f9
[R2-1] SQLite verified: state remains VERIFYING, zero COMPLETED events in journal.

--- Attack 2: Active watchdog expiry in VERIFYING (HUMAN_REVIEW) ---
[R2-2] Watchdog expired lease; task transitioned to HUMAN_REVIEW, lease released=1
[R2-2] Stale worker commit_completed() BLOCKED fail-closed: OptimisticLockError: lease lease_9c23258a5e11e99fb3b2f789 has already been released
[R2-2] SQLite verified: state remains HUMAN_REVIEW, version untouched, zero COMPLETED events.

--- Attack 3: Active watchdog expiry in RUNNING (RECOVERING) ---
[R2-3] Watchdog expired running lease; task transitioned to RECOVERING
[R2-3] Stale commit_completed() on RECOVERING task BLOCKED: OptimisticLockError: lease lease_8250445f06b01e35c98dd6d2 has already been released
[R2-3] SQLite verified: state remains RECOVERING.

--- Attack 4: Explicit lease release() before commit ---
[R2-4] Lease explicitly released via kernel.release()
[R2-4] Revoked lease commit_completed() BLOCKED: OptimisticLockError: lease lease_1e8cf14cbb5bca4e48db10eb has already been released
[R2-4] SQLite verified: task state intact in VERIFYING, lease released=1.

--- Attack 5: Fencing token staleness after task re-claim ---
[R2-5] Task re-claimed by worker 2 with fencing token 2 (w1 token: 1)
[R2-5] Stale fencing token commit_completed() BLOCKED: OptimisticLockError: lease lease_d492eec1ee65c6c73ee436db has already been released
[R2-5] SQLite verified: worker 2's active lease and fencing token preserved.

--- Attack 6: Multithreaded concurrent race (10 tasks, 20 threads) ---
[R2-6] Concurrent race completed: 1 won by commit, 9 won by watchdog.
[R2-6] 100% of tasks cleanly resolved without state corruption or bypass.
[R2-6] SQLite PRAGMA integrity_check: ok

ALL R2 LEASE EXPIRATION WATCHDOG RACE ADVERSARIAL CHECKS PASSED!
```

---

## 3. Test Verification Record

### 3.1 Pytest Suite Execution
Command: `python -m pytest tests/T04_kernel/ -q`
```text
........................................................................ [ 98%]
.                                                                        [100%]
73 passed in 7.02s
```
*73 passed (66 baseline + 1 r0 fix test + 3 r1 adversarial tests + 3 r2 adversarial tests).*

### 3.2 Meta-Audit Verification
Command: `python tools/t00_meta_audit.py`
*(Verified 0 regressions against origin/main)*
