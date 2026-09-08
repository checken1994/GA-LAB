# Handoff Report: GAP-13 Delta Audit Survey (WAITING_APPROVAL Bypass to READY)

**Agent:** `explorer_survey_8_2` (teamwork_preview_explorer)  
**Parent ID:** `55c745a6-7ce1-4c1e-9385-e614d0c57946`  
**Working Directory:** `c:\Users\check\Downloads\scp\.agents\explorer_survey_8_2`  
**Date:** 2026-09-08T01:28:15+07:00  
**Status:** COMPLETE (Hard Handoff)

---

## 1. Observation

1. **Empirical Reproduction Command & Output:**
   Command: `python -m tools.probes.probe_gap12_gap13_unproven_vulnerabilities`
   Terminal Output:
   ```text
   [PROBE GAP-12/13] Probing Unproven Branches for Peripheral GAPs...
   ...
   --- GAP-13: WAITING_APPROVAL Unauthenticated Bypass ---
   [GAP-13.1] Task moved to WAITING_APPROVAL.
   [GAP-13.2] EXPLOIT CONFIRMED: WAITING_APPROVAL -> READY succeeded with zero tokens or cryptographic signatures.
   ALL GAP-12 AND GAP-13 UNPROVEN VULNERABILITIES EMPIRICALLY REPRODUCED!
   Exit code: 0
   ```
2. **State Set Incompleteness in `scp/task_kernel.py`:**
   Lines 16–21:
   ```python
   STATES = {
       "CREATED", "PLANNING", "READY", "QUEUED", "LEASED", "RUNNING",
       "WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "UNKNOWN", "RECOVERING",
       "RECONCILING", "HUMAN_REVIEW", "RETRY_SCHEDULED", "COMPLETED",
       "FAILED", "CANCELLED",
   }
   ```
   `WAITING_APPROVAL` is missing from `STATES`.
3. **Ad-hoc Workaround in `scp/task_kernel_parts/taskkernel.py`:**
   Lines 251–252:
   ```python
   if to_state not in STATES and to_state != "WAITING_APPROVAL":
       raise InvalidTransition(f"unknown target state {to_state}")
   ```
4. **Allowed Transitions Table in `scp/task_kernel.py`:**
   Lines 25–26:
   ```python
   "PLANNING": {"READY", "WAITING_APPROVAL", "FAILED", "CANCELLED"},
   "WAITING_APPROVAL": {"READY", "CANCELLED"},
   ```
5. **Absence of Approval / Token / Lease Checks in `transition()` in `scp/task_kernel_parts/taskkernel.py`:**
   - Lines 283–301: WHY gate only runs for `to_state in ("COMPLETED", "FAILED", "RUNNING", "CHECKPOINTED", "VERIFYING")`. `to_state == "READY"` is completely skipped.
   - Lines 310–312: Lease checks only run for `is_leased_state = old in {"LEASED", "RUNNING", "WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "UNKNOWN"}` or when `task["active_lease_id"]` is set. `WAITING_APPROVAL` has no active lease and is not in the set.
   - Lines 347–358: Direct SQL update `UPDATE tasks SET state='READY', version=version+1...` executes unconditionally.
6. **In-Flight Set Omission in `scp/ask_kernel_adapter.py`:**
   Lines 82–86:
   ```python
   _IN_FLIGHT_STATES = {
       "CREATED", "PLANNING", "READY", "QUEUED", "LEASED", "RUNNING",
       "WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "UNKNOWN",
       "RECOVERING", "RECONCILING", "RETRY_SCHEDULED",
   }
   ```
   `WAITING_APPROVAL` is missing.

---

## 2. Logic Chain

1. From **Observation 4**, `ALLOWED_TRANSITIONS["WAITING_APPROVAL"]` explicitly lists `"READY"`.
2. From **Observation 5**, when `to_state == "READY"` and `old == "WAITING_APPROVAL"`:
   - Target state validation succeeds (`"READY"` is in `STATES`).
   - The WHY Gate does not inspect transitions to `"READY"`.
   - The Lease Authority Gate is bypassed because `WAITING_APPROVAL` is not a leased state and has `active_lease_id == None`.
   - No approval token, HMAC signature, human confirmation, or caller capability check exists in `transition()`.
3. Therefore, any unprivileged caller or rogue actor can call `kernel.transition(task_id, "READY")` on any task in `WAITING_APPROVAL`.
4. From **Observation 1**, this bypass was executed in practice on the live terminal, confirming that a task waiting for approval transitions to `READY` without credentials.
5. From **Observation 2 & 3**, `WAITING_APPROVAL` is an incompletely integrated state in `TaskKernel` that was patched via special-casing rather than formal inclusion in `STATES`.
6. From **Observation 6**, lack of `WAITING_APPROVAL` in `_IN_FLIGHT_STATES` causes deduplication and backpressure logic to misidentify waiting tasks as finished.
7. Consequently, human-in-the-loop and risk-governance boundaries in SCP are enforced only in high-level RAM structures (e.g. `AgentOrchestrator`), but fail-open at the database/kernel level, violating FA-10 and core Agent OS durability guarantees.

---

## 3. Caveats

1. **Production Code Unmodified:** In strict compliance with the prompt's critical constraint and FA-11 Rule 1 (Anti-Scope Creep), no production code files were altered.
2. **Subsystem Interaction Scope:** Investigation focused on `TaskKernel`, `AskKernelAdapter`, `Planner`, and `CapabilityToken`. External frontend/UI components connecting to `TaskKernel` via RPC/HTTP were not audited during this session.
3. **GAP-12 Interdependency:** GAP-12 (`transition(..., "FAILED")` unverified) also touches `TaskKernel.transition()`. While `WAITING_APPROVAL -> FAILED` is disallowed by `ALLOWED_TRANSITIONS`, `PLANNING -> FAILED` is open. Fixing GAP-13 should be coordinated with GAP-12.

---

## 4. Conclusion

GAP-13 is a **proven, high-severity architectural vulnerability** that completely circumvents human-in-the-loop governance for high-risk actions.
It is an ideal and immediate candidate for a full **Delta Audit** remediation cycle because:
1. The flaw is 100% deterministically reproducible via an empirical probe (< 1s execution).
2. The root cause is pinpointed to the lack of an approval gate in `TaskKernel.transition()` and state set asymmetry.
3. Five precise invariants (INV-GAP13-01 through 05) have been defined for Phase 1.
4. The remediation pattern mirrors GAP-11 (`commit_completed()`), replacing the raw transition with an authenticated, HMAC-verified `commit_approved()` gate.

---

## 5. Verification Method

To independently verify these findings on this repository:
1. Run the existing unproven vulnerabilities probe:
   ```pwsh
   python -m tools.probes.probe_gap12_gap13_unproven_vulnerabilities
   ```
   *Expected outcome:* Exit code 0, printing `[GAP-13.2] EXPLOIT CONFIRMED: WAITING_APPROVAL -> READY succeeded with zero tokens or cryptographic signatures.`
2. Inspect `scp/task_kernel.py`:
   - Verify `"WAITING_APPROVAL"` is absent from `STATES` (lines 16–21).
   - Verify `"WAITING_APPROVAL": {"READY", "CANCELLED"}` in `ALLOWED_TRANSITIONS` (lines 25–26).
3. Inspect `scp/task_kernel_parts/taskkernel.py`:
   - Verify line 251 contains `if to_state not in STATES and to_state != "WAITING_APPROVAL":`.
   - Verify lines 283–346 contain zero checks for approval tokens when `old == "WAITING_APPROVAL"` and `to_state == "READY"`.
4. Review detailed analysis report at:
   `c:\Users\check\Downloads\scp\.agents\explorer_survey_8_2\analysis.md`
