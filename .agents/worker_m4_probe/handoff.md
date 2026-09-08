# Milestone M4 Handoff Report: GAP-12 Probe Execution & Anti-Placebo Evidence

- **Agent:** `worker_m4_probe` (`teamwork_preview_worker`)
- **Working Directory:** `c:\Users\check\Downloads\scp\.agents\worker_m4_probe`
- **Recipient / Parent Conversation ID:** `55c745a6-7ce1-4c1e-9385-e614d0c57946`
- **Date:** 2026-09-08T01:32:00+07:00
- **Milestone:** M4 (Probe Execution & Anti-Placebo Evidence)
- **Target Vulnerability:** GAP-12 — Unverified Terminal `FAILED` State Transition & Rogue Worker Sabotage
- **Target Subsystem:** `TaskKernel` (`scp/task_kernel_parts/taskkernel.py`, `scp/task_kernel.py`)
- **Authority / Guidelines:** `.agents/skills/scp-delta-audit/SKILL.md`, `.agents/skills/scp-dna/SKILL.md`, `.agents/AGENTS.md` (FA-01 to FA-13)

---

## 1. Observation

### 1.1 Dedicated Standalone Probe Script Created
A dedicated, deterministic, non-flaky probe script was created at:
`tools/probes/probe_gap12_delta_audit.py`

This script executes all 4 GAP-12 exploit vectors without sleep races, tests raw SQLite persistence, and evaluates the Anti-Placebo contract against invariants:
- **INV-GAP12-01:** Prohibition of Raw Unverified Transition to Terminal `FAILED`
- **INV-GAP12-02:** Mandatory Indictment & Evidence for Failure Commitment
- **INV-GAP12-03:** Preservation of Retry Budget and Recovery Routing
- **INV-GAP12-04:** System Authority Separation for Pre-execution Indictment

### 1.2 Verbatim Terminal Execution Output
Command executed:
```powershell
python tools/probes/probe_gap12_delta_audit.py
```
Exit code: `0`

Verbatim stdout:
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
[*] Task running: ID=task_gap12_v2, State=RUNNING, Lease=lease_0577ee60868b0450dcbb028f, MaxAttempts=3
[!] [RED] EXPLOIT SUCCEEDED: Worker transitioned task directly to terminal FAILED on attempt 1!
    Task State: FAILED, Version: 7, ActiveLease: None
    Invariant Violated: INV-GAP12-01, INV-GAP12-02 & INV-GAP12-03 (No failure evidence, retry budget discarded)

--------------------------------------------------------------------------------
[VECTOR 3] Testing Verification Sabotage (VERIFYING -> FAILED without Verifier Check)
--------------------------------------------------------------------------------
[*] Task in verification: ID=task_gap12_v3, State=VERIFYING, Lease=lease_625d7f3138c8443332fae930
[!] [RED] EXPLOIT SUCCEEDED: Task terminated in FAILED without independent verifier indictment!
    Task State: FAILED, Version: 8
    Invariant Violated: INV-GAP12-01 & INV-GAP12-02 (Missing verifier counter-evidence)

--------------------------------------------------------------------------------
[VECTOR 4] Testing Stolen Lease Sabotage & Recovery Bypass
--------------------------------------------------------------------------------
[*] Task running: ID=task_gap12_v4, LegitimateWorker=legitimate_worker_delta, Lease=lease_b724cba89c7de878b04559dd
[!] [RED] EXPLOIT SUCCEEDED: Rogue actor with stolen lease killed task into terminal FAILED!
    Task State: FAILED, Version: 7, RemainingAttempts: Discarded
    Invariant Violated: INV-GAP12-01, INV-GAP12-02 & INV-GAP12-03 (Recovery engine completely bypassed)

================================================================================
FA-12 STEP 4: PHYSICAL SQLITE PERSISTENCE INSPECTION
Inspecting physical database file: C:\Users\check\AppData\Local\Temp\tmp4ngzsi6q_gap12_probe.sqlite3
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

### 1.3 Regression Check
Command: `pytest tests/T04_kernel -q`
Result: `78 passed in 6.93s`, exit code `0`.
Zero regressions introduced. Production code in `scp/` was completely untouched (`git status` clean in `scp/`).

---

## 2. Logic Chain

1. **Vulnerability Mechanics in Current Code:**
   In `scp/task_kernel_parts/taskkernel.py`, lines 253–256 protect against raw transitions to `COMPLETED` following GAP-11:
   ```python
   if to_state == "COMPLETED":
       raise InvalidTransition(
           "direct transition to COMPLETED is forbidden; use commit_completed() with valid evidence"
       )
   ```
   However, no check exists for `to_state == "FAILED"`. Furthermore, in `scp/task_kernel.py`, `FAILED` is explicitly enumerated in `ALLOWED_TRANSITIONS` for `PLANNING`, `RUNNING`, `VERIFYING`, `WAITING_TOOL`, `UNKNOWN`, `HUMAN_REVIEW`, `RECOVERING`, `RECONCILING`, and `RETRY_SCHEDULED`.

2. **Vector 1 Proof (Observation 1.2, Vector 1):**
   When `task_gap12_v1` was in `PLANNING`, `is_leased_state` was False and `has_active_lease` was False. Lines 329–330 assigned `token = 0` and bypassed all lease checks. An unauthenticated external actor (`unauthenticated_attacker_v1`) called `transition(task_id, "FAILED")` without lease or credentials. The database transaction executed `UPDATE tasks SET state='FAILED'` and committed. Because `TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}`, line 280 permanently locked the task as immutable. `INV-GAP12-01` and `INV-GAP12-04` are demonstrably broken.

3. **Vector 2 Proof (Observation 1.2, Vector 2):**
   `task_gap12_v2` was claimed and started by `worker_beta` with `max_attempts = 3`. The worker called `transition(task_id, "FAILED", lease_id=l2.lease_id, actor="worker_beta")` without attaching any crash dump, stack trace, or failure classification. The transition succeeded immediately on attempt 1, releasing the lease and terminating the task. The retry budget and recovery pipeline (`UNKNOWN` -> `RECOVERING` -> `RECONCILING`) were completely bypassed. `INV-GAP12-02` and `INV-GAP12-03` are demonstrably broken.

4. **Vector 3 Proof (Observation 1.2, Vector 3):**
   `task_gap12_v3` was in `VERIFYING`. For `COMPLETED`, GAP-11 enforced verifier verdicts and evidence tokens via `commit_completed()`. For `FAILED`, the worker simply invoked `transition(task_id, "FAILED")`, bypassing all verifier checks. The task was permanently failed without verifier counter-evidence or indictment.

5. **Vector 4 Proof (Observation 1.2, Vector 4):**
   `task_gap12_v4` was executing under `legitimate_worker_delta`. An adversary (`rogue_saboteur_delta`) supplied the stolen lease ID to `transition(..., "FAILED")`. Line 324 (`_assert_lease`) verified only that the lease was active in SQLite; it did NOT verify that `actor == lease['worker_id']`. The transition succeeded, permanently sabotaging the task.

6. **Physical Persistence Verification (Observation 1.2, SQLite Inspection):**
   Direct SQLite inspection via `sqlite3.connect()` confirmed that all 4 tasks were physically updated to `state = 'FAILED'`, `version` incremented, `active_lease_id` cleared to NULL, and corresponding `STATE_TRANSITION` events appended to `events` table. The vulnerability operates at the raw hardware/database persistence layer (satisfying FA-08, FA-09, and FA-12 Step 4).

7. **Anti-Placebo Rigor:**
   The probe conclusively proves the RED state on the existing codebase. Because the probe checks for both the exploit success (`VULNERABILITY_PROVEN_RED`) and the expected blocked exception (`PROTECTED_GREEN`), it guarantees that once the evolution path is implemented (raising `InvalidTransition`), the probe will transition from RED to GREEN without assertion weakening.

---

## 3. Caveats

1. **No Production Code Modified:** As mandated by the prompt and FA-11 Rule 1, `scp/task_kernel_parts/taskkernel.py` was not modified during this probe phase. The fix must be executed in Milestone M5 under explicit Orchestrator authorization.
2. **GAP-13 Scope Boundary:** As established in SCOPE.md, GAP-13 (`WAITING_APPROVAL -> READY` bypass) belongs to admission control/capability authorization and is intentionally excluded from this probe to keep the Delta Audit strictly bounded.

---

## 4. Conclusion

- **Milestone M4 Status:** **COMPLETED SUCCESSFULLY**.
- GAP-12 is empirically **PROVEN** across all 4 attack vectors:
  1. `PLANNING -> FAILED`: Unauthenticated external cancellation without lease or evidence.
  2. `RUNNING -> FAILED`: Unverified worker failure claim on attempt 1, discarding retry budget.
  3. `VERIFYING -> FAILED`: Verification sabotage bypassing independent verifier checks.
  4. `Stolen Lease Sabotage`: Rogue actor terminating task via stolen lease, bypassing OCC recovery.
- Physical database mutation is verified on raw SQLite tables (`tasks` and `events`).
- Anti-Placebo baseline established: Code is currently in **RED state**. Falsification condition is clearly specified.

---

## 5. Verification Method

To independently reproduce and verify this evidence:

1. **Run the Standalone Probe:**
   ```powershell
   python tools/probes/probe_gap12_delta_audit.py
   ```
   **Expected Terminal Output:** All 4 vectors report `VULNERABILITY_PROVEN_RED` with exit code `0`, and SQLite raw inspection outputs 4 rows with `state=FAILED`.

2. **Run Kernel Regression Suite:**
   ```powershell
   pytest tests/T04_kernel -q
   ```
   **Expected Terminal Output:** `78 passed in ~7s`, exit code `0`.

3. **Invalidation Condition:**
   This finding would be invalidated if calling `transition(task_id, "FAILED")` from `PLANNING` or `RUNNING` raised `InvalidTransition` or required failure evidence on the current commit. Terminal execution unequivocally demonstrates that it succeeds.
