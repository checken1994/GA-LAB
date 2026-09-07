# HANDOFF REPORT: PROTOCOL & CONCURRENCY EMPIRICAL STRESS CHALLENGE

**Author**: Challenger 2 (Protocol & Concurrency Stress Challenger)  
**Target Workspace**: `c:\Users\check\Downloads\scp`  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\orchestrator_5\challenger_2`  
**Date**: 2026-09-07T07:18:00Z  
**Parent Agent**: `parent` (`967399d1-d666-4dce-899b-4c2468b6dd91`)  
**Verdict**: **REJECT**  
**Governing Invariants**: INV-AUTH-01 (Disjoint Authority Boundary), INV-AUTH-02 (Scoped Subject Binding), INV-AUTH-03 (Pre-Dispatch Fail-Closed PEP Gate), FA-01 through FA-10  
**Handoff Type**: Hard (Task Complete — Empirical Challenge Verdict Delivered)  

---

## 1. Observation

### 1.1 Direct Observation of Source Code Defect

1. **`scp/hands/task_kernel_bridge.py` (lines 435–455)**:
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
   Line 437 transitions the task to terminal state `FAILED`. Line 451 immediately attempts to release the lease via `self.kernel.release(task_id, lease.lease_id)`.

2. **`scp/task_kernel_parts/taskkernel.py` (lines 331–342)**:
   ```python
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
   `TaskKernel.transition()` to any non-active state (including `FAILED`) automatically and atomically marks the lease released (`released=1`) in the database.

3. **`scp/task_kernel_parts/taskkernel.py` (lines 463–469)**:
   ```python
   463:     def _assert_lease(self, lease_id: str, task_id: str) -> dict[str, Any]:
   464:         lease = self.conn.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
   465:         ...
   466:         if lease["released"]:
   467:             raise OptimisticLockError(f"lease {lease_id} has already been released")
   ```
   When `self.kernel.release(task_id, lease.lease_id)` runs at line 451, `_assert_lease` raises `OptimisticLockError("lease ... has already been released")`.

4. **`scp/hands/task_kernel_bridge.py` (lines 527–566)**:
   ```python
   527:         except Exception as exc:
   528: 
   529:             if dispatch_started and lease_id and logical_key:
   530: 
   531:                 try:
   532: 
   533:                     return self._unknown_result(...)
   534: 
   535:                 except Exception:
   536: 
   537:                     return {
   538: 
   539:                         "success": False,
   540: 
   541:                         "action": action,
   542: 
   543:                         "error": f"Hands bridge could not persist unknown state: {type(exc).__name__}",
   544: 
   545:                         "requiresRecovery": True,
   546: 
   547:                         "safeToRetry": False,
   548: 
   549:                         "kernel": self._public_kernel(task_id, lease_id),
   550: 
   551:                     }
   ```
   Because `dispatch_started = True` was already set at line 413, the `OptimisticLockError` thrown at line 451 is caught here. `self._unknown_result(...)` attempts to transition the task from terminal `FAILED` to `UNKNOWN`, which is illegal (`InvalidTransition: terminal task is immutable`). The inner except catches this secondary exception and returns:
   `"error": "Hands bridge could not persist unknown state: OptimisticLockError"`, `"requiresRecovery": True`!

---

### 1.2 Verbatim Terminal Outputs from Empirical Stress Harness

We constructed and executed the comprehensive empirical challenge harness: `tools/probes/challenge_concurrency_protocol_stress.py`.

Command: `python tools/probes/challenge_concurrency_protocol_stress.py`
Output:
```text
==============================================================================
  CHALLENGER 2: PROTOCOL & CONCURRENCY EMPIRICAL SUITE
==============================================================================
[14:17:34] === CHALLENGE 1: Concurrency with Valid Tokens ===
[14:17:34] Launching 15 concurrent bridge executions with valid tokens...
[14:17:35] Completed 15 concurrent executions in 0.449s
[14:17:35] [PASS] Challenge 1: All 15 concurrent tasks completed, files verified, epochs matched.
[14:17:35] === CHALLENGE 2: Concurrency Denial (Missing Tokens) ===
[14:17:35] Launching 15 concurrent bridge executions WITHOUT tokens...
[14:17:35] Completed 15 concurrent denial executions in 0.185s
[14:17:35] [BUG DETECTED] Challenge 2 FAILED: 15/15 denial responses corrupted!
[14:17:35] Sample corrupt response: error='Hands bridge could not persist unknown state: OptimisticLockError', requiresRecovery=True
[14:17:35] === CHALLENGE 3: Concurrency Scope Mismatch Denial ===
[14:17:35] Launching 10 concurrent bridge executions with scope-mismatched tokens...
[14:17:35] [BUG DETECTED] Challenge 3 FAILED: 10/10 scope mismatch responses corrupted!
[14:17:35] Sample corrupt response: error='Hands bridge could not persist unknown state: OptimisticLockError', requiresRecovery=True
[14:17:35] === CHALLENGE 4: Idempotency Replay Stress ===
[14:17:35] Step 1: Initial execution...
[14:17:35] Step 2: Sequential replay with mutated parameter attempt...
[14:17:35] Step 3: Concurrent race on identical request_key (10 parallel requests)...
[14:17:35] Race outcome: 1 succeeded, 9 replayed/fenced
[14:17:35] [PASS] Challenge 4: Idempotency replay and concurrent race invariants verified.
[14:17:35] === CHALLENGE 5: FastAPI Route Concurrency ===
[14:17:36] Step 1: Testing concurrent valid requests to /v3/hands/execute...
[14:17:37] Step 2: Testing concurrent missing token requests to /v3/hands/execute...
[14:17:37] Step 3: Testing replay through /v3/hands/execute...
[14:17:37] [BUG DETECTED] Challenge 5: Route denial returned corrupted response: error='Hands bridge could not persist unknown state: OptimisticLockError', requiresRecovery=True

==============================================================================
  EMPIRICAL CHALLENGE SUMMARY (Elapsed: 2.59s)
==============================================================================
  challenge_1: PASS
  challenge_2: FAIL
    Reason: Bridge internal crash on release() swallowed CapabilityRequiredError into OptimisticLockError with requiresRecovery=True
    Sample: {"task_index": 0, "error": "Hands bridge could not persist unknown state: OptimisticLockError", "requiresRecovery": true, "task_id": "hands-7d45ae85f1c34d951b417008f9d428cf"}
  challenge_3: FAIL
    Reason: Bridge internal crash on release() swallowed CapabilityScopeMismatchError into OptimisticLockError with requiresRecovery=True
    Sample: {"task_index": 0, "error": "Hands bridge could not persist unknown state: OptimisticLockError", "requiresRecovery": true}
  challenge_4: PASS
  challenge_5: FAIL
    Reason: Route denial cascades into OptimisticLockError with requiresRecovery=True
    Sample: {"success": false, "action": "pc.write_file", "error": "Hands bridge could not persist unknown state: OptimisticLockError", "requiresRecovery": true, "safeToRetry": false, "kernel": {"taskId": "hands-8d597ee80154f2732dcc7ef0c2b19154", "state": "FAILED", "version": 7, "leaseId": "lease_fefde2988cac5397a0e07958"}, "run_id": "run-b5dd6866953d4fdd8cf92141c2e473fe", "trace_id": "trace-c053c993f1cf43bdaf553c6265547be1", "run_status": "INTERNAL_FAILED", "ledger_status": "OK"}

------------------------------------------------------------------------------
OVERALL VERDICT: REJECT
Reason: Critical failure in Policy Denial path in TaskKernelHandsBridge (lines 450-455).
Calling self.kernel.release() after transition('FAILED') triggers OptimisticLockError,
corrupting the PEP denial response and incorrectly setting requiresRecovery=True.
```

---

### 1.3 Verbatim Terminal Output from T00 Meta-Audit Authority

Command: `python tools/t00_meta_audit.py`
Output:
```text
[T00 Meta-Audit] Starting Test-Integrity Regression Authority...
[T00 Meta-Audit] Trusted Base: origin/main

--- SCOPE & LIMITATIONS ---
 * FA-01 (Semantic Weakening): Partial (skip/xfail checked, incl. module-level pytestmark). Logic weakening requires L4 human review.
 * FA-02: ENFORCED for regressions in collected pytest nodeids
 * FA-03 (Same-SHA Evidence): NOT ENFORCED by T00 (Requires dedicated evidence tool).
 * FA-04 (Manufactured Green): Regex-based. Complex AST tracking requires L4 human review.
 * FA-05 (Self-Granting Auth): NOT ENFORCED by T00 (Requires capability scanner).
[T00 Meta-Audit] Collecting baseline pytest nodeids (origin/main)...
[T00 Meta-Audit] Collecting candidate pytest nodeids...

--- BASELINE_DEBT (Tracked, Not Blocking) ---
 [DEBT] FA-01: scp/tests/external_audit/test_security.py -> pytest.skip() in test_bandit_no_new_high_severity_via_bandit (2 historical instances)
 [DEBT] FA-01: scp/tests/external_audit/test_security.py -> pytest.skip() in test_no_hardcoded_token_in_source (1 historical instances)
 [DEBT] FA-01: tests/T03_capability/test_os_sandbox.py -> pytest.skip() in test_sandbox_executes_command_inside_job_object (1 historical instances)
 [DEBT] FA-01: tests/T03_capability/test_os_sandbox.py -> pytest.skip() in test_sandbox_rejects_invalid_capability (1 historical instances)
 [DEBT] FA-04: scp/autofix/evidence_replay.py -> hardcoded VERIFIED: return {"ok": True, "status": "VERIFIED"} (1 historical instances)

--- L4 CODEOWNERS (Warning) ---
 [L4] L4 Protected Path Modified: spec/scp_future_cause_effect_matrix_v4_0_2.overlay.json
 [L4] L4 Protected Path Modified: spec/scp_future_target_manifest.yaml
 [L4] L4 Protected Path Modified: tests/T00_integrity/test_scp_future_target.py
 [L4] L4 Protected Path Modified: tests/T04_kernel/test_kernel_p1_regressions.py
 [L4] L4 Protected Path Modified: tests/T09_golden_task/test_golden_a_agent_os.py
Note: L4 is VERIFIED only by GitHub Server-Side Ruleset. This is a local warning.

[T00 Meta-Audit] All integrity checks passed (0 new regressions).
Exit code: 0
```

---

## 2. Logic Chain

1. **Step 1 (Mandate & Invariant Definition)**:
   The orchestrator required Challenger 2 to verify:
   - "Concurrency Denial Challenge: Multiple concurrent bridge executions without capability tokens -> verify all fail closed without corrupting TaskKernel state or transitioning tasks to UNKNOWN."
   Worker 2 in `worker_2/handoff.md` (line 43) claimed:
   "In `_policy_blocked_before_dispatch()` (lines 135–154): added policy rejection markers: ... This prevents PEP rejections from falsely cascading into TaskKernel UNKNOWN status."

2. **Step 2 (Empirical Contradiction)**:
   From Observation 1.2, executing `bridge.execute()` without a capability token (or with a mismatched token) does NOT return the expected `CapabilityRequiredError` or `CapabilityScopeMismatchError`.
   Instead, 100% of the denial requests return:
   ```json
   {
     "success": false,
     "action": "pc.write_file",
     "error": "Hands bridge could not persist unknown state: OptimisticLockError",
     "requiresRecovery": true,
     "safeToRetry": false,
     "kernel": {
       "taskId": "...",
       "state": "FAILED",
       ...
     }
   }
   ```

3. **Step 3 (Causal Analysis & Call Graph)**:
   - From Observation 1.1 item 1, in `TaskKernelHandsBridge.execute`:
     `self._policy_blocked_before_dispatch(result)` evaluates to `True`.
   - Line 437 calls `self.kernel.transition(task_id, "FAILED", ...)`.
   - From Observation 1.1 item 2, `TaskKernel.transition()` explicitly executes:
     `UPDATE leases SET released=1,version=version+1 WHERE lease_id=? AND released=0`. The lease is now marked `released=1`.
   - Line 451 calls `self.kernel.release(task_id, lease.lease_id)`.
   - From Observation 1.1 item 3, `self.kernel.release()` invokes `_assert_lease(lease_id, task_id)`. Seeing `lease["released"] == 1`, it raises `OptimisticLockError("lease ... has already been released")`.
   - From Observation 1.1 item 4, line 527 catches `OptimisticLockError`. Because `dispatch_started == True`, it executes `self._unknown_result(...)`, which attempts an illegal transition to `UNKNOWN` on an already-`FAILED` task, fails again, and falls back to returning `"error": "Hands bridge could not persist unknown state: OptimisticLockError"`, `"requiresRecovery": True`.

4. **Step 4 (Impact on Zero-Trust Architecture)**:
   - **PEP Masking**: Any caller (API client, orchestrator, subagent) submitting an unauthorized request is falsely told that an internal concurrency conflict / unknown crash occurred and that operator recovery is required (`requiresRecovery: True`), instead of receiving the clear PEP authorization rejection.
   - **Placebo Prevention**: Worker 2 only tested `HandsExecutor.execute()` directly in `test_hands_authority_pep.py`. Worker 2 never tested calling `TaskKernelHandsBridge.execute()` without a token. This blind spot resulted in deploying broken error-handling logic at the bridge boundary.

5. **Step 5 (Deduction of Verdict)**:
   Because Challenge 2, Challenge 3, and Challenge 5 fail on this critical protocol defect, Worker 2's implementation cannot be approved. The verdict must be **REJECT**.

---

## 3. Caveats

1. **Working Tree Modification**:
   In accordance with the mandatory constraint ("Review-only — do NOT modify implementation code"), Challenger 2 did NOT modify `scp/hands/task_kernel_bridge.py`. The fix belongs exclusively to the core implementer (Worker 2).
2. **Straightforward Fix Available**:
   In `scp/hands/task_kernel_bridge.py` lines 435–455, removing the redundant `self.kernel.release(task_id, lease.lease_id)` line (or wrapping it safely) will allow the clean `result` (`CapabilityRequiredError`) to return directly, resolving Challenge 2, 3, and 5 immediately.
3. **Passing Areas**:
   - Concurrency with valid tokens (Challenge 1) is robust and fast (15 concurrent tasks in 0.449s with exact checkpoint epochs).
   - Idempotency replay and concurrent race fencing (Challenge 4) are robust and proven.
   - T00 Meta-Audit passes with 0 new regressions.

---

## 4. Conclusion

**Verdict: REJECT**

Worker 2 successfully eradicated the self-granting backdoor in `HandsExecutor` and threaded tokens through the callers. However, Worker 2 failed to verify the Policy Denial path through `TaskKernelHandsBridge`.
In `TaskKernelHandsBridge.execute()`, calling `self.kernel.release(task_id, lease.lease_id)` at line 451 immediately after `self.kernel.transition(task_id, "FAILED")` raises `OptimisticLockError` on every single unauthorized execution. This causes PEP rejections to crash internally, setting `requiresRecovery: True` and returning an unhandled bridge error (`Hands bridge could not persist unknown state: OptimisticLockError`).

Worker 2 must fix line 451 in `scp/hands/task_kernel_bridge.py` before GAP-07 can be marked complete.

---

## 5. Verification Method

To independently verify this rejection and reproduce the exact bug:

```bash
# 1. Run the Challenger 2 Stress Suite (Exits with code 2 on bug reproduction)
python tools/probes/challenge_concurrency_protocol_stress.py

# 2. Inspect the failure output:
# Challenge 2 and 3 report:
# [BUG DETECTED] Challenge 2 FAILED: 15/15 denial responses corrupted!
# Sample: error='Hands bridge could not persist unknown state: OptimisticLockError', requiresRecovery=True

# 3. Direct 5-line reproduction script:
python -c "
import asyncio, tempfile
from pathlib import Path
from scp.hands.hands_executor import HandsExecutor
from scp.hands.task_kernel_bridge import TaskKernelHandsBridge
from scp.pc_control.pc_controller import PCController
from scp.security.capability_epoch import CapabilityAuthority

async def repro():
    d = Path(tempfile.mkdtemp())
    (d / 'w').mkdir()
    bridge = TaskKernelHandsBridge(HandsExecutor(controller=PCController(working_dir=d / 'w'), capability_authority=CapabilityAuthority(d / 'cap.json'), data_dir=d), db_path=d / 'k.db')
    res = await bridge.execute(action='pc.write_file', params={'path': str(d / 'w' / 'f.txt'), 'content': 'x'}, capability_level=3, approved=True, request_key='k1', capability_token=None)
    print('Result:', res)
    assert 'CapabilityRequiredError' in str(res.get('error', '')), 'BUG CONFIRMED: Did not return CapabilityRequiredError!'

asyncio.run(repro())
"
```

### Invalidation Conditions
- A denial execution through `TaskKernelHandsBridge` without a token returns `error: "CapabilityRequiredError..."` with `requiresRecovery` omitted or `False`.
- `python tools/probes/challenge_concurrency_protocol_stress.py` exits with code 0.
