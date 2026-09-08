# REVIEW & ADVERSARIAL AUDIT REPORT — REVIEWER 1

**Reviewer Role**: reviewer, critic (Teamwork Preview Reviewer)  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\reviewer_1`  
**Parent Orchestrator ID**: `f1e50da6-b37c-427b-a8a3-fdc334188734`  
**Date/Timestamp**: 2026-09-08T01:49:30Z  
**Milestone / Task**: M1 GAP-12 Remediation — State Machine Guard, Lease Fencing, Failure Commitment, and Downstream Migration Review  
**Final Verdict**: **APPROVE**  

---

## 1. EXECUTIVE SUMMARY & QUALITY REVIEW

### Review Summary
**Verdict**: **APPROVE**  
Worker 1's implementation of GAP-12 remediation across `taskkernel.py`, `ask_kernel_adapter.py`, `task_kernel_bridge.py`, and `test_adversarial_kernel_flaws.py` strictly adheres to all architectural requirements and system invariants (`INV-GAP12-01` through `INV-GAP12-04`). All 4 exploit vectors are verified blocked in live physical SQLite execution. No integrity violations or regressions were detected.

### Findings
- **Critical Findings**: None.
- **Major Findings**: None.
- **Minor / Observational Finding 1**: In `tests/T00_integrity/test_scp_target_test_coverage.py`, 10 tests fail due to pre-existing stale `manifest_blob_sha` in `spec/scp_target_test_coverage.yaml` (from commit `0c44c13`), which is outside Worker 1's write ownership and unrelated to GAP-12.

### Integrity Assessment
- **Hardcoded test results / expected outputs**: None found.
- **Dummy / facade implementations**: None. All logic directly manipulates and queries physical SQLite tables (`tasks`, `leases`, `events`, `queue_accounts`).
- **Task shortcuts / bypasses**: None. All downstream callers were migrated cleanly.
- **Fabricated verification outputs**: None. All tests and probes were independently executed on the live terminal with raw outputs inspected.
- **Self-certifying work**: None. 9 new adversarial tests were added covering all causal branches.

---

## 2. OBSERVATION

Directly observed file contents, line numbers, terminal commands, and verbatim execution outputs:

### 2.1 Code Implementation Observations
1. **`transition()` Guard (`scp/task_kernel_parts/taskkernel.py:259-262`)**:
   ```python
   if to_state in ("COMPLETED", "FAILED"):
       raise InvalidTransition(
           f"direct transition to {to_state} is forbidden; use commit_{to_state.lower()}() with valid evidence"
       )
   ```
   Direct transitions to `FAILED` are unconditionally intercepted before any transaction start or database modification.

2. **Lease Actor Binding (`scp/task_kernel_parts/taskkernel.py:470, 485-487`)**:
   ```python
   def _assert_lease(self, lease_id: str, task_id: str, actor: str | None = None) -> Any:
       ...
       if actor is not None and str(actor).strip():
           if lease['worker_id'] != str(actor).strip():
               raise InvalidTransition(f"actor '{actor}' does not match lease worker '{lease['worker_id']}'")
   ```
   Positional parameter compatibility `(lease_id, task_id)` is preserved while validating `actor == lease['worker_id']` when actor is supplied.

3. **Schema Backward Compatibility (`scp/task_kernel_parts/taskkernel.py:93, 100, 178-181`)**:
   `tasks` table creation includes `attempts INTEGER NOT NULL DEFAULT 0` and `error TEXT`. Dynamic `ALTER TABLE tasks ADD COLUMN attempts...` and `ALTER TABLE tasks ADD COLUMN error TEXT` are performed idempotently in `_schema()`.

4. **`commit_failed()` Endpoint (`scp/task_kernel_parts/taskkernel.py:961-1087`)**:
   - Validates non-empty `task_id`, `lease_id`, `actor`, `failure_classification`, and `indictment_ref`.
   - Executes `_assert_lease(lease_id, task_id, actor=actor)`.
   - Validates pre-condition states (`RUNNING`, `WAITING_TOOL`, `VERIFYING`, `LEASED`, `CHECKPOINTED`, `UNKNOWN`) and blocks terminal states.
   - Enforces retry budget preservation:
     - If classification is uncertain (`UNKNOWN`, `UNCERTAIN`, etc.) -> `UNKNOWN`.
     - If retryable (`RETRYABLE`, `TRANSIENT`, `TIMEOUT`, etc.) and `attempts < max_attempts` -> `RETRY_SCHEDULED`.
     - Otherwise (`attempts >= max_attempts` or `FATAL`) -> `FAILED`.
   - Atomically updates `tasks` with OCC version check, records immutable event in `events`, releases lease in `leases`, and decrements queue active count in `queue_accounts`.

5. **Downstream Callers Migration**:
   - `scp/ask_kernel_adapter.py:437-448`: If lease exists, calls `commit_failed()` with matching `worker_id` and `indictment_ref`; if no active lease, calls `set_task_kill()`.
   - `scp/hands/task_kernel_bridge.py:445-452, 577-584`: Calls `commit_failed()` with `actor=self.worker_id` matching `self.kernel.claim()` lease ownership.

6. **Adversarial Test Suite (`tests/T04_kernel/test_adversarial_kernel_flaws.py:917-1260`)**:
   Contains 9 distinct causal branch tests (`test_branch_1` through `test_branch_9`) covering the complete causal graph.

### 2.2 Terminal Execution Observations
1. **Delta Audit Probe**:
   - Command: `python tools/probes/probe_gap12_delta_audit.py`
   - Exit code: `0`
   - Output excerpt:
     ```
     PROBE RESULTS SUMMARY & ANTI-PLACEBO CONTRACT EVALUATION
       VECTOR_1: PLANNING -> FAILED (Unauthenticated, No Lease, No Evidence)
         Verdict: PROTECTED_GREEN_InvalidTransition
       VECTOR_2: RUNNING -> FAILED (No Crash Evidence / Zero Indictment)
         Verdict: PROTECTED_GREEN_InvalidTransition
       VECTOR_3: VERIFYING -> FAILED (Verifier Check Bypassed)
         Verdict: PROTECTED_GREEN_InvalidTransition
       VECTOR_4: Stolen Lease Sabotage (Recovery Machine Bypassed)
         Verdict: PROTECTED_GREEN_InvalidTransition

     Anti-Placebo Contract Status:
       >> GREEN STATE CONFIRMED: All 4 exploit vectors protected by InvalidTransition.
       >> Tasks and events verified in database: 0 unauthorized transitions to FAILED.
       >> Anti-Placebo Falsification Condition Satisfied.
       >> Verdict: ALL_VECTORS_PROTECTED_GREEN
     ```

2. **Kernel Test Suite**:
   - Command: `pytest tests/T04_kernel/test_adversarial_kernel_flaws.py -q`
   - Exit code: `0`
   - Output: `34 passed in 2.56s`
   - Command: `pytest tests/T04_kernel -q`
   - Exit code: `0`
   - Output: `87 passed in 7.34s`

3. **Capability PEP Integration**:
   - Command: `pytest tests/T03_capability/test_hands_authority_pep.py -q`
   - Exit code: `0`
   - Output: `9 passed in 0.86s`

4. **Meta-Audit & Guardrails**:
   - Command: `python tools/t00_meta_audit.py`
   - Exit code: `0`
   - Output: `[T00 Meta-Audit] All integrity checks passed (0 new regressions).`

---

## 3. LOGIC CHAIN

1. **Vulnerability Mechanics**:
   Previously, any caller could execute `kernel.transition(task_id, "FAILED")` from any state, bypassing lease ownership, indictment artifacts, and retry budgets (`INV-GAP12-01` & `INV-GAP12-03`).
2. **Transition Fence**:
   By adding `"FAILED"` to the existing `"COMPLETED"` guard at `taskkernel.py:259`, calling `transition(..., "FAILED")` immediately raises `InvalidTransition`. This directly neutralizes Vectors 1, 2, and 3 observed in the probe.
3. **Lease Actor Authentication**:
   By extending `_assert_lease(lease_id, task_id, actor=None)` to enforce `actor == lease['worker_id']`, any third party attempting to use a valid `lease_id` with an unauthenticated actor name is rejected with `InvalidTransition`. This neutralizes Vector 4.
4. **Failure Gate Architecture**:
   The introduction of `commit_failed()` mandates the presence of an `indictment_ref` and validates worker ownership, ensuring every failure is accountable and auditable (`INV-GAP12-02`).
5. **Retry Budget Preservation**:
   `commit_failed()` dynamically differentiates retryable/transient failures from fatal/exhausted failures. If `attempts < max_attempts` and failure is retryable, the task transitions to `RETRY_SCHEDULED`, preventing premature task abortion.
6. **Atomicity & Resource Cleanup**:
   OCC version checking on `tasks`, immutable logging in `events`, updating `leases.released = 1`, and decrementing `queue_accounts.active` occur atomically within a single SQLite transaction block, preventing concurrency leaks.

---

## 4. ADVERSARIAL CHALLENGE & CRITIQUE REPORT

**Overall Risk Assessment**: **LOW**

### Challenges Evaluated
1. **Challenge 1 (Pre-Execution Sabotage Attempt)**:
   - *Attack Scenario*: Attacker invokes `commit_failed()` on a task in `CREATED` or `PLANNING` state.
   - *Observed Defense*: Tasks in `CREATED` or `PLANNING` do not possess active leases. `_task()` verifies existence, `_assert_lease()` fails with `StaleLease`, and state pre-condition check (`old_state not in {"RUNNING", ...}`) fails with `InvalidTransition`.
   - *Result*: **BLOCKED (PASS)**.

2. **Challenge 2 (Indictment Bypass Attempt)**:
   - *Attack Scenario*: Caller passes empty string or whitespace as `indictment_ref` to bypass evidence requirement.
   - *Observed Defense*: `if not indictment_ref or not str(indictment_ref).strip(): raise KernelError(...)` fails closed immediately before transaction.
   - *Result*: **BLOCKED (PASS)**.

3. **Challenge 3 (Stolen Lease Worker Sabotage)**:
   - *Attack Scenario*: Worker B eavesdrops `lease_id` of Worker A and invokes `commit_failed(..., actor="Worker B")`.
   - *Observed Defense*: `_assert_lease()` checks `lease['worker_id'] == str(actor).strip()`, detects mismatch, and raises `InvalidTransition`.
   - *Result*: **BLOCKED (PASS)**.

4. **Challenge 4 (Terminal Immutability Attack)**:
   - *Attack Scenario*: Caller attempts to mutate or fail an already terminal (`FAILED` / `COMPLETED`) task.
   - *Observed Defense*: `if old_state in TERMINAL: raise InvalidTransition("terminal task is immutable")`.
   - *Result*: **BLOCKED (PASS)**.

5. **Challenge 5 (Queue Account Concurrency Underflow)**:
   - *Attack Scenario*: Repeated lease release could theoretically cause `queue_accounts.active` to drop below zero.
   - *Observed Defense*: SQLite update statement uses `CASE WHEN active > 0 THEN active - 1 ELSE 0 END`.
   - *Result*: **PROTECTED (PASS)**.

---

## 5. INVARIANTS COMPLIANCE MATRIX

| Invariant | Specification | Evidence / Verification | Status |
|---|---|---|---|
| `INV-GAP12-01` | Prohibition of raw unverified transition to terminal `FAILED` | `taskkernel.py:259` raises `InvalidTransition`; Probe vectors 1-4 verified; `test_branch_1` passed | **COMPLIANT** |
| `INV-GAP12-02` | Mandatory indictment ref & failure details in DB | `taskkernel.py:988, 1041-1072`; Raw SQLite inspection confirmed 0 unindicted fails; `test_branch_4` passed | **COMPLIANT** |
| `INV-GAP12-03` | Preservation of retry budget (`attempts < max_attempts`) | `taskkernel.py:1025-1029` routes to `RETRY_SCHEDULED`; `test_branch_5` & `test_branch_6` passed | **COMPLIANT** |
| `INV-GAP12-04` | Strict lease and actor verification in `_assert_lease()` | `taskkernel.py:485-487`; Probe vector 4 verified; `test_branch_3` passed | **COMPLIANT** |

---

## 6. CAVEATS

1. **`spec/scp_target_test_coverage.yaml` Manifest SHA**:
   In `tests/T00_integrity/test_scp_target_test_coverage.py`, tests fail because `manifest_blob_sha` in `spec/scp_target_test_coverage.yaml` (`5c9dbad52d...`) does not match the actual git blob SHA of `spec/scp_future_target_manifest.yaml` (`beedaa4367...`).
   - Root cause: Pre-existing drift introduced in commit `0c44c13`.
   - Impact on GAP-12: None. The files modified by Worker 1 (`taskkernel.py`, `ask_kernel_adapter.py`, `task_kernel_bridge.py`, `test_adversarial_kernel_flaws.py`) are strictly within GAP-12 scope and did not touch `spec/`.
2. No caveats regarding GAP-12 remediation logic.

---

## 7. CONCLUSION

Worker 1 has completely and cleanly remediated GAP-12. The remediation fulfills all requirements (R1 through R4), preserves all invariants (`INV-GAP12-01` through `INV-GAP12-04`), passes all regression audits (T00 Meta-Audit 0 regressions, T04 Kernel 87/87 passed, T03 Capability PEP 9/9 passed), and satisfies all adversarial stress tests without integrity violations.

**Verdict: APPROVE.**

---

## 8. INDEPENDENT VERIFICATION METHOD

To reproduce this review's verification:
1. `python tools/probes/probe_gap12_delta_audit.py` -> Must output `ALL_VECTORS_PROTECTED_GREEN` (exit code 0).
2. `pytest tests/T04_kernel/test_adversarial_kernel_flaws.py -q` -> 34 passed (exit code 0).
3. `pytest tests/T04_kernel -q` -> 87 passed (exit code 0).
4. `pytest tests/T03_capability/test_hands_authority_pep.py -q` -> 9 passed (exit code 0).
5. `python tools/t00_meta_audit.py` -> 0 new regressions (exit code 0).
