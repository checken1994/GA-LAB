# Handoff Report — GAP-12 Delta Audit Investigation

**Agent:** explorer_survey_8_1 (`teamwork_preview_explorer`)  
**Working Directory:** `c:\Users\check\Downloads\scp\.agents\explorer_survey_8_1`  
**Recipient / Parent Conversation ID:** `55c745a6-7ce1-4c1e-9385-e614d0c57946`  
**Handoff Type:** Hard (Investigation complete)  
**Date:** 2026-09-08T01:28:30+07:00  

---

## 1. Observation

1. **Absence of Guard for `to_state == "FAILED"` in `taskkernel.py`:**
   In `scp/task_kernel_parts/taskkernel.py`, lines 253–256 guard `COMPLETED` following GAP-11:
   ```python
   if to_state == "COMPLETED":
       raise InvalidTransition(
           "direct transition to COMPLETED is forbidden; use commit_completed() with valid evidence"
       )
   ```
   No equivalent guard exists for `to_state == "FAILED"`.

2. **Reachability of `FAILED` from Non-terminal States:**
   In `scp/task_kernel.py`, lines 23–42 define `ALLOWED_TRANSITIONS`:
   - Line 25: `"PLANNING": {"READY", "WAITING_APPROVAL", "FAILED", "CANCELLED"}`
   - Line 30: `"RUNNING": {"WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "RECOVERING", "HUMAN_REVIEW", "FAILED", "CANCELLED"}`
   - Line 31: `"WAITING_TOOL": {"VERIFYING", "UNKNOWN", "RECOVERING", "FAILED", "CANCELLED"}`
   - Line 32: `"VERIFYING": {"RUNNING", "COMPLETED", "HUMAN_REVIEW", "FAILED"}`
   - Lines 34, 35, 36, 37, 38: `FAILED` is reachable from `UNKNOWN`, `HUMAN_REVIEW`, `RECOVERING`, `RECONCILING`, `RETRY_SCHEDULED`.

3. **Unleased State Lease Bypass in `taskkernel.py`:**
   In `scp/task_kernel_parts/taskkernel.py`, lines 310–330:
   ```python
   is_leased_state = old in {"LEASED", "RUNNING", "WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "UNKNOWN"}
   has_active_lease = bool(task["active_lease_id"])
   if is_leased_state or has_active_lease:
       ...
   elif caller_lease:
       lease_row = self._assert_lease(caller_lease, task_id)
       token = int(lease_row["fencing_token"])
   else:
       token = 0
   ```
   For `old == "PLANNING"`, `is_leased_state` is False, `has_active_lease` is False, and `caller_lease` can be None. The lease check is completely bypassed (`token = 0`).

4. **Terminal Immutability:**
   In `scp/task_kernel.py` line 22: `TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}`.
   In `scp/task_kernel_parts/taskkernel.py` line 280:
   ```python
   if old in TERMINAL:
       raise InvalidTransition("terminal task is immutable")
   ```
   Once a task is transitioned to `FAILED`, it cannot transition to any other state.

5. **Empirical Reproduction Outputs:**
   Running `tools/probes/probe_gap11_failed.py`:
   ```text
   $env:PYTHONPATH="."; python tools/probes/probe_gap11_failed.py
   RED: Transition to FAILED succeeded directly via transition()
   ```
   Running `tools/probes/probe_gap12_gap13_unproven_vulnerabilities.py`:
   ```text
   $env:PYTHONPATH="."; python tools/probes/probe_gap12_gap13_unproven_vulnerabilities.py
   [GAP-12.1] EXPLOIT CONFIRMED: PLANNING -> FAILED succeeded without crash evidence or verifier indictment.
   [GAP-12.2] EXPLOIT CONFIRMED: RUNNING -> FAILED succeeded with only worker self-claim.
   [GAP-12.3] EXPLOIT CONFIRMED: VERIFYING -> FAILED succeeded bypassing independent verifier check.
   [GAP-12.4] EXPLOIT CONFIRMED: Rogue actor sabotaged task into terminal FAILED using stolen lease.
   ```

6. **Downstream Callers:**
   In `scp/ask_kernel_adapter.py`, line 430:
   ```python
   def fail(self, task: dict[str, Any], reason: str) -> None:
       ...
       if current["state"] not in _TERMINAL:
           self.kernel.transition(task["task_id"], "FAILED", actor="ask-kernel-adapter", reason=reason)
   ```
   Tested via `tests/T04_kernel/test_adversarial_kernel_flaws.py:863` (`test_ask_kernel_adapter_caller_fail_and_finalize_integration`).

---

## 2. Logic Chain

1. Observations 1 and 2 show that `transition()` allows any caller to transition a task to `FAILED` from 9 different states (`PLANNING`, `RUNNING`, `VERIFYING`, etc.) because `FAILED` is present in `ALLOWED_TRANSITIONS` and lacks any check similar to line 253.
2. Observation 3 demonstrates that for pre-execution tasks in `PLANNING`, callers do not even need a lease; an unauthenticated caller can invoke `transition(task_id, "FAILED")` and the method executes the SQL update without lease or identity validation.
3. Observation 4 establishes that `FAILED` is a terminal state. Once mutated, `tasks` row is immutable, and the task cannot be recovered or retried.
4. Observation 5 empirically confirms across 4 distinct attack vectors (`PLANNING`, `RUNNING`, `VERIFYING`, rogue lease-holder) that `FAILED` transitions execute successfully on live runtime with zero failure evidence, zero verifier indictment, and zero failure classification.
5. Therefore, GAP-12 is a confirmed, critical vulnerability that allows rogue workers or unauthenticated actors to permanently sabotage tasks, bypassing `max_attempts` and the recovery state machine.
6. The remedy follows the exact precedent set by GAP-11: (a) block raw `transition(..., "FAILED")` with `InvalidTransition`, (b) introduce `commit_failed()` requiring active lease authority and verified failure evidence/classification, and (c) route transient worker failures through `UNKNOWN` / `RECOVERING`.

---

## 3. Caveats

1. **Production Code Untouched:** In strict accordance with FA-11 Rule 1 (Anti-Scope Creep) and the user's critical constraint ("DO NOT modify any production code"), no modifications to `scp/task_kernel_parts/taskkernel.py` or any other product file were made during this investigation.
2. **GAP-13 Scope Separation:** GAP-13 (`WAITING_APPROVAL -> READY` unauthenticated bypass) was also noted in `EMERGENCY_GAP_REPORT.md` and reproduced in `probe_gap12_gap13_unproven_vulnerabilities.py`. However, it addresses capability authorization and human approval gates, whereas GAP-12 is a lifecycle terminal state vulnerability. They should be addressed as distinct remediation tasks.
3. **Adapter Refactoring Required Upon Fix:** When GAP-12 is remediated, `scp/ask_kernel_adapter.py:430` and `tests/T04_kernel/test_adversarial_kernel_flaws.py:863` will need to update their `fail()` call path to use `commit_failed()` or pass appropriate failure metadata.

---

## 4. Conclusion

- GAP-12 (Unverified transition to FAILED / Rogue Worker Sabotage) is a **fully verified, highly impactful vulnerability** that is an ideal candidate for Delta Audit remediation.
- It is structurally symmetric to GAP-11, highly bounded within `scp/task_kernel_parts/taskkernel.py`, and completely verifiable through deterministic, non-flaky probe scripts.
- Four concrete invariants have been defined in `analysis.md` (INV-GAP12-01 through INV-GAP12-04), providing an exact blueprint for Phase 1 through Phase 5 of the Delta Audit.

---

## 5. Verification Method

To independently verify these findings:
1. **Run the Empirical Probe Script:**
   ```powershell
   $env:PYTHONPATH="."
   python tools/probes/probe_gap12_gap13_unproven_vulnerabilities.py
   ```
   Expected output: All 4 GAP-12 exploits confirm execution with exit code 0.
2. **Run the Focused Failed Probe:**
   ```powershell
   $env:PYTHONPATH="."
   python tools/probes/probe_gap11_failed.py
   ```
   Expected output: `RED: Transition to FAILED succeeded directly via transition()`.
3. **Inspect Implementation in `taskkernel.py`:**
   Inspect `scp/task_kernel_parts/taskkernel.py` lines 240–374 and note the absence of any check blocking `to_state == "FAILED"`.
4. **Invalidation Condition:**
   These findings would be invalidated if calling `transition(task_id, "FAILED")` from `PLANNING` or `RUNNING` raised `InvalidTransition` or required failure evidence. The terminal output demonstrates that it does neither.
