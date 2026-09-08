# ADVERSARIAL CHALLENGE & VERIFICATION REPORT — CHALLENGER 2

**Challenger Role**: critic, specialist (Empirical Challenger 2)  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\challenger_2`  
**Parent Orchestrator ID**: `f1e50da6-b37c-427b-a8a3-fdc334188734`  
**Date/Timestamp**: 2026-09-08T01:57:00Z  
**Milestone / Task**: M1 GAP-12 Remediation — Adversarial Empirical Verification of Downstream Callers, Retry Preservation, and Lifecycle State Machines  
**Final Verdict**: **APPROVE**  

---

## 1. OBSERVATION

Directly observed files, line numbers, terminal commands, raw SQLite records, and verbatim outputs from independent executions:

### 1.1 Baseline Verification Runs
1. **Target Kernel Tests (`pytest tests/T04_kernel -q`)**:
   - Command: `pytest tests/T04_kernel -q`
   - Exit code: `0`
   - Terminal output:
     ```
     ........................................................................ [ 82%]
     ...............                                                          [100%]
     87 passed in 7.28s
     ```

2. **Capability PEP Tests (`pytest tests/T03_capability/test_hands_authority_pep.py -q`)**:
   - Command: `pytest tests/T03_capability/test_hands_authority_pep.py -q`
   - Exit code: `0`
   - Terminal output:
     ```
     .........                                                                [100%]
     9 passed in 0.70s
     ```

3. **Meta-Audit Integrity Check (`python tools/t00_meta_audit.py`)**:
   - Command: `python tools/t00_meta_audit.py`
   - Exit code: `0`
   - Terminal output excerpt:
     ```
     [T00 Meta-Audit] Starting Test-Integrity Regression Authority...
     [T00 Meta-Audit] Trusted Base: origin/main
     [T00 Meta-Audit] Collecting baseline pytest nodeids (origin/main)...
     [T00 Meta-Audit] Collecting candidate pytest nodeids...
     [T00 Meta-Audit] All integrity checks passed (0 new regressions).
     ```

4. **Delta Audit Exploit Probe (`python tools/probes/probe_gap12_delta_audit.py`)**:
   - Command: `python tools/probes/probe_gap12_delta_audit.py`
   - Exit code: `0`
   - Output excerpt:
     ```
     Anti-Placebo Contract Status:
       >> GREEN STATE CONFIRMED: All 4 exploit vectors protected by InvalidTransition.
       >> Tasks and events verified in database: 0 unauthorized transitions to FAILED.
       >> Anti-Placebo Falsification Condition Satisfied.
       >> Verdict: ALL_VECTORS_PROTECTED_GREEN
     ```

### 1.2 Independent Adversarial Stress Test Execution
Executed `python tools/probes/probe_challenger2_gap12_adversarial.py` developed specifically to independently stress-test:
- Retry preservation across attempts 1, 2, 3 (until exhaustion)
- Uncertain error fail-closed routing to `UNKNOWN`
- Downstream `AskKernelAdapter.fail()` physical SQLite updates
- Downstream `TaskKernelHandsBridge.execute()` physical SQLite updates
- Adversarial boundaries: 17-state scan, stolen lease spoofing, empty indictment, active queue underflow, and OCC race

Command: `python tools/probes/probe_challenger2_gap12_adversarial.py`  
Exit code: `0`  
Verbatim Terminal Output:
```
================================================================================
CHALLENGER 2: EMPIRICAL ADVERSARIAL STRESS HARNESS (GAP-12 REMEDIATION)
Zero-Trust & Fail-Closed Protocols: FA-08, FA-09, FA-12, FA-13
================================================================================

--- [TEST SUITE 1] Retryable Lifecycle & Budget Exhaustion ---
  [*] Attempt 1 passed: correctly routed to RETRY_SCHEDULED, attempts=1, lease released, active=0
  [*] Attempt 2 passed: correctly routed to RETRY_SCHEDULED, attempts=2
  [*] Attempt 3 passed: budget exhausted, moved to terminal FAILED
  [*] Terminal immutability confirmed: no further transitions allowed from FAILED

--- [TEST SUITE 2] Uncertain Errors Routing to UNKNOWN ---
  [*] UNKNOWN passed: routed strictly to UNKNOWN (no blind retry)
  [*] UNCERTAIN passed: routed strictly to UNKNOWN (no blind retry)
  [*] LOST_RESPONSE passed: routed strictly to UNKNOWN (no blind retry)
  [*] CRASH_AFTER_SUBMIT passed: routed strictly to UNKNOWN (no blind retry)

--- [TEST SUITE 3] Downstream AskKernelAdapter.fail() Integration ---
  [*] Case 1 (FATAL) passed: physical DB confirmed FAILED, lease released, queue decremented
  [*] Case 2 (RETRYABLE) passed: physical DB confirmed RETRY_SCHEDULED for ask adapter

--- [TEST SUITE 4] Downstream TaskKernelHandsBridge.execute() Integration ---
  [*] Case 1 (Policy Denied) passed: task FAILED, lease released, indictment recorded in physical DB
  [*] Case 2 (Pre-dispatch crash) passed: task cleanly FAILED, lease released

--- [TEST SUITE 5] Adversarial Boundary & Concurrency Attacks ---
  [>] Probing raw transition to FAILED across all known states...
  [*] All 17 states safely blocked direct transition to FAILED with InvalidTransition
  [*] Lease actor spoofing and empty indictment rejected fail-closed
  [*] Queue underflow defense verified: active count cannot go below 0
  [>] Testing OCC concurrency race on commit_failed()...
  [*] OCC Concurrency race passed: 1 winner, 1 conflict (OptimisticLockError), 1 journal entry

================================================================================
VERDICT: ALL 5 ADVERSARIAL TEST SUITES PASSED (100% EMPIRICAL CONFIRMATION)
  - Retry preservation and exhaustion lifecycle: VERIFIED
  - Uncertain failure fail-closed routing: VERIFIED
  - Downstream AskKernelAdapter physical SQLite integration: VERIFIED
  - Downstream TaskKernelHandsBridge physical SQLite integration: VERIFIED
  - OCC concurrency race, actor spoofing & underflow protection: VERIFIED
================================================================================
```

### 1.3 Physical SQLite Evidence Observations
Inspecting the SQLite database rows during probe execution:
1. **`tasks` table after retryable failure (Attempt 1)**:
   - `SELECT state, attempts, active_lease_id, active_fencing_token FROM tasks WHERE task_id='task-adv-retry-1'`
   - Result: `state='RETRY_SCHEDULED'`, `attempts=1`, `active_lease_id=NULL`, `active_fencing_token=0`.
2. **`tasks` table after attempt budget exhaustion (Attempt 3)**:
   - `SELECT state, attempts, active_lease_id FROM tasks WHERE task_id='task-adv-retry-1'`
   - Result: `state='FAILED'`, `attempts=3`, `active_lease_id=NULL`.
3. **`leases` table**:
   - `SELECT released FROM leases WHERE lease_id=?`
   - Result: `released=1` across all failure commitments.
4. **`queue_accounts` table**:
   - `SELECT active FROM queue_accounts WHERE owner=?`
   - Result: Decremented from `1` to `0` upon each failure commitment. Underflow attempt confirmed `active=0` (never negative).
5. **`events` table**:
   - `SELECT type, to_state, payload_json FROM events WHERE task_id='task-adv-retry-1'`
   - Contains immutable event records:
     - `TASK_RETRY_SCHEDULED` (attempt 1 & 2)
     - `TASK_FAILED` (attempt 3)
     - Full JSON payload contains `attempts`, `max_attempts`, `failure_classification`, and `indictment_ref`.

---

## 2. LOGIC CHAIN

Step-by-step reasoning from observations to audit verdict:

1. **State Machine Boundary Invariant (`INV-GAP12-01`)**:
   - *Observation*: Probing direct `transition(task_id, "FAILED")` across all 17 states in `STATES` (`CREATED`, `PLANNING`, `READY`, `QUEUED`, `LEASED`, `RUNNING`, `WAITING_TOOL`, `VERIFYING`, `CHECKPOINTED`, `UNKNOWN`, `RECOVERING`, `RECONCILING`, `HUMAN_REVIEW`, `RETRY_SCHEDULED`, `COMPLETED`, `FAILED`, `CANCELLED`) consistently raised `InvalidTransition` (Section 1.2, Test Suite 5).
   - *Deduction*: No caller can force a task into `FAILED` via raw `transition()`. Direct bypass of the failure commitment protocol is mechanically impossible at the state machine level.

2. **Retry Budget Preservation & Exhaustion Mechanics (`INV-GAP12-03`)**:
   - *Observation*: When `commit_failed()` is invoked with `failure_classification="RETRYABLE"` and `attempts < max_attempts`, the returned task and physical SQLite row transition to `RETRY_SCHEDULED`, incrementing `attempts` from 0 to 1, and then from 1 to 2. Only when `new_attempts >= max_attempts` (attempt 3 of 3) does the state transition to `FAILED` (Section 1.2, Test Suite 1; Section 1.3).
   - *Deduction*: Tasks experiencing transient disruptions are protected from premature abortion. The retry budget is preserved and enforced strictly according to configured `max_attempts`.

3. **Uncertain Failures Fail-Closed Routing**:
   - *Observation*: Classifications `"UNKNOWN"`, `"UNCERTAIN"`, `"LOST_RESPONSE"`, and `"CRASH_AFTER_SUBMIT"` route immediately to `UNKNOWN` with `TASK_UNKNOWN_STATE` events, even when `max_attempts = 10` has 9 remaining attempts (Section 1.2, Test Suite 2).
   - *Deduction*: Adheres strictly to the core DNA invariant: uncertain external side effects must NEVER be blindly retried. They transition to `UNKNOWN` where explicit reconciliation is mandatory.

4. **Downstream Integration Integrity**:
   - *Observation*:
     - In `AskKernelAdapter.fail()`, physical SQLite records confirm that tasks transition to `FAILED` (or `RETRY_SCHEDULED` for retryable classifications), leases are marked `released=1`, `queue_accounts.active` decrements, and an indictment URI (`ask://...`) is journaled in `events` (Section 1.2, Test Suite 3).
     - In `TaskKernelHandsBridge.execute()`, policy denials and pre-dispatch exceptions trigger `commit_failed()`, setting state to `FAILED`, releasing leases, and journaling indictment URIs (`hands://...`) (Section 1.2, Test Suite 4).
   - *Deduction*: Downstream callers do not bypass the kernel failure gate. They comply fully with the `commit_failed()` contract and clean up concurrency quotas.

5. **Security Boundaries & OCC Concurrency**:
   - *Observation*:
     - Stolen lease attacks with spoofed actor names (`"imposter"`, `"attacker"`, `"root"`, etc.) are rejected with `InvalidTransition` (actor mismatch).
     - Missing or whitespace indictment references are rejected fail-closed with `KernelError`.
     - Concurrent race between two threads attempting `commit_failed()` resulted in exactly 1 winner and 1 `OptimisticLockError`, with exactly 1 failure event recorded in SQLite.
     - Queue underflow protection ensures `queue_accounts.active` never drops below 0.
   - *Deduction*: The failure endpoint is thread-safe, resistant to actor impersonation, and preserves database integrity under race conditions.

---

## 3. CAVEATS

1. **`spec/scp_target_test_coverage.yaml` Git Blob Hash Drift**:
   In `tests/T00_integrity/test_scp_target_test_coverage.py`, failures occur because historical commit blob hashes in the spec file drifted in commit `0c44c13`. This is completely independent of GAP-12 remediation and was not modified.
2. **Actor Whitespace Normalization**:
   `_assert_lease()` uses `str(actor).strip()`. Consequently, passing `" legit-worker "` matches `"legit-worker"`. This is intentional whitespace trimming and does not allow unauthorized actors to hijack leases.
3. No functional caveats in GAP-12 remediation or downstream integration.

---

## 4. CONCLUSION

All requirements (R1 through R4) and invariants (`INV-GAP12-01` through `INV-GAP12-04`) for GAP-12 remediation are empirically verified:
- `transition()` strictly forbids direct transitions to `FAILED` across all 17 lifecycle states.
- `commit_failed()` correctly preserves retry budgets for transient errors (`RETRY_SCHEDULED`) and fails closed upon attempt exhaustion (`FAILED`).
- Uncertain failures (`UNKNOWN`) are routed safely without blind retries.
- Downstream callers (`AskKernelAdapter` and `TaskKernelHandsBridge`) release active leases and decrement queue concurrency in physical SQLite.
- Concurrency, OCC, and stolen lease defenses are verified under live physical execution.

**Final Verdict**: **APPROVE**

---

## 5. INDEPENDENT VERIFICATION METHOD

To independently reproduce this verification:

1. **Execute Challenger 2 Adversarial Probe Harness**:
   ```pwsh
   python tools/probes/probe_challenger2_gap12_adversarial.py
   ```
   *Expected Output*: Exit code `0`, `ALL 5 ADVERSARIAL TEST SUITES PASSED (100% EMPIRICAL CONFIRMATION)`.

2. **Execute Delta Audit Exploit Probe**:
   ```pwsh
   python tools/probes/probe_gap12_delta_audit.py
   ```
   *Expected Output*: Exit code `0`, `ALL_VECTORS_PROTECTED_GREEN`.

3. **Execute Test Suites & Meta-Audit**:
   ```pwsh
   pytest tests/T04_kernel -q
   pytest tests/T03_capability/test_hands_authority_pep.py -q
   python tools/t00_meta_audit.py
   ```
   *Expected Output*: Exit code `0`, 87 passed, 9 passed, 0 new regressions.
