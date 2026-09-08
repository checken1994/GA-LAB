# Independent Review & Adversarial Critic Report: GAP-12 Delta Audit

- **Agent:** `reviewer_delta_2` (`teamwork_preview_reviewer`)
- **Roles:** Reviewer, Adversarial Critic
- **Working Directory:** `c:\Users\check\Downloads\scp\.agents\reviewer_delta_2`
- **Parent Conversation ID:** `55c745a6-7ce1-4c1e-9385-e614d0c57946`
- **Date:** 2026-09-08T01:36:00+07:00
- **Target Subsystem:** TaskKernel State Machine (`scp/task_kernel_parts/taskkernel.py`, `scp/task_kernel.py`)
- **Reviewed Work Product:** `worker_m4_probe/handoff.md` and `tools/probes/probe_gap12_delta_audit.py`
- **Review Verdict:** **APPROVE**

---

## 1. Observation

### 1.1 Independent Probe Execution & Physical SQLite Verification
Command executed:
```powershell
python tools/probes/probe_gap12_delta_audit.py
```
Exit code: `0`
Verbatim stdout observed:
```text
================================================================================
SCP-OMEGA DELTA AUDIT: GAP-12 EMPIRICAL PROBE
Subsystem: TaskKernel State Machine
Invariants Tested:
  - INV-GAP12-01: Prohibition of Raw Unverified Transition to Terminal FAILED
  - INV-GAP12-02: Mandatory Indictment & Evidence for Failure Commitment
  - INV-GAP12-03: Preservation of Retry Budget and Recovery Routing
  - INV-GAP12-04: System Authority Separation for Pre-execution Indictment
================================================================================

--------------------------------------------------------------------------------
[VECTOR 1] Testing Unauthenticated Pre-Execution Sabotage (PLANNING -> FAILED)
--------------------------------------------------------------------------------
[*] Task created: ID=task_gap12_v1, State=PLANNING, ActiveLease=None
[!] [RED] EXPLOIT SUCCEEDED: Unauthenticated actor transitioned task directly to FAILED!
    Task State: FAILED, Version: 3
    Invariant Violated: INV-GAP12-01 & INV-GAP12-04 (No authority or evidence required)

--------------------------------------------------------------------------------
[VECTOR 2] Testing Worker Execution Failure with Zero Crash Evidence (RUNNING -> FAILED)
--------------------------------------------------------------------------------
[*] Task running: ID=task_gap12_v2, State=RUNNING, Lease=lease_8866a4e2d4785e83b4897b46, MaxAttempts=3
[!] [RED] EXPLOIT SUCCEEDED: Worker transitioned task directly to terminal FAILED on attempt 1!
    Task State: FAILED, Version: 7, ActiveLease: None
    Invariant Violated: INV-GAP12-01, INV-GAP12-02 & INV-GAP12-03 (No failure evidence, retry budget discarded)

--------------------------------------------------------------------------------
[VECTOR 3] Testing Verification Sabotage (VERIFYING -> FAILED without Verifier Check)
--------------------------------------------------------------------------------
[*] Task in verification: ID=task_gap12_v3, State=VERIFYING, Lease=lease_5ffad4784788c2241b8fc580
[!] [RED] EXPLOIT SUCCEEDED: Task terminated in FAILED without independent verifier indictment!
    Task State: FAILED, Version: 8
    Invariant Violated: INV-GAP12-01 & INV-GAP12-02 (Missing verifier counter-evidence)

--------------------------------------------------------------------------------
[VECTOR 4] Testing Stolen Lease Sabotage & Recovery Bypass
--------------------------------------------------------------------------------
[*] Task running: ID=task_gap12_v4, LegitimateWorker=legitimate_worker_delta, Lease=lease_5e5d273982d20145b25d3fa1
[!] [RED] EXPLOIT SUCCEEDED: Rogue actor with stolen lease killed task into terminal FAILED!
    Task State: FAILED, Version: 7, RemainingAttempts: Discarded
    Invariant Violated: INV-GAP12-01, INV-GAP12-02 & INV-GAP12-03 (Recovery engine completely bypassed)

================================================================================
FA-12 STEP 4: PHYSICAL SQLITE PERSISTENCE INSPECTION
Inspecting physical database file: C:\Users\check\AppData\Local\Temp\tmp6_1h9rf5_gap12_probe.sqlite3
================================================================================

--- RAW SQLITE: 'tasks' TABLE ROWS ---
  [Row] task_id=task_gap12_v1 | state=FAILED | version=3 | active_lease=None | fencing_token=0 | max_attempts=3
  [Row] task_id=task_gap12_v2 | state=FAILED | version=7 | active_lease=None | fencing_token=0 | max_attempts=3
  [Row] task_id=task_gap12_v3 | state=FAILED | version=8 | active_lease=None | fencing_token=0 | max_attempts=3
  [Row] task_id=task_gap12_v4 | state=FAILED | version=7 | active_lease=None | fencing_token=0 | max_attempts=3

--- RAW SQLITE: 'events' TABLE TRANSITION JOURNAL ---
  [Event] task_id=task_gap12_v1 | seq=3 | type=STATE_TRANSITION | transition=PLANNING->FAILED | actor=unauthenticated_attacker_v1 | reason='arbitrary_external_cancellation_without_proof'
  [Event] task_id=task_gap12_v2 | seq=7 | type=STATE_TRANSITION | transition=RUNNING->FAILED | actor=worker_beta | reason='unverified_worker_crash_claim'
  [Event] task_id=task_gap12_v3 | seq=8 | type=STATE_TRANSITION | transition=VERIFYING->FAILED | actor=worker_gamma | reason='sabotage_in_verifying_phase'
  [Event] task_id=task_gap12_v4 | seq=7 | type=STATE_TRANSITION | transition=RUNNING->FAILED | actor=rogue_saboteur_delta | reason='malicious_kill_via_stolen_lease'

Total terminal FAILED transition events recorded in DB: 4

================================================================================
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
  >> Anti-Placebo Falsification Condition: Upon implementing INV-GAP12-01 through 04,
     calls to transition(..., 'FAILED') must raise InvalidTransition, causing this probe
     to record PROTECTED_GREEN for all vectors.
================================================================================
```

### 1.2 Kernel Regression Test Execution
Command executed:
```powershell
pytest tests/T04_kernel -q
```
Exit code: `0`
Verbatim stdout observed:
```text
........................................................................ [ 92%]
......                                                                   [100%]
78 passed in 7.18s
```

### 1.3 Git Production Tree Cleanliness Check
Command executed:
```powershell
git diff scp/
git status --porcelain
```
Output:
- `git diff scp/`: 0 bytes, exit code `0`.
- Untracked / modified items: Only metadata in `.agents/` and the probe script at `tools/probes/probe_gap12_delta_audit.py`.
- **Zero lines of production code in `scp/` were altered.**

### 1.4 Source Code & Architecture Inspection
- **`scp/task_kernel.py` lines 16–22 & 23–42:**
  `STATES` contains 17 states: `CREATED`, `PLANNING`, `READY`, `QUEUED`, `LEASED`, `RUNNING`, `WAITING_TOOL`, `VERIFYING`, `CHECKPOINTED`, `UNKNOWN`, `RECOVERING`, `RECONCILING`, `HUMAN_REVIEW`, `RETRY_SCHEDULED`, `COMPLETED`, `FAILED`, `CANCELLED`.
  `TERMINAL` is defined as `{"COMPLETED", "FAILED", "CANCELLED"}`.
  `ALLOWED_TRANSITIONS` permits direct transition to `FAILED` from 9 distinct states (`PLANNING`, `RUNNING`, `WAITING_TOOL`, `VERIFYING`, `UNKNOWN`, `HUMAN_REVIEW`, `RECOVERING`, `RECONCILING`, `RETRY_SCHEDULED`).
- **`scp/task_kernel_parts/taskkernel.py` lines 253–256:**
  GAP-11 protected `COMPLETED`:
  ```python
  if to_state == "COMPLETED":
      raise InvalidTransition("direct transition to COMPLETED is forbidden; use commit_completed() with valid evidence")
  ```
  However, no corresponding guard exists for `to_state == "FAILED"`.
- **`scp/task_kernel_parts/taskkernel.py` line 280:**
  `if old in TERMINAL: raise InvalidTransition("terminal task is immutable")`.
  Once a task transitions to `FAILED`, it is permanently immutable at the SQLite database layer.
- **`scp/task_kernel_parts/taskkernel.py` lines 303–330:**
  When transitioning from unleased states (`PLANNING`), `is_leased_state` is False and `caller_lease` is None, setting `token = 0` and bypassing all lease/authentication checks.
- **`scp/task_kernel_parts/taskkernel.py` lines 464–479 (`_assert_lease`):**
  Checks `task_id`, `released`, `expires_at`, `global_kill_epoch`, and `fencing_token`, but does NOT check `lease['worker_id'] == actor`.
- **Downstream Callers Found:**
  - `scp/ask_kernel_adapter.py:430`:
    `self.kernel.transition(task["task_id"], "FAILED", actor="ask-kernel-adapter", reason=reason)`
  - `scp/hands/task_kernel_bridge.py:449` & `586`:
    `self.kernel.transition(task_id, "FAILED", actor="hands-kernel-bridge", reason=...)`

---

## 2. Logic Chain

1. **State Machine Immutability Amplifies Severity (Observation 1.4):**
   Because `FAILED` is an immutable terminal state (`old in TERMINAL -> InvalidTransition`), any unauthorized, unverified, or premature transition into `FAILED` causes permanent task death.
2. **Missing Gate Creates GAP-11 Symmetrical Hole (Observations 1.1 & 1.4):**
   GAP-11 correctly identified that allowing raw `transition(..., "COMPLETED")` permitted fake passes. However, leaving `transition(..., "FAILED")` unblocked created an exact mirror vulnerability: rogue actors or crashing workers can unilaterally condemn a task without providing an indictment, crash log, or evidence token.
3. **Exploit Mechanics Proven across All 4 Vectors (Observation 1.1):**
   - In `PLANNING`, an unauthenticated attacker calls `transition()` with no credentials or lease; the kernel executes the update because lines 329–330 do not enforce lease or authority for non-leased states.
   - In `RUNNING`, worker crashes discard the retry budget (`max_attempts = 3`) and bypass the OCC recovery pipeline (`UNKNOWN` -> `RECOVERING` -> `RECONCILING`), terminating the task on attempt 1.
   - In `VERIFYING`, the verification phase is aborted to `FAILED` without an independent verifier report or evidence ref.
   - A stolen lease holder can kill running tasks because `_assert_lease` checks only token currency, not worker identity.
4. **Physical Persistence Confirmed (Observation 1.1, FA-12 Step 4):**
   Direct inspection via `sqlite3.connect()` verified that `tasks` rows were updated to `state = 'FAILED'`, `version` incremented, and `active_lease_id` cleared to NULL. Events were permanently committed to `events`. This confirms that the exploit operates at the database layer, not via RAM artifacts.
5. **Anti-Placebo Contract Soundness (Observation 1.1):**
   The probe evaluates the true state of the codebase. It records `VULNERABILITY_PROVEN_RED` when transitions succeed, and `PROTECTED_GREEN` when blocked with `InvalidTransition`. This satisfies FA-09 and guarantees zero-placebo test mechanics when remediation is implemented in M5.
6. **Downstream Callers are Impacted (Observation 1.4):**
   Downstream components (`AskKernelAdapter.fail()`, `TaskKernelBridge`) rely on `transition(..., "FAILED")`. In M5, these callers must be updated to use the new authorized failure commitment API (`commit_failed()`), or utilize administrative authority.
7. **Zero Production Mutation & Strict Non-Regression (Observations 1.2 & 1.3):**
   The workspace is clean (`git diff scp/` is empty) and all 78 existing kernel tests pass cleanly, meeting the critical constraints of the audit phase.

---

## 3. Review Findings & Adversarial Challenges

### 3.1 Review Summary
**Verdict:** **APPROVE**
The worker's handoff report, invariant formulations (INV-GAP12-01 to 04), standalone probe script, and physical evidence strictly comply with the SCP-Omega Delta Audit protocol (`scp-delta-audit`), SCP DNA, and FA-01 through FA-13.

### 3.2 Finding 1 (Major — Downstream Caller Remediation Requirement)
- **What:** Downstream callers (`AskKernelAdapter.fail()` and `TaskKernelBridge`) currently call raw `kernel.transition(task_id, "FAILED")`.
- **Where:** `scp/ask_kernel_adapter.py:430`, `scp/hands/task_kernel_bridge.py:449, 586`.
- **Why:** When `transition(..., "FAILED")` is blocked with `InvalidTransition` in Milestone M5, these callers will fail unless migrated to `commit_failed()` or provided with system authority.
- **Suggestion:** In M5, design `commit_failed(task_id, lease_id, indictment, error_payload)` and update `AskKernelAdapter.fail()` and `TaskKernelBridge` to pass structured failure evidence.

### 3.3 Finding 2 (Adversarial Critic — Lease Actor Spoofing in `_assert_lease`)
- **What:** `_assert_lease(lease_id, task_id)` verifies token currency and expiration, but does NOT verify that the transition caller (`actor`) matches `lease['worker_id']`.
- **Where:** `scp/task_kernel_parts/taskkernel.py:464–479`.
- **Why:** Even with `commit_failed()`, a rogue agent who discovers or sniffs a lease ID could forge a failure indictment if caller identity is not bound to lease ownership.
- **Suggestion:** When implementing `commit_failed()`, enforce that `actor == lease['worker_id']` or require `is_system` administrative authority.

### 3.4 Verified Claims
- `tools/probes/probe_gap12_delta_audit.py` reproduces RED state on 4 vectors → **VERIFIED** via independent execution (exit code 0).
- Physical SQLite mutation occurs on `tasks` and `events` → **VERIFIED** via raw sqlite3 query.
- No production code modified in `scp/` → **VERIFIED** via `git diff scp/` (clean).
- Kernel regression suite passes → **VERIFIED** via `pytest tests/T04_kernel -q` (78 passed).

### 3.5 Integrity Checklist (Zero Violations)
- Hardcoded test results / expected outputs embedded in source code: **NONE**
- Dummy or facade implementations: **NONE**
- Shortcuts bypassing intended task: **NONE**
- Fabricated verification outputs or logs: **NONE**
- Evidence of self-certifying work without genuine verification: **NONE**

---

## 4. Caveats

1. **Audit Phase Boundary:** In accordance with the prompt and FA-11 Anti-Scope Creep, production code in `scp/` was not modified during this review.
2. **GAP-13 Excluded from Current Audit:** Invariants and probes were strictly bounded to GAP-12 (Terminal FAILED transition & sabotage). GAP-13 (`WAITING_APPROVAL -> READY` capability token bypass) remains documented as an unproven admission control gap to be addressed in its designated cycle.

---

## 5. Conclusion

The GAP-12 Delta Audit evidence presented by `worker_m4_probe` is empirically sound, methodologically rigorous, and completely verified. The vulnerability is demonstrated at the physical SQLite layer across 4 attack vectors without flakiness or mock artifacts. 

The audit work is **APPROVED**. The system is ready to proceed to Milestone M5 (Evolution Path & Remediation Specification).

---

## 6. Verification Method

To independently verify this report:

1. **Execute GAP-12 Empirical Probe:**
   ```powershell
   python tools/probes/probe_gap12_delta_audit.py
   ```
   *Expected:* Exit code 0, all 4 vectors report `VULNERABILITY_PROVEN_RED`, physical SQLite tables confirm 4 tasks in `FAILED`.
2. **Execute Kernel Suite:**
   ```powershell
   pytest tests/T04_kernel -q
   ```
   *Expected:* Exit code 0, 78 passed.
3. **Verify Git Tree Cleanliness:**
   ```powershell
   git diff scp/
   ```
   *Expected:* Output empty, confirming zero production modifications.
