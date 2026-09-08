# Handoff Report: Adversarial Verification of TaskKernel State Machine Boundaries (GAP-13)

**Author**: Empirical Challenger #2 (`challenger_gap13_2`)  
**Parent Agent**: Orchestrator (`6c4f4b5d-80a9-4083-87c8-3858c1af90bc`)  
**Mission**: Adversarial challenge on TaskKernel State Machine Boundaries and Lifecycle Gates  
**Mandate Compliance**: Zero-Trust, Fail-Closed, FA-01 through FA-13 (FA-04 No Manufactured Green, FA-05 No Self-Granting Authority, FA-08 No Forged Provenance, FA-09 Exploit Mandate, FA-12 Empirical Closure, FA-13 Causal Test Coverage)  
**Verdict**: **CONFIRMED_CORRECT**  
**Date**: 2026-09-08T06:53:00Z  

---

## 1. Observation

### 1.1 Source Code Implementation Observations
Direct inspection of `scp/task_kernel_parts/taskkernel.py` reveals the following security enforcement boundaries:

1. **State Machine Definition & Transition Table (`scp/task_kernel.py:16-42`)**:
   - Total states in `STATES`: `{'CREATED', 'PLANNING', 'READY', 'QUEUED', 'LEASED', 'RUNNING', 'WAITING_TOOL', 'CHECKPOINTED', 'VERIFYING', 'UNKNOWN', 'RECOVERING', 'RECONCILING', 'HUMAN_REVIEW', 'RETRY_SCHEDULED', 'COMPLETED', 'FAILED', 'CANCELLED'}`.
   - `TERMINAL` states: `{'COMPLETED', 'FAILED', 'CANCELLED'}`.
   - `ALLOWED_TRANSITIONS["WAITING_APPROVAL"] = {"READY", "CANCELLED"}`.

2. **Raw Transition Gate from `WAITING_APPROVAL` (`scp/task_kernel_parts/taskkernel.py:403-406`)**:
   ```python
   if old == "WAITING_APPROVAL" and to_state == "READY":
       raise InvalidTransition(
           "direct transition from WAITING_APPROVAL to READY is forbidden; use commit_approval() with valid capability token"
       )
   ```

3. **`commit_approval()` Implementation (`scp/task_kernel_parts/taskkernel.py:1084-1181`)**:
   - **Line 1116**: `self._assert_not_killed()` is called *immediately* after transaction begin, before reading task or verifying tokens.
   - **Lines 1120-1126**:
     ```python
     if current_state in TERMINAL:
         raise InvalidTransition("terminal task is immutable")
     if current_state != "WAITING_APPROVAL":
         raise InvalidTransition(
             f"task {task_id} in state '{current_state}' cannot be approved; task must be in WAITING_APPROVAL"
         )
     ```
   - **Lines 1142-1153**: Atomic OCC database update:
     ```python
     cur = self.conn.execute(
         "UPDATE tasks SET state='READY', version=version+1, updated_at=? WHERE task_id=? AND version=? AND state='WAITING_APPROVAL'",
         (now_str, task_id, cur_version),
     )
     if cur.rowcount != 1:
         raise OptimisticLockError(...)
     ```
   - **Lines 1155-1176**: Append-only event journaling with token digest and transition metadata (`WAITING_APPROVAL` -> `READY`).

### 1.2 Empirical Adversarial Test Execution Results

We authored and executed a comprehensive adversarial boundary test suite in `tests/T04_kernel/test_gap13_state_machine_boundaries.py` covering 25 test cases across 5 attack vectors:

```text
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[CANCELLED] PASSED [  4%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[CHECKPOINTED] PASSED [  8%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[COMPLETED] PASSED [ 12%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[CREATED] PASSED [ 16%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[FAILED] PASSED [ 20%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[HUMAN_REVIEW] PASSED [ 24%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[LEASED] PASSED [ 28%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[PLANNING] PASSED [ 32%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[QUEUED] PASSED [ 36%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[READY] PASSED [ 40%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[RECONCILING] PASSED [ 44%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[RECOVERING] PASSED [ 48%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[RETRY_SCHEDULED] PASSED [ 52%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[RUNNING] PASSED [ 56%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[UNKNOWN] PASSED [ 60%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[VERIFYING] PASSED [ 64%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_commit_approval_on_all_non_waiting_states[WAITING_TOOL] PASSED [ 68%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_raw_transition_to_ready_under_all_variants PASSED [ 72%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_raw_transition_to_all_illegal_states_from_waiting_approval PASSED [ 76%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_global_kill_switch_during_commit_approval PASSED [ 80%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_attack_per_task_kill_on_waiting_approval PASSED [ 84%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_terminal_state_resurrection_strictly_prohibited[COMPLETED] PASSED [ 88%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_terminal_state_resurrection_strictly_prohibited[FAILED] PASSED [ 92%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_terminal_state_resurrection_strictly_prohibited[CANCELLED] PASSED [ 96%]
tests/T04_kernel/test_gap13_state_machine_boundaries.py::test_concurrent_commit_approval_race_exactly_one_winner PASSED [100%]

============================= 25 passed in 1.55s ==============================
```

### 1.3 Full Test Suite & Meta-Audit Executions
- `python -m pytest tests/T04_kernel/ -q --basetemp=reports/pytest-basetemp-c2`:
  `140 passed in 10.09s` (0 failures, 0 skips, 0 xfails).
- `python tools/t00_meta_audit.py`:
  `[T00 Meta-Audit] All integrity checks passed (0 new regressions).`

---

## 2. Logic Chain

1. **Attack Vector 1: Illegal State Approval Rejection**:
   - *Observation*: Calling `commit_approval()` with a legitimately signed `CapabilityToken` was attempted against every single one of the 17 non-`WAITING_APPROVAL` states.
   - *Inference*: In all 17 cases, `commit_approval()` raised `InvalidTransition` fail-closed.
   - *Physical DB Check*: Bypassing ORM/RAM layers, direct SQLite queries confirmed rowcount=0 mutated; task `state` and `version` remained strictly identical to pre-attack values; and exactly 0 `TASK_APPROVED` journal events were appended.
   - *Conclusion*: Non-waiting tasks cannot be approved or fast-tracked into `READY`.

2. **Attack Vector 2: Raw Transition Bypass Rejection**:
   - *Observation*: Calling `transition(task_id, 'READY')` from `WAITING_APPROVAL` was attempted with: default args, rogue actor, malicious override payload, spoofed lease_id, and spoofed event_id.
   - *Inference*: Line 403 unconditionally intercepts all attempts, raising `InvalidTransition("direct transition from WAITING_APPROVAL to READY is forbidden; use commit_approval() with valid capability token")`.
   - *Alternative targets*: Transitions from `WAITING_APPROVAL` to all other active states (`QUEUED`, `RUNNING`, `PLANNING`, etc.) are blocked by `ALLOWED_TRANSITIONS`. Only `CANCELLED` is permitted.
   - *Conclusion*: Raw transition bypass is completely impossible.

3. **Attack Vector 3: Global Kill Switch Integration**:
   - *Observation*: Activating the global kill switch (`kernel.set_global_kill(True)`) and immediately attempting `commit_approval()` on a `WAITING_APPROVAL` task.
   - *Inference*: Line 1116 calls `_assert_not_killed()` before task lookup or token verification, strictly raising `KillSwitchActive("global kill switch active")`.
   - *Physical DB Check*: Task remains in `WAITING_APPROVAL`, version unchanged, 0 journal events. Once toggled off, `commit_approval()` succeeds normally.
   - *Per-task kill*: Calling `kernel.set_task_kill(task_id)` cleanly transitions the task to `CANCELLED`. Subsequent `commit_approval()` attempts raise `InvalidTransition("terminal task is immutable")`.
   - *Conclusion*: Kill switches take precedence over approval operations fail-closed.

4. **Attack Vector 4: Terminal State Immutability**:
   - *Observation*: Tasks in `COMPLETED`, `FAILED`, and `CANCELLED` were subjected to `commit_approval()`, `set_task_kill()`, and `transition()` to active states (`READY`, `PLANNING`, `CREATED`, `QUEUED`, `RUNNING`, `WAITING_APPROVAL`).
   - *Inference*: Every single operation raised `InvalidTransition("terminal task is immutable")` or `InvalidTransition(f"{old}->{to_state}")`.
   - *Conclusion*: Terminal tasks are strictly immutable and cannot be resurrected or approved.

5. **Attack Vector 5: Concurrency Race Condition**:
   - *Observation*: 6 threads simultaneously executed `commit_approval()` on the same task.
   - *Inference*: Exactly 1 thread successfully committed (`READY`, version bumped by 1, 1 `TASK_APPROVED` event). The remaining 5 threads were fail-closed blocked by `OptimisticLockError` or `InvalidTransition`.
   - *Conclusion*: Atomic OCC fencing at the SQLite layer (`WHERE task_id=? AND version=? AND state='WAITING_APPROVAL'`) reliably serializes concurrent approval attempts.

---

## 3. Caveats

1. **Test Basetemp Isolation on Windows**: On Windows workstations, running pytest across multiple rapid invocations requires providing an isolated `--basetemp` (e.g. `--basetemp=reports/pytest-basetemp-c2`) to prevent transient file lock contention (`WinError 32`) on SQLite temporary files.
2. **Environment Variable Dependency**: `CapabilityToken` verification strictly requires `SCP_CAPABILITY_SECRET`. If omitted in production, `get_capability_secret()` raises `MissingSecretError` (GAP-09 fail-closed).

---

## 4. Conclusion

**Verdict: CONFIRMED_CORRECT**

The TaskKernel state machine boundaries, approval gate, and lifecycle invariants implemented for GAP-13 are mathematically sound, empirically verified, and robustly protected against adversarial exploitation:
- No state other than `WAITING_APPROVAL` can be approved via `commit_approval()`.
- Raw transitions from `WAITING_APPROVAL` to `READY` are strictly blocked.
- Global and per-task kill switches immediately halt approval attempts fail-closed.
- Terminal states (`COMPLETED`, `FAILED`, `CANCELLED`) remain strictly immutable.
- Concurrency races are safely resolved by atomic database OCC fencing.

---

## 5. Verification Method

To independently verify these adversarial challenge findings:

1. **Execute State Machine Boundary Adversarial Test Suite**:
   ```powershell
   python -m pytest tests/T04_kernel/test_gap13_state_machine_boundaries.py -v --basetemp=reports/pytest-basetemp-c2
   ```
   *Expected*: 25 passed in ~1.5s (Exit code 0).

2. **Execute Cryptographic Adversarial Challenge Test Suite**:
   ```powershell
   python -m pytest tests/T04_kernel/test_gap13_adversarial_challenge.py -v --basetemp=reports/pytest-basetemp-c2
   ```
   *Expected*: 17 passed in ~1.5s (Exit code 0).

3. **Execute Full Kernel Test Suite**:
   ```powershell
   python -m pytest tests/T04_kernel/ -q --basetemp=reports/pytest-basetemp-c2
   ```
   *Expected*: 140 passed (Exit code 0).

4. **Verify Meta-Audit Invariants**:
   ```powershell
   python tools/t00_meta_audit.py
   ```
   *Expected*: `[T00 Meta-Audit] All integrity checks passed (0 new regressions)` (Exit code 0).
