# HANDOFF REPORT: REVIEWER 2 (ITERATION 2) — CALLER PROTOCOLS & BRIDGE QUALITY REVIEW

**Author**: Reviewer 2 (Caller Protocols & Bridge Quality Reviewer — Iteration 2)  
**Target Workspace**: `c:\Users\check\Downloads\scp`  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\orchestrator_5\reviewer_2_r2`  
**Recipient / Parent Agent**: `parent` (`967399d1-d666-4dce-899b-4c2468b6dd91`)  
**Date**: 2026-09-07T07:47:30Z  
**HEAD SHA**: `354ebce7dd354179c701257fbbdc23fad7515454`  
**TREE HASH**: `d2f5b289b76e23da6086302e56cd829c4922a84b`  
**Handoff Type**: Hard (Review Complete)  
**Governing Invariants**: INV-AUTH-01, INV-AUTH-02, INV-AUTH-03, INV-AUTH-04, FA-01 through FA-10  

---

## Review Summary

**Verdict**: **APPROVE**  
**Overall Risk Assessment**: **LOW**

---

## 1. Observation

### 1.1 Source Code Inspections

1. **`scp/hands/task_kernel_bridge.py` lines 168–186 (`_public_kernel`)**:
   - `_public_kernel(task_id, lease_id)` retrieves task from `self.kernel.get_task(task_id)` and constructs:
     ```python
     task_state = task.get("state") if isinstance(task, dict) else task["state"]
     result = {
         "taskId": task_id,
         "state": task_state,
         "taskState": task_state,
         "version": task.get("version") if isinstance(task, dict) else task["version"],
         "requiresRecovery": False,
     }
     if lease_id:
         result["leaseId"] = lease_id
     return result
     ```
   - Verifies that `taskState` matches `state`, and `requiresRecovery: False` is explicitly populated for non-uncertain terminal states.

2. **`scp/hands/task_kernel_bridge.py` lines 443–467 (`execute()` policy rejection path)**:
   - Redundant line 451 `self.kernel.release(task_id, lease.lease_id)` was completely removed.
   - Code now executes:
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
         return {
             **result,
             "requiresRecovery": False,
             "safeToRetry": False,
             "kernel": self._public_kernel(task_id, lease.lease_id),
         }
     ```
   - In `scp/task_kernel_parts/taskkernel.py` lines 334–342, `TaskKernel.transition(task_id, "FAILED")` runs `UPDATE leases SET released=1,version=version+1 WHERE lease_id=? AND released=0` within an atomic SQLite transaction.
   - Setting `lease_active = False` guarantees the `finally:` block (lines 616–625) does not attempt a second lease release.

3. **`scp/hands/planner.py` lines 283–306 (`_validate_step`)**:
   - Normalized step token preservation:
     ```python
     raw_capability = max(0, min(int(raw.get("capabilityLevel", definition.capability_level)), 5))
     raw_token = raw.get("capabilityToken") if raw.get("capabilityToken") is not None else raw.get("capability_token")
     if raw_token is not None:
         parsed_token = parse_capability_token(raw_token)
         step_token: Any = parsed_token.to_dict() if parsed_token is not None else raw_token
     else:
         step_token = None
     return {
         "stepId": step_id,
         "action": action,
         "params": params,
         "capabilityLevel": raw_capability,
         "capabilityToken": step_token,
         ...
     }
     ```
   - Step tokens provided as `CapabilityToken` dataclass objects or dictionary representations are normalized to serializable dictionaries (`.to_dict()`), surviving persistence without corruption.

4. **`scp/hands/planner.py` lines 465–479, 581–596, 736–750 (`_run_plan_locked`, `_run_dag_step`, `_run_dag_locked`)**:
   - Resolves `step_token = step.get("capabilityToken") or step.get("capability_token") or (capability_token.get(step_id)...) or capability_token`.
   - Parses `parsed_step_token = parse_capability_token(step_token)` and validates token before executing or scheduling ready DAG nodes.
   - Forwards `capability_token=parsed_step_token` directly into `self.executor.execute()`.

5. **`tests/T03_capability/test_hands_authority_pep.py`**:
   - Contains 9 automated unit/integration tests verifying:
     - `test_hands_executor_rejects_missing_token_fail_closed`
     - `test_hands_executor_rejects_scope_mismatch_fail_closed`
     - `test_hands_executor_rejects_revoked_epoch`
     - `test_hands_executor_rollback_requires_token`
     - `test_bridge_execute_missing_token_clean_policy_denial_no_recovery`
     - `test_bridge_rejects_scope_mismatch_fail_closed`
     - `test_bridge_rejects_revoked_token_fail_closed`
     - `test_planner_step_capability_token_preservation_and_execution`
     - `test_planner_step_capability_token_scope_mismatch_fails_closed`

---

### 1.2 Verbatim Execution Results

#### Verification 1: `tests/T03_capability/test_hands_authority_pep.py`
```text
pytest tests/T03_capability/test_hands_authority_pep.py -v

============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\check\Downloads\scp
configfile: pytest.ini
collected 9 items

tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rejects_missing_token_fail_closed PASSED [ 11%]
tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rejects_scope_mismatch_fail_closed PASSED [ 22%]
tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rejects_revoked_epoch PASSED [ 33%]
tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rollback_requires_token PASSED [ 44%]
tests/T03_capability/test_hands_authority_pep.py::test_bridge_execute_missing_token_clean_policy_denial_no_recovery PASSED [ 55%]
tests/T03_capability/test_hands_authority_pep.py::test_bridge_rejects_scope_mismatch_fail_closed PASSED [ 66%]
tests/T03_capability/test_hands_authority_pep.py::test_bridge_rejects_revoked_token_fail_closed PASSED [ 77%]
tests/T03_capability/test_hands_authority_pep.py::test_planner_step_capability_token_preservation_and_execution PASSED [ 88%]
tests/T03_capability/test_hands_authority_pep.py::test_planner_step_capability_token_scope_mismatch_fails_closed PASSED [100%]

============================== 9 passed in 1.14s ==============================
```

#### Verification 2: Kernel P1 & Golden Task Regressions
```text
pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py -v

============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
collected 6 items

tests/T04_kernel/test_kernel_p1_regressions.py::test_bridge_duplicate_request_returns_replayed_response PASSED [ 16%]
tests/T04_kernel/test_kernel_p1_regressions.py::test_orphan_sweep_keeps_fresh_lease_and_reconciles_stale_one PASSED [ 33%]
tests/T04_kernel/test_kernel_p1_regressions.py::test_checkpoint_event_does_not_poison_rebuild_projection PASSED [ 50%]
tests/T04_kernel/test_kernel_p1_regressions.py::test_checkpoint_still_rejects_invalid_state PASSED [ 66%]
tests/T04_kernel/test_kernel_p1_regressions.py::test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch PASSED [ 83%]
tests/T09_golden_task/test_golden_a_agent_os.py::test_golden_a_agent_os_real_execution_flow PASSED [100%]

============================== 6 passed in 3.22s ==============================
```

#### Verification 3: Concurrency Protocol Stress Suite
```text
python tools/probes/challenge_concurrency_protocol_stress.py

==============================================================================
  EMPIRICAL CHALLENGE SUMMARY (Elapsed: 2.40s)
==============================================================================
  challenge_1: PASS
  challenge_2: PASS
  challenge_3: PASS
  challenge_4: PASS
  challenge_5: PASS

------------------------------------------------------------------------------
OVERALL VERDICT: APPROVE
```

#### Verification 4: Test Integrity Meta-Audit (Pre-commit / CI Gate)
```text
python tools/t00_meta_audit.py

[T00 Meta-Audit] Starting Test-Integrity Regression Authority...
[T00 Meta-Audit] Trusted Base: origin/main
[T00 Meta-Audit] Collecting baseline pytest nodeids (origin/main)...
[T00 Meta-Audit] Collecting candidate pytest nodeids...
...
[T00 Meta-Audit] All integrity checks passed (0 new regressions).
```

#### Verification 5: Full Project Pytest Suite (Clean Workspace Run)
```text
pytest tests/ -q

........................................................................ [ 16%]
........................................................................ [ 32%]
........................................................................ [ 48%]
........................................................................ [ 64%]
........................................................................ [ 80%]
........................................................................ [ 96%]
..................                                                       [100%]
450 passed in 133.23s (0:02:13)
```

#### Verification 6: Independent Empirical Probes

1. **Direct SQLite State Verification on Bridge Pre-Dispatch Denial**:
   - Executed `bridge.execute("pc.write_file", ..., capability_token=None)`
   - Results:
     - `result['success'] == False`
     - `result['requiresRecovery'] == False`
     - `result['kernel']['requiresRecovery'] == False`
     - `result['kernel']['taskState'] == 'FAILED'`
     - `result['kernel']['state'] == 'FAILED'`
     - Database verification:
       - `tasks.state == 'FAILED'`
       - `tasks.active_lease_id IS NULL`
       - `tasks.active_fencing_token == 0`
       - `leases.released == 1`
       - Task events sequence: `['CREATED', 'PLANNING', 'READY', 'QUEUED', 'LEASED', 'RUNNING', None, 'FAILED']`
     - Status: **PASSED**

2. **DAG Step Token Execution & Scope Mismatch Denial Probes**:
   - Multi-step DAG with step-level `capabilityToken` passed to individual steps: completed with `res['success'] == True`, files verified.
   - Multi-step DAG with mismatched step-level token (`hands:pc.status` on `pc.write_file`): failed closed with `res['success'] == False`, target file not created.
   - Status: **PASSED**

---

## 2. Logic Chain

1. **Lease Lifecycle Atomicity**:
   - In `TaskKernel`, transitioning a task to terminal states (`FAILED`, `COMPLETED`, `CANCELLED`) automatically executes `UPDATE leases SET released=1,version=version+1 WHERE lease_id=? AND released=0` and clears `active_lease_id`.
   - Therefore, any subsequent explicit call to `release(task_id, lease_id)` on an already-transitioned task violates OCC and fails with `OptimisticLockError`.
   - By eliminating line 451 `self.kernel.release(task_id, lease.lease_id)` and setting `lease_active = False` in `task_kernel_bridge.py`, the bridge allows `transition(task_id, "FAILED")` to stand as the sole atomic release mechanism. The policy denial response returns cleanly without an exception, without an invalid secondary transition attempt to `UNKNOWN`, and with `requiresRecovery: False`.

2. **Step Token Preservation & DAG Propagation**:
   - `HandsPlanner._validate_step()` previously discarded all parameters not in its static dict template, dropping step-level authority.
   - Worker 3 updated `_validate_step()` to accept `capabilityToken` / `capability_token`, normalize them through `parse_capability_token().to_dict()`, and store them in the plan definition.
   - Both sequential (`_run_plan_locked`) and DAG (`_run_dag_locked`, `_run_dag_step`) execution pathways now resolve step-level tokens, authenticate them with `parse_capability_token()`, and pass `capability_token=parsed_step_token` to `executor.execute()`.
   - If a step lacks a valid token or has a scope mismatch, it is rejected fail-closed before any mutating side effects can touch the system.

3. **Integrity & Anti-Placebo Compliance**:
   - Zero tests were skipped, deleted, or loosened (verified by `tools/t00_meta_audit.py`).
   - No mock returns or simulated `VERIFIED` statuses were introduced in `task_kernel_bridge.py` or `planner.py`.
   - All tests run against live SQLite and filesystem backends.

---

## 3. Caveats

- **Historical Debt**: Baseline debt warnings reported by `tools/t00_meta_audit.py` in unrelated files (`scp/tests/external_audit/test_security.py` and `tests/T03_capability/test_os_sandbox.py`) are pre-existing in `origin/main` and remain unchanged.
- **Windows File Handle Collision in Pytest**: When executing back-to-back test suites without cleaning `reports/pytest-basetemp`, Windows OS file locks can cause temporary `[WinError 183]` / `[WinError 145]` directory collisions. Using clean basetemp directories eliminates this runner artifact completely (450/450 tests green).

---

## 4. Conclusion

1. **Defect 1 (Double Lease Release)**: Fully resolved. `task_kernel_bridge.py` handles pre-dispatch policy rejections cleanly, transitions to `FAILED`, atomically releases the lease in SQLite, and returns `requiresRecovery: False` and `taskState: 'FAILED'`.
2. **Defect 2 (Planner Step Token Retention)**: Fully resolved. `planner.py` preserves step-level tokens, serializes them cleanly, and enforces step-level tokens in sequential and concurrent DAG execution.
3. **Verdict**: **APPROVE**. The remediations satisfy all architectural invariants, pass all unit and regression tests, succeed under concurrency stress, and maintain complete test integrity.

---

## 5. Verification Method

### Commands to Run Independently

```powershell
# 1. Run PEP authority and bridge regression tests
pytest tests/T03_capability/test_hands_authority_pep.py -v

# 2. Run Task Kernel and Golden Task regressions
pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py -v

# 3. Run Concurrency and Protocol Stress Suite
python tools/probes/challenge_concurrency_protocol_stress.py

# 4. Run Test-Integrity Meta-Audit Gate
python tools/t00_meta_audit.py

# 5. Run Full Project Test Suite
pytest tests/ -q
```

### Invalidation Conditions
- Any occurrence of `OptimisticLockError` on a pre-dispatch policy rejection.
- Any pre-dispatch policy denial returning `requiresRecovery: True`.
- Any dangling active lease in `leases` or `tasks.active_lease_id` after a task transition to `FAILED`.
- Any failure in the 450 tests or regression detected by `t00_meta_audit.py`.
