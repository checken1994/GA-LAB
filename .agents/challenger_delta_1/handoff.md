# Milestone M4 Adversarial Review Handoff Report

- **Agent:** `challenger_delta_1` (`teamwork_preview_challenger`)
- **Roles:** critic, specialist
- **Working Directory:** `c:\Users\check\Downloads\scp\.agents\challenger_delta_1`
- **Recipient / Parent Conversation ID:** `55c745a6-7ce1-4c1e-9385-e614d0c57946`
- **Timestamp:** 2026-09-08T01:36:00+07:00
- **Milestone:** M4 (Adversarial Challenge & Probe Verification)
- **Target Vulnerability:** GAP-12 — Unverified Terminal `FAILED` State Transition & Rogue Worker Sabotage
- **Target Subsystem:** `TaskKernel` (`scp/task_kernel_parts/taskkernel.py`, `scp/task_kernel.py`, `scp/ask_kernel_adapter.py`)
- **Verdict:** `APPROVE`

---

## 1. Observation

### 1.1 Direct Source Code Observations
1. **`scp/task_kernel_parts/taskkernel.py:251-256`:**
   ```python
   if to_state not in STATES and to_state != "WAITING_APPROVAL":
       raise InvalidTransition(f"unknown target state {to_state}")
   if to_state == "COMPLETED":
       raise InvalidTransition(
           "direct transition to COMPLETED is forbidden; use commit_completed() with valid evidence"
       )
   ```
   *Observation:* Direct transition to `COMPLETED` is explicitly blocked following GAP-11. However, there is NO check forbidding direct transition to `FAILED`.
2. **`scp/task_kernel.py:23-42` (`ALLOWED_TRANSITIONS` & `TERMINAL`):**
   ```python
   ALLOWED_TRANSITIONS = {
       "PLANNING": {"READY", "WAITING_APPROVAL", "FAILED", "CANCELLED"},
       "RUNNING": {"WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "RECOVERING", "HUMAN_REVIEW", "FAILED", "CANCELLED"},
       "VERIFYING": {"RUNNING", "COMPLETED", "HUMAN_REVIEW", "FAILED"},
       ...
   }
   TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
   ```
   *Observation:* `FAILED` is an explicitly allowed target transition from `PLANNING`, `RUNNING`, `VERIFYING`, `WAITING_TOOL`, `UNKNOWN`, `HUMAN_REVIEW`, `RECOVERING`, `RECONCILING`, and `RETRY_SCHEDULED`. Furthermore, `FAILED` is classified as `TERMINAL`. Once reached, line 280 (`if old in TERMINAL: raise InvalidTransition("terminal task is immutable")`) permanently locks the task.
3. **`scp/task_kernel_parts/taskkernel.py:310-330` (Lease Authority Gate):**
   ```python
   is_leased_state = old in {"LEASED", "RUNNING", "WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "UNKNOWN"}
   has_active_lease = bool(task["active_lease_id"])
   if is_leased_state or has_active_lease:
       ...
   elif caller_lease:
       ...
   else:
       token = 0
   ```
   *Observation:* When a task is in `PLANNING` (`old == "PLANNING"`), `is_leased_state` is `False` and `has_active_lease` is `False`. If `caller_lease` is omitted, `token = 0` and zero lease validation or authentication is performed.
4. **`scp/task_kernel_parts/taskkernel.py:464-479` (`_assert_lease`):**
   ```python
   def _assert_lease(self, lease_id: str, task_id: str) -> Any:
       lease = self._lease(lease_id)
       control = self._control()
       now = time.time()
       if lease['task_id'] != task_id or lease['released'] or lease['expires_at'] <= now or (lease['global_kill_epoch'] != control['global_kill_epoch']) or control['global_kill']:
           if lease['released']:
               raise OptimisticLockError(...)
           raise StaleLease(lease_id)
       latest = self.conn.execute('SELECT COALESCE(MAX(fencing_token), 0) AS n FROM leases WHERE task_id=?', (task_id,)).fetchone()['n']
       if int(lease['fencing_token']) != int(latest):
           raise StaleLease(lease_id)
       return lease
   ```
   *Observation:* `_assert_lease` checks only `task_id`, release state, expiration, kill epoch, and fencing token. It NEVER checks whether the caller `actor` matches `lease['worker_id']`. Neither does `transition()`.
5. **`scp/meta/why_gate.py:226-258` (`WhyGate.gate`):**
   In `taskkernel.py:287-292`, `get_why_gate().gate()` is called with `llm_enabled=False`. In this mode, `_check_falsification()` only scans regex patterns in `FALSIFICATION_REJECT_PATTERNS`. Because normal failure reasons do not match patterns like `delete.*rule` or `whitelist`, `WhyGate` returns `ALLOW` or `UPHOLD`, neither of which raises `InvalidTransition`.
6. **`scp/task_kernel_parts/taskkernel.py:recovery_decision`:**
   `TaskKernel.recovery_decision()` routes recoverable errors to `QUEUED` or `RECONCILING` or `HUMAN_REVIEW`. However, `transition(..., "FAILED")` bypasses `recovery_decision()`, `reconcile_unknown()`, and `task["max_attempts"]` entirely.
7. **`scp/ask_kernel_adapter.py:426-439` and `tests/T04_kernel/test_adversarial_kernel_flaws.py:886-892`:**
   `ask_kernel_adapter.fail()` invokes `self.kernel.transition(task["task_id"], "FAILED", actor="ask-kernel-adapter", reason=reason)`. Test `test_adversarial_kernel_flaws.py:891` explicitly asserts that this leaves the task in `"FAILED"`.

### 1.2 Verbatim Probe Execution & Determinism
Command executed directly on live environment:
```powershell
python tools/probes/probe_gap12_delta_audit.py
```
Exit code: `0`
Verbatim output snippet:
```text
================================================================================
SCP-OMEGA DELTA AUDIT: GAP-12 EMPIRICAL PROBE
Subsystem: TaskKernel State Machine
...
PROBE RESULTS SUMMARY & ANTI-PLACEBO CONTRACT EVALUATION
================================================================================
  VECTOR_1: PLANNING -> FAILED (Unauthenticated, No Lease, No Evidence)
    Verdict: VULNERABILITY_PROVEN_RED
  VECTOR_2: RUNNING -> FAILED (No Crash Evidence / Zero Indictment)
    Verdict: VULNERABILITY_PROVEN_RED
  VECTOR_3: VERIFYING -> FAILED (Verifier Check Bypassed)
    Verdict: VULNERABILITY_PROVEN_RED
  VECTOR_4: Stolen Lease Sabotage (Recovery Machine Bypassed)
    Verdict: VULNERABILITY_PROVEN_RED

Anti-Placebo Contract Status:
  >> RED STATE CONFIRMED: All 4 exploit vectors succeed on current codebase.
  >> Vulnerability GAP-12 is actively exploitable at the database layer.
```
- **Determinism Stress-Test:** A stress-test loop executing 5 consecutive subprocess invocations of `python tools/probes/probe_gap12_delta_audit.py` resulted in:
  `All 5 consecutive probe runs succeeded deterministically with RED STATE CONFIRMED!` (100% reproducibility, 0% flakiness).
- **Physical SQLite Verification:**
  - Raw `tasks` table rows: all 4 tasks mutated to `state='FAILED'`, `version` incremented, `active_lease_id` cleared to `None`, `active_fencing_token` set to `0`.
  - Raw `events` table rows: 4 distinct `STATE_TRANSITION` events committed to disk recording transitions to `FAILED`.
- **Regression Suite:**
  `pytest tests/T04_kernel -q` yielded `78 passed in 8.12s` (exit code `0`).

---

## 2. Logic Chain

1. **Absence of Artificial Mocking (Grounding: Observation 1.1, 1.2):**
   Inspection of `tools/probes/probe_gap12_delta_audit.py` proves it does not import or use `unittest.mock`, `MagicMock`, or monkeypatched functions. It instantiates `TaskKernel(db_path)` against a physical temporary SQLite file created via `tempfile.mkstemp()`. The probe executes actual production SQLite queries and commits real transactions. Therefore, the findings are not test artifacts.
2. **Absence of Sleep Races (Grounding: Observation 1.2):**
   Inspection confirms zero calls to `time.sleep()` or asynchronous scheduling in `tools/probes/probe_gap12_delta_audit.py`. All operations execute sequentially and synchronously. 5 consecutive automated test runs yielded identical results with zero flakiness.
3. **Absence of Hidden Guards (Grounding: Observation 1.1 #1, #3, #4, #5):**
   - `WhyGate`: With `llm_enabled=False`, it does not block failure transitions.
   - `_assert_lease`: Only checks lease existence, expiration, and fencing token, not caller identity (`actor`).
   - `transition()`: In unleased states like `PLANNING`, it skips lease assertion entirely.
   - Concurrency & Deduplication: Neither `expected_version` nor `event_id` is required, allowing unconstrained execution.
   Thus, no hidden guard prevents caller sabotage to `FAILED`.
4. **Validation of Exploit Vectors:**
   - *Vector 1 (PLANNING -> FAILED):* Proves an unauthenticated caller with no lease and no credentials can permanently kill an unstarted task.
   - *Vector 2 (RUNNING -> FAILED):* Proves a worker can crash a task on attempt 1 without providing failure evidence or traceback, discarding the remaining retry budget (`max_attempts=3`).
   - *Vector 3 (VERIFYING -> FAILED):* Proves that unlike `COMPLETED` (which requires `commit_completed` and verifier verdict), `FAILED` can be invoked unilaterally from `VERIFYING` without verifier indictment.
   - *Vector 4 (Stolen Lease Sabotage):* Proves that any rogue actor who possesses the `lease_id` can terminate a task into `FAILED`, because `TaskKernel` fails to bind the lease to the caller `actor`.

---

## 3. Caveats

1. **Downstream Caller Blast Radius (Critical for M5 Implementation):**
   `scp/ask_kernel_adapter.py:430` calls `self.kernel.transition(task["task_id"], "FAILED", actor="ask-kernel-adapter", reason=reason)`, and `tests/T04_kernel/test_adversarial_kernel_flaws.py:891` tests this behavior.
   When GAP-12 is resolved in M5 by blocking `transition(..., "FAILED")` and introducing `commit_failed()` / system authority, `ask_kernel_adapter.fail()` must be refactored to use the new method, and corresponding test assertions updated.
2. **No Production Code Modified:**
   In compliance with the challenger mandate and FA-11 Rule 1, `scp/` production code was untouched.

---

## 4. Conclusion

- **Verdict:** **`APPROVE`**.
- The GAP-12 vulnerability is conclusively and empirically **PROVEN** across all 4 attack vectors.
- The probe script `tools/probes/probe_gap12_delta_audit.py` is rock-solid, deterministic, and enforces the strict Anti-Placebo mandate (RED baseline confirmed on current code; falsification criteria defined for GREEN evolution).
- Physical SQLite state mutations are verified at the database layer (satisfying FA-08, FA-09, and FA-12 Step 4).
- The team is authorized to proceed to Milestone M5 (Remediation & Evolution Path).

---

## 5. Verification Method

1. **Run Standalone Deterministic Probe:**
   ```powershell
   python tools/probes/probe_gap12_delta_audit.py
   ```
   *Expected Output:* All 4 vectors return `VULNERABILITY_PROVEN_RED`, raw SQLite rows show `state=FAILED`, exit code `0`.
2. **Run Kernel Regression Suite:**
   ```powershell
   pytest tests/T04_kernel -q
   ```
   *Expected Output:* `78 passed`, exit code `0`.
3. **Invalidation Condition:**
   This assessment would be invalidated if `transition(task_id, "FAILED")` was rejected by an existing hidden guard or if the probe exhibited nondeterministic failure under repeated execution. Neither condition occurred.
