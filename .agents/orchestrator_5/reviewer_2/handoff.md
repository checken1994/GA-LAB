# HANDOFF REPORT: ADVERSARIAL & QUALITY REVIEW OF CALLER PROTOCOLS & BRIDGES (GAP-07)

**Author**: Reviewer 2 (Caller Protocols & Bridge Reviewer)  
**Roles**: Reviewer, Adversarial Critic  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\orchestrator_5\reviewer_2`  
**Target Workspace**: `c:\Users\check\Downloads\scp`  
**Parent Agent**: `parent` (`967399d1-d666-4dce-899b-4c2468b6dd91`)  
**Verdict**: **REQUEST_CHANGES**  
**Date**: 2026-09-07T14:18:00+07:00  

---

## 1. Observation

### 1.1 Critical Defect: Pre-Dispatch Policy Rejection Cascades to Recovery Exception
- **File**: `scp/hands/task_kernel_bridge.py` lines 435–456
- **Code observed**:
  ```python
  if self._policy_blocked_before_dispatch(result):
      self.kernel.transition(
          task_id,
          "FAILED",
          actor="hands-kernel-bridge",
          reason="hands_policy_denied_before_dispatch",
          payload={"action": action},
      )
      self.kernel.release(task_id, lease.lease_id)
      lease_active = False
      return {**result, "safeToRetry": False, "kernel": self._public_kernel(task_id, lease.lease_id)}
  ```
- **Interacting Code**: `scp/task_kernel_parts/taskkernel.py` lines 334–342 (`TaskKernel.transition`):
  ```python
  if to_state in {"RUNNING", "WAITING_TOOL", "VERIFYING", "CHECKPOINTED"}:
      new_lease_id = caller_lease
      new_fencing_token = token
  else:
      new_lease_id = None
      new_fencing_token = 0
      if caller_lease:
          self.conn.execute("UPDATE leases SET released=1,version=version+1 WHERE lease_id=? AND released=0", (caller_lease,))
          self.conn.execute(
              "UPDATE queue_accounts SET active=CASE WHEN active>0 THEN active-1 ELSE 0 END,version=version+1 WHERE owner=?",
              (task["owner"],),
          )
          if hasattr(self, "_bound_leases"):
              self._bound_leases.pop(task_id, None)
  ```
- **Crash Point**: In `scp/task_kernel_parts/taskkernel.py` line 466 (`_assert_lease`), called by `release()`:
  ```python
  if lease['released']:
      raise OptimisticLockError(
          f"lease {lease_id} has already been released",
          table="leases",
          entity_id=lease_id,
      )
  ```
- **Observed Result & Error**: Calling `TaskKernelHandsBridge.execute("pc.write_file", ..., capability_token=None)` returns:
  ```json
  {
    "success": false,
    "action": "pc.write_file",
    "error": "Hands bridge could not persist unknown state: OptimisticLockError",
    "requiresRecovery": true,
    "safeToRetry": false,
    "kernel": {
      "taskId": "hands-321b0542e7696510998b92f0078057bd",
      "state": "FAILED",
      "version": 7,
      "leaseId": "lease_2d71e2f4697a378c44122c00"
    }
  }
  ```
  Verified via Level 1 exploit probe script `.agents/orchestrator_5/reviewer_2/adversarial_bridge_probe.py`.

### 1.2 Major Defect: Planner Step Validation Discards `capabilityToken`
- **File**: `scp/hands/planner.py` lines 284–300 (`_validate_step`)
- **Code observed**:
  ```python
  return {
      "stepId": step_id,
      "action": action,
      "params": params,
      "capabilityLevel": raw_capability,
      "approved": bool(raw.get("approved", False)),
      "dryRun": bool(raw.get("dryRun", False)),
      "dependsOn": depends_on,
      "precondition": precondition,
      "postcondition": postcondition,
      "retryPolicy": retry_policy,
      "state": "PLANNED",
      "attempts": 0,
      "evidence": {},
      "error": "",
  }
  ```
  `_validate_step` strictly projects only known keys. Any `capabilityToken` or `capability_token` supplied inside `steps` when calling `create_plan()` is omitted. As a result, `step.get("capabilityToken")` in `_run_plan_locked` (line 459) and `_run_dag_step` (line 573) is unconditionally `None` for all plans created via `create_plan()`.

### 1.3 Verified Test Integrity (Zero Assertions Loosened, Zero Tests Skipped)
- **File**: `tests/T04_kernel/test_kernel_p1_regressions.py`
  - All 5 test functions present: `test_bridge_duplicate_request_returns_replayed_response`, `test_orphan_sweep_keeps_fresh_lease_and_reconciles_stale_one`, `test_checkpoint_event_does_not_poison_rebuild_projection`, `test_checkpoint_still_rejects_invalid_state`, `test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch`.
  - Exactly 0 assertions were loosened or removed (FA-01 compliant).
  - Exactly 0 tests were deleted or skipped (FA-02 compliant).
- **File**: `tests/T09_golden_task/test_golden_a_agent_os.py`
  - `test_golden_a_agent_os_real_execution_flow`: all 14 assertions remain 100% intact.
- **Verification Commands Executed**:
  1. `pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py -v`:
     Output: `6 passed in 3.60s` (exit code 0).
  2. `python tools/t00_meta_audit.py`:
     Output: `[T00 Meta-Audit] All integrity checks passed (0 new regressions)` (exit code 0).

---

## 2. Logic Chain

1. **Step 1 (Root Cause of Defect 1)**:
   In `scp/hands/task_kernel_bridge.py` line 437, when a pre-dispatch policy rejection occurs (e.g. `CapabilityRequiredError`), the bridge calls:
   `self.kernel.transition(task_id, "FAILED", ...)` (Observation 1.1).
2. **Step 2 (Automatic Lease Release in Kernel)**:
   `TaskKernel.transition()` (`taskkernel.py` lines 328–342) specifies that whenever transitioning to a non-leased state (such as `"FAILED"`, `"COMPLETED"`, `"CANCELLED"`), the database transaction atomically releases the active lease (`UPDATE leases SET released=1, version=version+1...`), pops `_bound_leases[task_id]`, and sets `tasks.active_lease_id = NULL`.
3. **Step 3 (The Double-Release Collision)**:
   At line 451, `task_kernel_bridge.py` redundantly calls `self.kernel.release(task_id, lease.lease_id)`. Inside `release()`, `_assert_lease` checks `if lease['released']: raise OptimisticLockError("lease ... has already been released")`.
4. **Step 4 (Cascade into UNKNOWN / Recovery)**:
   Because this `OptimisticLockError` is uncaught inside the `if self._policy_blocked_before_dispatch` block, control jumps to the outer `except Exception as exc:` at line 527.
   Since `dispatch_started` was set to `True` at line 413, line 533 calls `self._unknown_result(...)`. Inside `_unknown_result()`, it attempts to record an `UNKNOWN` state on the task, which raises `InvalidTransition("terminal task is immutable")`. Line 549 catches this secondary failure and returns:
   `{"error": "Hands bridge could not persist unknown state: OptimisticLockError", "requiresRecovery": True, ...}`.
5. **Step 5 (Violation of Review Requirement)**:
   The dispatch explicitly mandates: *"Ensure pre-dispatch policy rejections transition to FAILED and never cascade into UNKNOWN."*
   Currently, every pre-dispatch policy rejection in `TaskKernelHandsBridge` fails with `requiresRecovery: True` and obscure `OptimisticLockError`, completely breaking callers and downstream reconcilers.
6. **Step 6 (Root Cause of Defect 2)**:
   `planner.py` added `step_token = step.get("capabilityToken") or step.get("capability_token") or ...` in `_run_plan_locked` and `_run_dag_step`. But `_validate_step()` filters out all fields not explicitly enumerated in its return dict (Observation 1.2). Therefore, step-level tokens passed in `create_plan()` are silently dropped.

---

## 3. Caveats

1. **Test Suite Blind Spot**:
   `tests/T04_kernel/test_kernel_p1_regressions.py` tests successful dispatches with valid tokens and replay deduplication, but did not have a test case for `bridge.execute(..., capability_token=None)` on a mutating action. Thus, this double-release bug was masked and not caught by the existing regression test suite (`PASS != TRUE`).
2. **Review-Only Role Discipline**:
   In accordance with the non-negotiable constraint *"Review-only — do NOT modify implementation code"*, this reviewer did not edit `task_kernel_bridge.py` or `planner.py`. A fix must be applied by the core implementer (Worker 2).

---

## 4. Conclusion

**Verdict**: **REQUEST_CHANGES**

The caller protocol and bridge implementation cannot be approved in its current state due to 1 Critical Defect and 1 Major Defect:

1. **[CRITICAL] Double-Lease Release on Pre-Dispatch Policy Rejection**:
   - **Location**: `scp/hands/task_kernel_bridge.py` line 451
   - **Problem**: `self.kernel.release(task_id, lease.lease_id)` crashes with `OptimisticLockError` because `transition(task_id, "FAILED")` has already released the lease atomically.
   - **Required Fix**: In `scp/hands/task_kernel_bridge.py`:
     ```python
     if self._policy_blocked_before_dispatch(result):
         self.kernel.transition(
             task_id,
             "FAILED",
             actor="hands-kernel-bridge",
             reason="hands_policy_denied_before_dispatch",
             payload={"action": action},
         )
         lease_active = False
         return {**result, "safeToRetry": False, "kernel": self._public_kernel(task_id, lease.lease_id)}
     ```
     (Delete the redundant line 451 `self.kernel.release(task_id, lease.lease_id)`).

2. **[MAJOR] `_validate_step()` Discards `capabilityToken`**:
   - **Location**: `scp/hands/planner.py` line 284
   - **Problem**: Step dictionary stripping drops `capabilityToken` during `create_plan()`.
   - **Required Fix**: Include `"capabilityToken": raw.get("capabilityToken") or raw.get("capability_token")` in the dictionary returned by `_validate_step()`.

3. **[MANDATORY TEST ADDITION]**:
   Add a regression test in `tests/T04_kernel/test_kernel_p1_regressions.py` verifying that calling `bridge.execute("pc.write_file", ..., capability_token=None)` returns `success=False`, `error` containing `CapabilityRequiredError`, `requiresRecovery=False`, and leaves the task cleanly in `FAILED` state with lease released.

---

## 5. Verification Method

### 5.1 Independent Reproduction of Exploit Probe
Run the standalone probe authored by Reviewer 2:
```bash
python .agents/orchestrator_5/reviewer_2/adversarial_bridge_probe.py
```
- **Observed Behavior (Unfixed)**: Exits with `res.requiresRecovery: True` and `res.error: Hands bridge could not persist unknown state: OptimisticLockError`.
- **Expected Behavior (Fixed)**: Must return `res.requiresRecovery: False` (or None), `CapabilityRequiredError` in `res.error`, and `res.kernel.state == 'FAILED'`.

### 5.2 Test Suite Verification Commands
```bash
# 1. Affected kernel & golden task tests
pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py -v

# 2. Meta-Audit Authority
python tools/t00_meta_audit.py

# 3. Full pytest suite
pytest tests/ -q
```

### 5.3 Invalidation Conditions
- Any pre-dispatch policy rejection returning `requiresRecovery: True`.
- Any error message mentioning `OptimisticLockError` on policy-blocked executions.
- Any loosened assertion in `test_kernel_p1_regressions.py` or `test_golden_a_agent_os.py`.
