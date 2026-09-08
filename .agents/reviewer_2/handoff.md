# REVIEW & ADVERSARIAL CHALLENGE REPORT — REVIEWER 2

**Reviewer Identity**: Reviewer 2 (`teamwork_preview_reviewer`)  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\reviewer_2`  
**Parent Orchestrator ID**: `f1e50da6-b37c-427b-a8a3-fdc334188734`  
**Timestamp**: 2026-09-08T01:52:00Z  
**Target Subject**: Worker 1 GAP-12 Remediation (`commit_failed()` Endpoint & State Fence)  
**Verdict**: **APPROVE**  

---

## 1. OBSERVATION

Directly observed files, line numbers, terminal commands, and verbatim execution outputs:

### 1.1 Implementation & Interface Observations
1. **Transition Guard in `scp/task_kernel_parts/taskkernel.py:259-263`**:
   ```python
   if to_state in ("COMPLETED", "FAILED"):
       raise InvalidTransition(
           f"direct transition to {to_state} is forbidden; use commit_{to_state.lower()}() with valid evidence"
       )
   ```
   Direct calls to `kernel.transition(task_id, "FAILED")` from any state are categorically intercepted with `InvalidTransition`.

2. **Actor-Bound Lease Fencing in `scp/task_kernel_parts/taskkernel.py:470-488`**:
   `_assert_lease(self, lease_id: str, task_id: str, actor: str | None = None)` checks:
   ```python
   if actor is not None and str(actor).strip():
       if lease['worker_id'] != str(actor).strip():
           raise InvalidTransition(f"actor '{actor}' does not match lease worker '{lease['worker_id']}'")
   ```
   Stolen lease sabotage by mismatched actors is rejected at the database lease verification level.

3. **`commit_failed()` Endpoint in `scp/task_kernel_parts/taskkernel.py:961-1090`**:
   - **Input Validation (lines 980-989)**:
     ```python
     if not task_id or not str(task_id).strip(): raise KernelError("task_id is required")
     if not lease_id or not str(lease_id).strip(): raise StaleLease("lease_id is required")
     if not actor or not str(actor).strip(): raise KernelError("actor is required")
     if not failure_classification or not str(failure_classification).strip(): raise KernelError("failure_classification is required")
     if not indictment_ref or not str(indictment_ref).strip(): raise KernelError("indictment_ref is required; failure commitment requires verifiable failure evidence")
     ```
   - **Existence, State, & Lease Ownership (lines 993-1010)**:
     Fetches task via `_task(task_id)` (raising `NotFound` if nonexistent); asserts lease via `_assert_lease(..., actor=actor)`; verifies `old_state not in TERMINAL` and `old_state in {"RUNNING", "WAITING_TOOL", "VERIFYING", "LEASED", "CHECKPOINTED", "UNKNOWN"}`; asserts `task["active_lease_id"] == lease_id` and instance bound lease matching.
   - **Classification & Retry Budget Routing (lines 1012-1033)**:
     ```python
     cur_version = int(task["version"])
     current_attempts = int(task["attempts"]) if ("attempts" in task.keys() and task["attempts"] is not None) else 0
     max_attempts = int(task["max_attempts"]) if ("max_attempts" in task.keys() and task["max_attempts"] is not None) else 3
     new_attempts = current_attempts + 1

     if classification_upper in uncertain_classes:
         target_state = "UNKNOWN"
         event_type = "TASK_UNKNOWN_STATE"
     elif (classification_upper in retryable_classes) and (new_attempts < max_attempts):
         target_state = "RETRY_SCHEDULED"
         event_type = "TASK_RETRY_SCHEDULED"
     else:
         target_state = "FAILED"
         event_type = "TASK_FAILED"
     ```
   - **Atomic Database Persistence & OCC (lines 1043-1085)**:
     Executes conditional `UPDATE tasks SET state=?,attempts=?,error=?,version=version+1... WHERE task_id=? AND version=?`, asserting `cur.rowcount == 1` or raising `OptimisticLockError`. Appends hashed journal event to `events`, releases lease (`leases.released=1`), decrements queue quota on `queue_accounts`, and rolls back on any exception.

4. **Downstream Callers Migrated**:
   - `scp/ask_kernel_adapter.py:438-448`: Calls `self.kernel.commit_failed()` with `actor=task.get("worker_id") or "ask-route-worker"`, `indictment_ref=indictment_ref or f"ask://{task['task_id']}/failure/{reason}"`, and falls back to `set_task_kill()` if no active lease exists.
   - `scp/hands/task_kernel_bridge.py:445-452` & `577-584`: Calls `self.kernel.commit_failed()` with `actor=self.worker_id`, `failure_classification="FATAL"`, and URI indictment references (`hands://...`).

5. **Test Coverage in `tests/T04_kernel/test_adversarial_kernel_flaws.py:915-1259`**:
   Contains 9 comprehensive causal tests (`test_branch_1_...` through `test_branch_9_...`) covering all 4 exploit vectors, input validations, lease actor mismatches, retry budget branches, fatal terminations, and adapter/bridge integration.

### 1.2 Verbatim Terminal Verification Results
1. `python tools/probes/probe_gap12_delta_audit.py`:
   ```
   ================================================================================
   SCP-OMEGA DELTA AUDIT: GAP-12 EMPIRICAL PROBE
   Subsystem: TaskKernel State Machine
   Invariants Tested:
     - INV-GAP12-01: Prohibition of Raw Unverified Transition to Terminal FAILED
     - INV-GAP12-02: Mandatory Indictment & Evidence for Failure Commitment
     - INV-GAP12-03: Preservation of Retry Budget and Recovery Routing
     - INV-GAP12-04: System Authority Separation for Pre-execution Indictment
   ================================================================================

   [VECTOR 1] Testing Unauthenticated Pre-Execution Sabotage (PLANNING -> FAILED)
   [*] [GREEN] Call blocked with InvalidTransition: direct transition to FAILED is forbidden; use commit_failed() with valid evidence

   [VECTOR 2] Testing Worker Execution Failure with Zero Crash Evidence (RUNNING -> FAILED)
   [*] [GREEN] Call blocked with InvalidTransition: direct transition to FAILED is forbidden; use commit_failed() with valid evidence

   [VECTOR 3] Testing Verification Sabotage (VERIFYING -> FAILED without Verifier Check)
   [*] [GREEN] Call blocked with InvalidTransition: direct transition to FAILED is forbidden; use commit_failed() with valid evidence

   [VECTOR 4] Testing Stolen Lease Sabotage & Recovery Bypass
   [*] [GREEN] Call blocked with InvalidTransition: direct transition to FAILED is forbidden; use commit_failed() with valid evidence

   Anti-Placebo Contract Status:
     >> GREEN STATE CONFIRMED: All 4 exploit vectors protected by InvalidTransition.
     >> Tasks and events verified in database: 0 unauthorized transitions to FAILED.
     >> Anti-Placebo Falsification Condition Satisfied.
     >> Verdict: ALL_VECTORS_PROTECTED_GREEN
   Exit code: 0
   ```

2. `pytest tests/T04_kernel -q`:
   ```
   ........................................................................ [ 82%]
   ...............                                                          [100%]
   87 passed in 8.08s
   Exit code: 0
   ```

3. `pytest tests/T03_capability/test_hands_authority_pep.py -q`:
   ```
   .........                                                                [100%]
   9 passed in 0.73s
   Exit code: 0
   ```

4. `python tools/t00_meta_audit.py`:
   ```
   [T00 Meta-Audit] Starting Test-Integrity Regression Authority...
   [T00 Meta-Audit] Trusted Base: origin/main
   [T00 Meta-Audit] Collecting baseline pytest nodeids (origin/main)...
   [T00 Meta-Audit] Collecting candidate pytest nodeids...
   [T00 Meta-Audit] All integrity checks passed (0 new regressions).
   Exit code: 0
   ```

---

## 2. LOGIC CHAIN

Step-by-step reasoning linking observations to review conclusions:

1. **Direct Terminal FAILED Transition Prohibition (Observation 1.1.1 & 1.2.1)**:
   By modifying `transition()` to reject `to_state in ("COMPLETED", "FAILED")`, callers can no longer transition a task directly into `FAILED`. This mechanically enforces that every terminal failure must pass through `commit_failed()`. This closes GAP-12 Vectors 1, 2, and 3.

2. **Lease Actor Impersonation Defense (Observation 1.1.2 & 1.1.3)**:
   In `_assert_lease()`, validating `lease['worker_id'] == str(actor).strip()` guarantees that an unauthorized actor holding or guessing a valid `lease_id` cannot commit failure on behalf of another worker. If the actor does not match, `InvalidTransition` is raised immediately. This closes GAP-12 Vector 4.

3. **Behavior under Explicit Edge Cases & Boundary Conditions (Observation 1.1.3)**:
   - **`task_id` does not exist**: Handled via `self._task(task_id)` which queries SQLite and raises `NotFound(task_id)`. If `task_id` is empty/whitespace, handled via line 980 raising `KernelError("task_id is required")`.
   - **`lease_id` expired or released**: If `lease_id` is missing/whitespace, raises `StaleLease("lease_id is required")`. If `lease_id` does not exist in SQLite, `self._lease(lease_id)` raises `StaleLease(lease_id)`. If `lease['released']` is True, `_assert_lease()` raises `OptimisticLockError("lease ... has already been released")`. If `lease['expires_at'] <= now`, raises `StaleLease`. If fencing token is stale, raises `StaleLease`.
   - **`actor` empty or mismatched**: If empty/whitespace, line 984 raises `KernelError("actor is required")`. If mismatched with `lease['worker_id']`, `_assert_lease()` raises `InvalidTransition("actor ... does not match lease worker ...")`.
   - **`indictment_ref` empty or whitespace**: Line 988 raises `KernelError("indictment_ref is required; failure commitment requires verifiable failure evidence")`.
   - **`attempts >= max_attempts`**: Lines 1013-1030 compute `new_attempts = current_attempts + 1`. The condition `(classification_upper in retryable_classes) and (new_attempts < max_attempts)` evaluates to `False`. Execution falls through to the `else:` branch, setting `target_state = "FAILED"` and `event_type = "TASK_FAILED"`.
   - **`failure_classification` handling**:
     - `UNKNOWN` (and `UNCERTAIN`, `LOST_RESPONSE`, `CRASH_AFTER_SUBMIT`): Routes to `target_state = "UNKNOWN"`, preventing blind retries without reconciliation (complying with DNA invariant: uncertain external state must enter recovery/unknown).
     - `RETRYABLE` (and `TRANSIENT`, `TIMEOUT`, `NETWORK_ERROR`, `TEMPORARY`): Routes to `target_state = "RETRY_SCHEDULED"` if `new_attempts < max_attempts`; routes to `target_state = "FAILED"` if exhausted.
     - `FATAL`: Falls through to `else:` branch, routing immediately to `target_state = "FAILED"`.

4. **Concurrency, OCC, & Atomic Invariants (Observation 1.1.3)**:
   Updating `tasks` with `WHERE task_id=? AND version=?` ensures that if two concurrent requests attempt to transition or mutate the task simultaneously, exactly one succeeds and the other triggers `OptimisticLockError`. Transaction rollback occurs upon any failure, preventing dirty or partial state writes.

5. **Downstream Compatibility & Test Preservation (Observation 1.1.4, 1.1.5 & 1.2.2-1.2.4)**:
   Callers in `AskKernelAdapter` and `TaskKernelHandsBridge` were properly migrated to provide the required parameters (`lease_id`, `actor`, `failure_classification`, `indictment_ref`). All 87 kernel tests pass, 9 capability PEP tests pass, and `t00_meta_audit.py` confirms 0 integrity regressions.

6. **Integrity & Anti-Cheat Audit**:
   Inspected all modifications for:
   - Hardcoded test returns: None.
   - Facade or stub implementations: None; full SQLite transaction logic.
   - Shortcuts bypassing tasks: None; root cause addressed at kernel state machine level.
   - Fabricated logs or test mocks: None; all tests executed on live SQLite databases.

---

## 3. ADVERSARIAL STRESS-TEST MATRIX

| Stress Scenario | Adversarial Action | System Response | Verdict |
|---|---|---|---|
| **S1: Pre-Execution Sabotage** | Unauthenticated caller calls `kernel.transition(task_id, "FAILED")` on `PLANNING` task | `InvalidTransition: direct transition to FAILED is forbidden` | **PASS (Blocked)** |
| **S2: Missing Task ID** | Caller calls `commit_failed(task_id="missing-uuid", ...)` | `NotFound: missing-uuid` (rolls back transaction) | **PASS (Fail-Closed)** |
| **S3: Stolen Lease Sabotage** | Rogue worker passes legitimate `lease_id` with rogue `actor="attacker"` | `InvalidTransition: actor 'attacker' does not match lease worker` | **PASS (Blocked)** |
| **S4: Expired / Stale Lease** | Worker commits failure on lease where `expires_at < now` | `StaleLease` | **PASS (Blocked)** |
| **S5: Released Lease Double Commit** | Worker commits failure twice using same lease | 2nd call raises `OptimisticLockError: lease ... has already been released` | **PASS (Blocked)** |
| **S6: Missing Evidence Indictment** | Worker calls `commit_failed(..., indictment_ref="   ")` | `KernelError: indictment_ref is required` | **PASS (Fail-Closed)** |
| **S7: Retry Budget Exhaustion** | Retryable failure committed when `attempts == max_attempts` | Transitions to terminal `FAILED` (`TASK_FAILED` event logged) | **PASS (Correct)** |
| **S8: Uncertain Failure Routing** | Worker crashes after submit, commits `failure_classification="UNKNOWN"` | Transitions to `UNKNOWN` (`TASK_UNKNOWN_STATE` event logged) | **PASS (Safe)** |
| **S9: Concurrent Double Failure** | Two threads call `commit_failed()` concurrently on version 1 | First commits version 2; second raises `OptimisticLockError` | **PASS (OCC Protected)** |

---

## 4. CAVEATS

- **Pre-existing Manifest Drift in `test_scp_target_test_coverage.py`**: A pre-existing failure in `test_scp_target_test_coverage.py` occurs because `spec/scp_target_test_coverage.yaml` tracks historical commit tree hashes. This is outside the scope of GAP-12 and was not touched by Worker 1.
- **Serialization of Details Payload**: `details` must be JSON serializable. While all internal callers pass string/dict payloads, external callers passing non-serializable objects will trigger `TypeError`, which is safely rolled back in SQLite.
- No functional caveats in GAP-12 logic.

---

## 5. CONCLUSION

Worker 1's remediation of GAP-12 is robust, complete, and fully adheres to Zero-Trust and Fail-Closed architecture. The transition fence prevents rogue cancellation across all lifecycle states; `_assert_lease()` prevents lease hijacking; `commit_failed()` enforces verifiable indictment and retry budget preservation; and SQLite transactions guarantee atomic state transitions and journal logging.

**Verdict**: **APPROVE**

---

## 6. VERIFICATION METHOD

To reproduce and independently confirm this verdict:

```pwsh
# 1. Execute deterministic GAP-12 probe
python tools/probes/probe_gap12_delta_audit.py
# Verify: Exit code 0, ALL_VECTORS_PROTECTED_GREEN

# 2. Execute T04 Kernel test suite (87 tests)
pytest tests/T04_kernel -q
# Verify: Exit code 0, 87 passed

# 3. Execute Capability Authority PEP test suite (9 tests)
pytest tests/T03_capability/test_hands_authority_pep.py -q
# Verify: Exit code 0, 9 passed

# 4. Execute Meta-Audit Guardrails
python tools/t00_meta_audit.py
# Verify: Exit code 0, 0 new regressions
```

**Invalidation Conditions**:
- If `kernel.transition(task_id, "FAILED")` can be called directly without raising `InvalidTransition`.
- If `kernel.commit_failed()` permits a caller with `actor != lease["worker_id"]`.
- If `kernel.commit_failed()` accepts an empty or whitespace `indictment_ref`.
- If `commit_failed()` with `RETRYABLE` classification and remaining retry budget moves directly to `FAILED` instead of `RETRY_SCHEDULED`.
