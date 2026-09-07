# HANDOFF REPORT: TASKKERNEL BRIDGE LEASE LIFECYCLE INVESTIGATION & REMEDIATION SPECIFICATION

**Author**: Explorer 4 (TaskKernel Bridge Lease Lifecycle Specialist)  
**Target Workspace**: `c:\Users\check\Downloads\scp`  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_4`  
**Parent Agent**: `parent` (`967399d1-d666-4dce-899b-4c2468b6dd91`)  
**Date**: 2026-09-07T07:25:00Z  
**Milestone**: GAP-07 Iteration 2  
**Handoff Type**: Hard (Investigation Complete — Remediation Specification Delivered)  
**Governing Invariants**: INV-AUTH-01, INV-AUTH-03, FA-01 through FA-10, `scp-dna`, `scp-task-kernel-review`  

---

## Executive Summary

When `TaskKernelHandsBridge.execute()` encounters a pre-dispatch policy rejection (such as a missing capability token violating FA-05), it calls `self.kernel.transition(task_id, "FAILED")` at line 437. Inside `TaskKernel.transition()`, transitions to terminal, non-leased states like `"FAILED"` atomically mark the active lease as released (`released=1`) in the SQLite `leases` table and clear `active_lease_id` in `tasks`.

At line 451 of `task_kernel_bridge.py`, the code redundantly calls `self.kernel.release(task_id, lease.lease_id)`. Because the lease was already released during `transition()`, `_assert_lease()` raises `OptimisticLockError("lease ... has already been released")`. This uncaught exception falls through to the outer exception handler, which attempts an illegal transition to `UNKNOWN` on the terminal task, fails again, and returns `requiresRecovery: True` with `error: "Hands bridge could not persist unknown state: OptimisticLockError"`. This swallows the legitimate PEP denial (e.g. `CapabilityRequiredError`) and triggers false alerts for operator recovery.

Removing line 451 (`self.kernel.release(task_id, lease.lease_id)`) completely resolves the defect: the task transitions cleanly to `FAILED`, the lease is marked released in SQLite, the queue account is decremented, `requiresRecovery` is not set, and the true PEP authorization error is returned to the caller.

---

## 1. Observation

### 1.1 Direct Observation of Source Code Defect

1. **`scp/hands/task_kernel_bridge.py` lines 435–456**:
   ```python
   435:             if self._policy_blocked_before_dispatch(result):
   436: 
   437:                 self.kernel.transition(
   438: 
   439:                     task_id,
   440: 
   441:                     "FAILED",
   442: 
   443:                     actor="hands-kernel-bridge",
   444: 
   445:                     reason="hands_policy_denied_before_dispatch",
   446: 
   447:                     payload={"action": action},
   448: 
   449:                 )
   450: 
   451:                 self.kernel.release(task_id, lease.lease_id)
   452: 
   453:                 lease_active = False
   454: 
   455:                 return {**result, "safeToRetry": False, "kernel": self._public_kernel(task_id, lease.lease_id)}
   ```
   Line 437 transitions `task_id` to `"FAILED"`. Line 451 immediately calls `self.kernel.release(task_id, lease.lease_id)`.

2. **`scp/task_kernel_parts/taskkernel.py` lines 328–342 (`TaskKernel.transition`)**:
   ```python
   328:                 if to_state in {"RUNNING", "WAITING_TOOL", "VERIFYING", "CHECKPOINTED"}:
   329:                     new_lease_id = caller_lease
   330:                     new_fencing_token = token
   331:                 else:
   332:                     new_lease_id = None
   333:                     new_fencing_token = 0
   334:                     if caller_lease:
   335:                         self.conn.execute("UPDATE leases SET released=1,version=version+1 WHERE lease_id=? AND released=0", (caller_lease,))
   336:                         self.conn.execute(
   337:                             "UPDATE queue_accounts SET active=CASE WHEN active>0 THEN active-1 ELSE 0 END,version=version+1 WHERE owner=?",
   338:                             (task["owner"],),
   339:                         )
   340:                         if hasattr(self, "_bound_leases"):
   341:                             self._bound_leases.pop(task_id, None)
   ```
   Because `to_state == "FAILED"`, it enters the `else:` branch. Lines 334–341 atomically execute `UPDATE leases SET released=1...`, decrement `queue_accounts.active`, and remove `task_id` from `self._bound_leases`.

3. **`scp/task_kernel_parts/taskkernel.py` lines 460–471 (`_assert_lease`)**:
   ```python
   460:     def _assert_lease(self, lease_id: str, task_id: str) -> Any:
   461:         lease = self._lease(lease_id)
   462:         control = self._control()
   463:         now = time.time()
   464:         if lease['task_id'] != task_id or lease['released'] or lease['expires_at'] <= now or (lease['global_kill_epoch'] != control['global_kill_epoch']) or control['global_kill']:
   465:             if lease['released']:
   466:                 raise OptimisticLockError(
   467:                     f"lease {lease_id} has already been released",
   468:                     table="leases",
   469:                     entity_id=lease_id,
   470:                 )
   471:             raise StaleLease(lease_id)
   ```
   When `release()` is called at line 451, `_assert_lease()` checks `lease['released']`. Finding it is 1, it raises `OptimisticLockError("lease ... has already been released")`.

4. **`scp/hands/task_kernel_bridge.py` lines 527–565 (Cascade into UNKNOWN / Recovery)**:
   ```python
   527:         except Exception as exc:
   528:             if dispatch_started and lease_id and logical_key:
   529:                 try:
   530:                     return self._unknown_result(...)
   531:                 except Exception:
   532:                     return {
   533:                         "success": False,
   534:                         "action": action,
   535:                         "error": f"Hands bridge could not persist unknown state: {type(exc).__name__}",
   536:                         "requiresRecovery": True,
   537:                         "safeToRetry": False,
   538:                         "kernel": self._public_kernel(task_id, lease_id),
   539:                     }
   ```
   Because `dispatch_started = True` was already set at line 413, line 528 evaluates to `True`. `self._unknown_result(...)` is invoked. Inside `record_action_dispatched()`, `_assert_lease()` raises `OptimisticLockError` and state validation raises `InvalidTransition("FAILED->UNKNOWN")`. The inner except catches this and returns:
   `"error": "Hands bridge could not persist unknown state: OptimisticLockError"`, `"requiresRecovery": True`.

### 1.2 Verbatim Tool Execution Outputs

#### Probe 1: Reviewer 2 Exploit Probe
Command: `python .agents/orchestrator_5/reviewer_2/adversarial_bridge_probe.py`
Output:
```text
[EXPLOIT REPRODUCTION RESULT]
  res.success: False
  res.error: Hands bridge could not persist unknown state: OptimisticLockError
  res.requiresRecovery: True
  res.kernel.state: FAILED
>> Exploit reproduction CONFIRMED: Policy rejection cascaded into recovery exception handler.
```

#### Probe 2: Explorer 4 Comprehensive Lease Remediation Verification
Script: `.agents/orchestrator_5/explorer_4/verify_lease_remediation.py`
Command: `python .agents/orchestrator_5/explorer_4/verify_lease_remediation.py`
Output:
```text
==============================================================================
  EXPLORER 4: TASKKERNEL BRIDGE LEASE LIFECYCLE INVESTIGATION
==============================================================================

[STEP 1] Testing Baseline (Existing code with line 451)...
  success: False
  error: Hands bridge could not persist unknown state: OptimisticLockError
  requiresRecovery: True
  safeToRetry: False
  kernel: {'taskId': 'hands-64e47646bec6db2e9d96ac35a4532fb3', 'state': 'FAILED', 'version': 7, 'leaseId': 'lease_27ca3c1a27047fecf7c90f1b'}
  -> Baseline confirmed: line 451 triggers OptimisticLockError cascade!

[STEP 2] Testing Remediated (Line 451 removed)...
  success: False
  error: CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)
  requiresRecovery: None
  safeToRetry: False
  kernel: {'taskId': 'hands-b886d781f9ded1dbba6aee242a65b408', 'state': 'FAILED', 'version': 7, 'leaseId': 'lease_425103519a0db5a99a4a4a87'}
  -> Remediated execute() confirmed: returns CapabilityRequiredError cleanly, requiresRecovery=False!

[STEP 3] Verifying SQLite Database Invariants for Remediated Task...
  Task state: FAILED
  Task active_lease_id: None
  Task active_fencing_token: 0
  Lease released: 1
  Queue active: 0
  Events recorded: ['TASK_CREATED', 'STATE_TRANSITION', 'STATE_TRANSITION', 'STATE_TRANSITION', 'LEASE_GRANTED', 'WORKER_STARTED', 'CHECKPOINT_WRITTEN', 'STATE_TRANSITION']
  -> All Database invariants VERIFIED: lease is atomically released by transition('FAILED')!
  -> Verified release idempotency/guard: OptimisticLockError: lease lease_425103519a0db5a99a4a4a87 has already been released

==============================================================================
  ALL TESTS PASSED: Remediation is 100% sound and verified.
==============================================================================
```

---

## 2. Logic Chain

### 2.1 Step-by-Step Causal Deduction

```
Caller calls bridge.execute(action="pc.write_file", ..., capability_token=None)
  │
  ├─ [Line 413] dispatch_started = True
  ├─ [Line 427] HandsExecutor.execute() returns CapabilityRequiredError (FA-05 Zero-Trust gate)
  ├─ [Line 435] _policy_blocked_before_dispatch(result) returns True
  ├─ [Line 437] self.kernel.transition(task_id, "FAILED", ...)
  │     │
  │     └─ Inside taskkernel.py lines 334-342:
  │           UPDATE leases SET released=1, version=version+1 WHERE lease_id=?
  │           UPDATE queue_accounts SET active=active-1 WHERE owner=?
  │           self._bound_leases.pop(task_id, None)
  │           UPDATE tasks SET state='FAILED', active_lease_id=NULL, active_fencing_token=0
  │           self._commit() -> SQLite transaction commits.
  │
  ├─ [Line 451] self.kernel.release(task_id, lease.lease_id)  <-- DEFECT POINT
  │     │
  │     └─ Inside taskkernel.py lines 586 & 465-470:
  │           _assert_lease() checks lease['released'] -> is 1 (True)
  │           raises OptimisticLockError: lease ... has already been released
  │
  ├─ [Line 527] Outer except Exception catches OptimisticLockError
  │     │
  │     ├─ dispatch_started is True
  │     └─ calls self._unknown_result(task_id, lease_id, ...)
  │           │
  │           └─ record_action_dispatched() raises because lease is released and state is FAILED
  │
  └─ [Line 551] Inner except catches secondary exception and returns:
        error: "Hands bridge could not persist unknown state: OptimisticLockError"
        requiresRecovery: True
        (Legitimate CapabilityRequiredError is swallowed; operator recovery falsely requested)
```

### 2.2 Line-by-Line Call Graph (Investigation Mapping)

| Calling Line | Invoked Function | File & Lines | Behavior / Outcome |
|---|---|---|---|
| `task_kernel_bridge.py:427` | `HandsExecutor.execute()` | `hands_executor.py:110` | Returns PEP rejection `CapabilityRequiredError` |
| `task_kernel_bridge.py:435` | `_policy_blocked_before_dispatch()` | `task_kernel_bridge.py:135` | Matches `"capabilityrequired"` -> returns `True` |
| `task_kernel_bridge.py:437` | `TaskKernel.transition(task_id, "FAILED")` | `taskkernel.py:246` | Transitions task, marks `leases.released=1`, clears `tasks.active_lease_id=NULL`, pops `_bound_leases` |
| `task_kernel_bridge.py:451` | `TaskKernel.release(task_id, lease_id)` | `taskkernel.py:583` | Calls `_assert_lease()`, detects `lease['released']==1`, raises `OptimisticLockError` |
| `task_kernel_bridge.py:527` | `except Exception as exc:` | `task_kernel_bridge.py:527` | Traps `OptimisticLockError`, triggers `_unknown_result()` |
| `task_kernel_bridge.py:533` | `_unknown_result()` | `task_kernel_bridge.py:182` | Calls `record_action_dispatched()`, fails due to state `FAILED` & released lease |
| `task_kernel_bridge.py:549` | `except Exception:` | `task_kernel_bridge.py:549` | Traps secondary error, formats and returns `requiresRecovery=True` payload |

### 2.3 Proof of Invariant Preservation When Line 451 is Removed

1. **State Machine Invariant**:
   TaskKernel explicitly enforces that any transition out of `{"RUNNING", "WAITING_TOOL", "VERIFYING", "CHECKPOINTED"}` releases the lease within the database transaction (`taskkernel.py` lines 334–342). Releasing the lease is not an optional caller action—it is an atomic lifecycle transition of the state machine.
2. **Lease Cleanup Invariant**:
   Inspecting SQLite table `leases` confirms `released == 1` immediately after `transition(task_id, "FAILED")`.
   Inspecting SQLite table `tasks` confirms `active_lease_id IS NULL` and `state == 'FAILED'`.
   Inspecting SQLite table `queue_accounts` confirms `active == 0`.
3. **Instance Cleanup Invariant**:
   `task_kernel_bridge.py` line 453 sets `lease_active = False`. The outer `finally:` block (lines 605–614) checks `if lease_id and lease_active:`. Because `lease_active` is `False`, the finally block safely skips calling `release()`.
4. **Consistency with Success Path**:
   In `task_kernel_bridge.py` line 467–486 (the success path):
   `final_task = self.kernel.commit_verification_result(task_id, lease.lease_id, ...)`
   `lease_active = False`
   In that path, `commit_verification_result` releases the lease atomically in the DB, and the bridge simply sets `lease_active = False` without calling `release()`. Line 451 in the failure path was an erroneous deviation from this standard pattern.

---

## 3. Caveats

1. **Planner Defect Distinct from Bridge Lease Lifecycle**:
   Reviewer 2 also documented a Major Defect in `scp/hands/planner.py` line 284 (`_validate_step()` dropping `capabilityToken`). That defect is located entirely within `planner.py` and does not affect `task_kernel_bridge.py` lease lifecycle.
2. **Scope of Explorer 4**:
   Explorer 4 is strictly read-only and did not modify product code files directly. The fix must be applied to `scp/hands/task_kernel_bridge.py` by Worker 2.
3. **Database Concurrency**:
   Because the lease release is executed inside the SQLite transaction of `transition()`, there is zero race window between the task transitioning to `FAILED` and the lease being released.

---

## 4. Conclusion & Concrete Remediation Specification

### 4.1 Target File & Exact Edit

- **File**: `scp/hands/task_kernel_bridge.py`
- **Location**: Lines 448–455
- **Action**: Delete line 451 (`self.kernel.release(task_id, lease.lease_id)`).

#### Diff / Patch Specification

```patch
--- a/scp/hands/task_kernel_bridge.py
+++ b/scp/hands/task_kernel_bridge.py
@@ -448,8 +448,6 @@
                     payload={"action": action},
                 )
-                self.kernel.release(task_id, lease.lease_id)
                 lease_active = False
                 return {**result, "safeToRetry": False, "kernel": self._public_kernel(task_id, lease.lease_id)}
```

#### Exact Code Block After Remediation

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

### 4.2 Mandatory Regression Test Addition

In `tests/T04_kernel/test_kernel_p1_regressions.py`, append the following test case to lock in this fix and prevent regression:

```python
def test_bridge_policy_denial_transitions_to_failed_without_unknown_cascade(tmp_path: Path):
    """P1 Regression: Pre-dispatch policy denial must cleanly transition to FAILED.
    
    Verifies that self.kernel.transition(task_id, 'FAILED') does not trigger
    a double-release OptimisticLockError, requiresRecovery is not True, and
    the policy error (CapabilityRequiredError) is preserved.
    """
    bridge, workspace, _ = _bridge_with_executor(tmp_path)
    try:
        target = workspace / "denied_file.txt"
        result = asyncio.run(
            bridge.execute(
                action="pc.write_file",
                params={"path": str(target), "content": "should_fail"},
                capability_level=3,
                approved=True,
                request_key=f"p1-denial-{uuid.uuid4().hex}",
                capability_token=None,  # Triggers CapabilityRequiredError
            )
        )
        assert result.get("success") is False
        assert "CapabilityRequiredError" in str(result.get("error", "")), f"Expected CapabilityRequiredError, got: {result.get('error')}"
        assert result.get("requiresRecovery") in (False, None), f"requiresRecovery must not be True: {result}"
        assert result.get("safeToRetry") is False
        assert result.get("kernel", {}).get("state") == "FAILED", f"Kernel state must be FAILED: {result}"
        assert not target.exists(), "File must not have been created"

        # Verify DB state directly
        kernel = TaskKernel(str(tmp_path / "kernel.sqlite3"))
        task_id = result["kernel"]["taskId"]
        task = kernel.get_task(task_id)
        assert task["state"] == "FAILED"
        assert task["active_lease_id"] is None
        assert task["active_fencing_token"] == 0

        lease_row = kernel.conn.execute("SELECT * FROM leases WHERE lease_id=?", (result["kernel"]["leaseId"],)).fetchone()
        assert lease_row["released"] == 1, "Lease must be marked released in DB"

        kernel.close()
    finally:
        bridge.close()
```

---

## 5. Verification Method

### 5.1 Verification Commands

1. **Verify Remediation via Explorer 4 Verification Script**:
   ```bash
   python .agents/orchestrator_5/explorer_4/verify_lease_remediation.py
   ```
   Must exit 0 with:
   `ALL TESTS PASSED: Remediation is 100% sound and verified.`

2. **Verify Remediation via Challenger 2 Stress Suite**:
   ```bash
   python tools/probes/challenge_concurrency_protocol_stress.py
   ```
   Challenge 2 and Challenge 3 must PASS without any `OptimisticLockError` or `requiresRecovery: True`.

3. **Full Regression Suite**:
   ```bash
   pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py -v
   ```
   Must pass with 0 failures and 0 skipped tests.

### 5.2 Invalidation Conditions

The remediation is INVALID if any of the following occur:
- Any pre-dispatch policy denial returns `"error": "Hands bridge could not persist unknown state: OptimisticLockError"`.
- Any pre-dispatch policy denial returns `"requiresRecovery": True`.
- In SQLite, `leases.released` is NOT 1 after a policy-denied transition to `FAILED`.
- Any test assertions are loosened or deleted (violating FA-01 / FA-02).
