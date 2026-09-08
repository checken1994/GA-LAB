# Milestone Review & Adversarial Challenge Report: GAP-12 Delta Audit

- **Agent:** `reviewer_delta_1` (`teamwork_preview_reviewer`)
- **Roles:** `reviewer`, `critic`
- **Working Directory:** `c:\Users\check\Downloads\scp\.agents\reviewer_delta_1`
- **Recipient / Parent Conversation ID:** `55c745a6-7ce1-4c1e-9385-e614d0c57946`
- **Date:** 2026-09-08T01:35:00+07:00
- **Milestone:** GAP-12 Delta Audit Review & Adversarial Challenge
- **Target Vulnerability:** GAP-12 — Unverified Terminal `FAILED` State Transition & Rogue Worker Sabotage
- **Target Subsystem:** `TaskKernel` (`scp/task_kernel_parts/taskkernel.py`, `scp/task_kernel.py`, `scp/ask_kernel_adapter.py`, `scp/hands/task_kernel_bridge.py`)
- **Authority / Guidelines:** `.agents/skills/scp-delta-audit/SKILL.md`, `.agents/skills/scp-dna/SKILL.md`, `.agents/AGENTS.md` (FA-01 to FA-13)

---

## 1. 5-Component Handoff Report

### 1.1 Observation

1. **Independent Standalone Probe Execution:**
   - Command: `python tools/probes/probe_gap12_delta_audit.py`
   - Execution Time: ~1.2s, Exit Code: `0`
   - Verbatim terminal observation:
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
     [*] Task running: ID=task_gap12_v2, State=RUNNING, Lease=lease_7f990a99e5514e038922a22c, MaxAttempts=3
     [!] [RED] EXPLOIT SUCCEEDED: Worker transitioned task directly to terminal FAILED on attempt 1!
         Task State: FAILED, Version: 7, ActiveLease: None
         Invariant Violated: INV-GAP12-01, INV-GAP12-02 & INV-GAP12-03 (No failure evidence, retry budget discarded)

     --------------------------------------------------------------------------------
     [VECTOR 3] Testing Verification Sabotage (VERIFYING -> FAILED without Verifier Check)
     --------------------------------------------------------------------------------
     [*] Task in verification: ID=task_gap12_v3, State=VERIFYING, Lease=lease_33f4e58d9e6e011df59539fd
     [!] [RED] EXPLOIT SUCCEEDED: Task terminated in FAILED without independent verifier indictment!
         Task State: FAILED, Version: 8
         Invariant Violated: INV-GAP12-01 & INV-GAP12-02 (Missing verifier counter-evidence)

     --------------------------------------------------------------------------------
     [VECTOR 4] Testing Stolen Lease Sabotage & Recovery Bypass
     --------------------------------------------------------------------------------
     [*] Task running: ID=task_gap12_v4, LegitimateWorker=legitimate_worker_delta, Lease=lease_f383a25345bd1dc8d06ab7bf
     [!] [RED] EXPLOIT SUCCEEDED: Rogue actor with stolen lease killed task into terminal FAILED!
         Task State: FAILED, Version: 7, RemainingAttempts: Discarded
         Invariant Violated: INV-GAP12-01, INV-GAP12-02 & INV-GAP12-03 (Recovery engine completely bypassed)

     ================================================================================
     FA-12 STEP 4: PHYSICAL SQLITE PERSISTENCE INSPECTION
     Inspecting physical database file: C:\Users\check\AppData\Local\Temp\tmprzy8btik_gap12_probe.sqlite3
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

2. **Kernel Test Suite Execution:**
   - Command: `pytest tests/T04_kernel -q`
   - Result: `78 passed in 7.49s`, exit code `0`.
   - Baseline regression status: Clean, zero regressions.

3. **Codebase Inspection of `scp/task_kernel_parts/taskkernel.py`:**
   - Lines 253–256: Explicitly forbids direct transition to `COMPLETED`:
     ```python
     if to_state == "COMPLETED":
         raise InvalidTransition(
             "direct transition to COMPLETED is forbidden; use commit_completed() with valid evidence"
         )
     ```
   - Symmetrical check for `to_state == "FAILED"` is entirely missing.
   - Lines 329–330: For unleased states (`PLANNING`), `token = 0` and lease checks are completely skipped.
   - Lines 324–325: For leased states (`RUNNING`), `_assert_lease` verifies lease existence and expiry, but does NOT verify caller identity matches `lease["worker_id"]`.
   - Lines 348–350: Unconditional SQL execution:
     `UPDATE tasks SET state='FAILED',version=version+1,active_lease_id=NULL,active_fencing_token=0,updated_at=? WHERE task_id=? AND version=?`

4. **Peripheral Call Site Analysis (FA-11 Peripheral Audit):**
   - Direct search for `transition(..., "FAILED")` across `scp/` revealed:
     - `scp/ask_kernel_adapter.py:430`: `self.kernel.transition(task["task_id"], "FAILED", actor="ask-kernel-adapter", reason=reason)`
     - `scp/hands/task_kernel_bridge.py:445`: `self.kernel.transition(task_id, "FAILED", actor="hands-kernel-bridge", reason="hands_policy_denied_before_dispatch", payload={"action": action})`
     - `scp/hands/task_kernel_bridge.py:582`: `self.kernel.transition(task_id, "FAILED", actor="hands-kernel-bridge", reason="hands_bridge_pre_dispatch_failure", payload={"errorType": type(exc).__name__})`
   - Upstream worker handoff noted `ask_kernel_adapter.py`, but completely overlooked `scp/hands/task_kernel_bridge.py`.

### 1.2 Logic Chain

1. **Vulnerability Existence:**
   `taskkernel.py:transition()` permits `to_state="FAILED"` without verifying failure evidence, failure classification, retry budget exhaustion, or caller identity. Once transitioned, the task enters `TERMINAL` state (`taskkernel.py:280`) and is immutable.
2. **Empirical Reproduction:**
   The standalone probe executed in live terminal without mocking or stubs. The database layer (`tasks` and `events` tables in SQLite) recorded all 4 failure mutations physically, satisfying FA-08, FA-09, and FA-12 Step 4.
3. **Anti-Placebo Contract Rigor:**
   The probe tests both the vulnerability (RED condition) and the planned protection (`PROTECTED_GREEN` via `InvalidTransition`). It guarantees that once `transition(..., "FAILED")` is blocked, the probe will transition from RED to GREEN without assertion weakening (FA-01).
4. **Integrity Verification:**
   The probe uses live temp files, dynamically generated lease tokens, and real SQLite database connections. There are no hardcoded responses, no simulated passes, and no dummy implementations.

### 1.3 Caveats

1. **Exclusion of GAP-13:** This review strictly covers GAP-12 (Terminal `FAILED` transition). GAP-13 (`WAITING_APPROVAL -> READY` bypass) is separated per orchestrator boundary.
2. **Read-Only Scope:** In compliance with the reviewer mandate, no production files in `scp/` were modified during this review.
3. **M5 Scope Extension Required:** As identified during adversarial analysis, the remediation plan must encompass `scp/hands/task_kernel_bridge.py` in addition to `scp/ask_kernel_adapter.py`.

### 1.4 Conclusion

- **Verdict:** **`APPROVE`** for Milestone M4 (Probe Execution & Anti-Placebo Evidence).
- GAP-12 is conclusively proven across all 4 attack vectors at the physical database layer.
- Zero integrity violations were detected.
- Zero regressions were introduced to existing tests (78/78 pass).
- The Anti-Placebo baseline is established and verified.
- Milestone M5 remediation must be executed under the expanded scope documented below.

### 1.5 Verification Method

1. **Reproduce Probe Evidence:**
   ```powershell
   python tools/probes/probe_gap12_delta_audit.py
   ```
   Must exit with code 0 and report 4 `VULNERABILITY_PROVEN_RED` vectors.
2. **Reproduce Kernel Test Suite:**
   ```powershell
   pytest tests/T04_kernel -q
   ```
   Must report `78 passed` with exit code 0.
3. **Invalidation Criteria:**
   If `transition(task_id, "FAILED")` from `PLANNING` or `RUNNING` raised `InvalidTransition` on the current codebase, this finding would be invalidated. Terminal execution proves it does not.

---

## 2. Quality Review Report

### 2.1 Review Summary
- **Verdict:** **APPROVE**
- **Reviewed Products:**
  - `c:\Users\check\Downloads\scp\.agents\worker_m4_probe\handoff.md`
  - `tools/probes/probe_gap12_delta_audit.py`
  - Target Manifest Invariants (`INV-GAP12-01` to `04`)
  - Kernel implementation in `taskkernel.py` and `task_kernel.py`
  - Proposed Evolution Path

### 2.2 Verified Claims

| Claim | Verification Method | Result |
|---|---|---|
| Vector 1 (`PLANNING -> FAILED` unauthenticated) succeeds | Executed live probe in PowerShell | **VERIFIED (RED)** |
| Vector 2 (`RUNNING -> FAILED` on attempt 1 without evidence) succeeds | Executed live probe in PowerShell | **VERIFIED (RED)** |
| Vector 3 (`VERIFYING -> FAILED` without verifier indictment) succeeds | Executed live probe in PowerShell | **VERIFIED (RED)** |
| Vector 4 (`RUNNING -> FAILED` via stolen lease) succeeds | Executed live probe in PowerShell | **VERIFIED (RED)** |
| Physical SQLite persistence of `FAILED` state & events journal | Independent direct SQLite query in probe | **VERIFIED** (4 tasks, 4 events) |
| Zero regression on existing kernel tests | Executed `pytest tests/T04_kernel -q` | **VERIFIED** (78 passed in 7.49s) |
| Production code clean | Checked git status across `scp/` | **VERIFIED** (0 files modified) |

### 2.3 Findings

#### [Major] Finding 1: Unaccounted Call Sites in `scp/hands/task_kernel_bridge.py`
- **Where:** `scp/hands/task_kernel_bridge.py`, lines 445–457 and 582–594.
- **What:** The bridge calls `self.kernel.transition(task_id, "FAILED", ...)` when pre-dispatch policy denies an action or when an exception occurs before dispatch.
- **Why:** The upstream worker handoff only planned to update `AskKernelAdapter.fail()`. If raw `transition(..., "FAILED")` is blocked in `taskkernel.py`, calls from `task_kernel_bridge.py` will raise `InvalidTransition` (and line 596 will silently swallow it with `except Exception: pass`), leaving tasks in unhandled non-terminal states.
- **Suggestion:** Milestone M5 evolution path must explicitly adapt `scp/hands/task_kernel_bridge.py` to use `commit_failed()` or provide system authority.

#### [Minor] Finding 2: `AskKernelAdapter.fail()` Swallows Exceptions Silently
- **Where:** `scp/ask_kernel_adapter.py`, lines 440–447.
- **What:** `fail()` catches all exceptions and routes them to `observe_nonfatal()`, returning `None`.
- **Why:** If `commit_failed()` is introduced and fails validation (e.g. invalid lease), the error will be silently masked and `tests/T04_kernel/test_adversarial_kernel_flaws.py:891` (`assert task['state'] == 'FAILED'`) will fail with an obscure mismatch.
- **Suggestion:** Ensure `AskKernelAdapter.fail()` receives valid lease authority and logs structured telemetry if commit fails.

### 2.4 Coverage Gaps

- `scp/hands/task_kernel_bridge.py` failure dispatch — Risk Level: **HIGH** — Recommendation: **MANDATORY INVESTIGATION & REMEDIATION in M5**.

---

## 3. Adversarial Challenge Report

### 3.1 Challenge Summary
- **Overall Risk Assessment:** **CRITICAL** (if unpatched), **LOW** (if patched with expanded M5 scope).
- **Core Insight:** Symmetrical vulnerability to GAP-11. Where GAP-11 allowed fake pass bypasses, GAP-12 allows arbitrary denial-of-service and sabotage by workers, callers, or stolen leaseholders, completely nullifying retry policies, OCC reconciliation, and verifier authority.

### 3.2 Challenges

#### Challenge 1: Worker Sabotage & Retry Budget Theft (Assumption Stress-Testing)
- **Assumption Challenged:** "Workers will only report failure when they actually crash, and TaskKernel can trust the worker's direct transition to FAILED."
- **Attack Scenario:** A compromised, buggy, or rogue worker claims a task, does zero work, and immediately invokes `transition(task_id, "FAILED")` on attempt 1 of 5.
- **Blast Radius:** The task is terminated immediately. OCC recovery (`UNKNOWN -> RECOVERING -> RECONCILING`) is bypassed. The remaining 4 retry attempts are discarded. The workload permanently fails.
- **Mitigation:** TaskKernel must reject raw `transition(..., "FAILED")`. A task in `RUNNING` can only be failed via `commit_failed()` with verified failure evidence, and only after retry budget exhaustion or an explicit fatal non-retryable error classification.

#### Challenge 2: Stolen Lease Identity Impersonation (Edge Case Mining)
- **Assumption Challenged:** "Checking that a caller provides an active lease ID is sufficient proof of caller authority."
- **Attack Scenario:** An adversary intercepts a lease ID from network traces, shared logs, or a compromised sidecar. The adversary calls `transition(task_id, "FAILED", lease_id=stolen_lease, actor="adversary")`.
- **Blast Radius:** Line 324 of `taskkernel.py` only verifies that the lease is unexpired and unreleased. It does NOT check `actor == lease['worker_id']`. The adversary terminates the legitimate worker's task.
- **Mitigation:** `commit_failed()` and `transition()` must enforce `lease['worker_id'] == actor` or verify cryptographic possession of the lease token.

#### Challenge 3: Pre-Execution DOS Sabotage (`PLANNING -> FAILED`)
- **Assumption Challenged:** "Unleased transitions in PLANNING are safe because no worker has started yet."
- **Attack Scenario:** Any unauthenticated actor who knows or guesses a `task_id` calls `transition(task_id, "FAILED")` while the task is in `PLANNING`.
- **Blast Radius:** Lines 329–330 assign `token = 0` and skip all lease checks. The task is killed before it can ever be scheduled or queued.
- **Mitigation:** In pre-execution states, caller transitions to `FAILED` must be prohibited. If a planner rejects a plan, it must either transition to `CANCELLED` (with reason) or require explicit administrative authority.

---

## 4. FA-01 through FA-13 Compliance Matrix

| Rule | Description | Compliance Status | Evidence / Notes |
|---|---|---|---|
| **FA-01** | No assertion loosening | **COMPLIANT** | Zero assertions loosened in test suite or probe. |
| **FA-02** | No delete/skip/xfail | **COMPLIANT** | Zero tests deleted, skipped, or xfailed. |
| **FA-03** | No unverified claims | **COMPLIANT** | Full terminal output of probe and pytest captured live on current SHA. |
| **FA-04** | No simulated VERIFIED | **COMPLIANT** | Verified via real TaskKernel execution and SQLite persistence. |
| **FA-05** | No self-granted authority | **COMPLIANT** | No artificial token issuance. |
| **FA-06** | No mutation before baseline reconcile | **COMPLIANT** | Zero files in `scp/` modified. |
| **FA-07** | No maturity claim from presence | **COMPLIANT** | Explicitly classified as M4 probe evidence, not production maturity. |
| **FA-08** | No forged provenance | **COMPLIANT** | Probe output and SQLite data executed and read live via system shell. |
| **FA-09** | Exploit Mandate | **COMPLIANT** | Standalone probe `tools/probes/probe_gap12_delta_audit.py` executed and proved all 4 exploit vectors in terminal. |
| **FA-10** | Cross-workspace isolation | **COMPLIANT** | All operations strictly bounded to current workspace. |
| **FA-11** | Peripheral Audit & No Blind Eye | **COMPLIANT** | Audited peripheral call sites and uncovered `scp/hands/task_kernel_bridge.py`. |
| **FA-12** | Empirical Closure (5 Steps) | **COMPLIANT** | Step 1 (Causal graph), Step 2 (Scan hidden bugs), Step 3 (Live terminal execution), Step 4 (Direct SQLite physical inspection), Step 5 (End-to-End trace). |
| **FA-13** | Causal-Driven Coverage | **COMPLIANT** | All 4 failure vectors probed; unproven branches identified. |

---

## 5. Required Action for Milestone M5

The Orchestrator can now proceed to authorize Milestone M5 (Evolution Path Implementation & Final 10-Section Synthesis) with the following required implementation deliverables:

1. **`scp/task_kernel_parts/taskkernel.py`:**
   - Add guard blocking direct `to_state == "FAILED"` in `transition()`:
     ```python
     if to_state == "FAILED":
         raise InvalidTransition(
             "direct transition to FAILED is forbidden; use commit_failed() with valid failure evidence or recovery engine"
         )
     ```
   - Implement `commit_failed(task_id, lease_id, failure_evidence, actor, ...)` requiring valid lease, actor match, failure evidence, and retry boundary check.
2. **`scp/ask_kernel_adapter.py`:**
   - Adapt `fail()` to call `commit_failed()` with lease and error indictment.
3. **`scp/hands/task_kernel_bridge.py`:**
   - Adapt lines 445 and 582 to use `commit_failed()` or appropriate failure path.
4. **`tests/T04_kernel/test_adversarial_kernel_flaws.py`:**
   - Add adversarial tests verifying that `transition(..., "FAILED")` is blocked and `commit_failed()` succeeds only with valid evidence and lease.
5. **Anti-Placebo Verification:**
   - Run `python tools/probes/probe_gap12_delta_audit.py` -> Must turn **100% PROTECTED_GREEN**.
