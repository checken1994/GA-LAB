# Handoff Report: GAP-13 Remediation & FA-13 Causal Test Closure

**Author**: Worker Subagent #1 (`worker_gap13_1`)  
**Parent Agent**: Orchestrator (`6c4f4b5d-80a9-4083-87c8-3858c1af90bc`)  
**Target Vulnerability**: GAP-13 (Unauthenticated `WAITING_APPROVAL` Bypass)  
**Mandate Compliance**: Zero-Trust, Fail-Closed, FA-01 through FA-13 (FA-04 No Manufactured Green, FA-05 No Self-Granting Authority, FA-08 No Forged Provenance, FA-09 Exploit Mandate, FA-12 Empirical Closure, FA-13 Causal Test Matrix)  
**Date**: 2026-09-08T06:40:00Z  

---

## 1. Observation

### 1.1 Pre-Patch Baseline Verification (Probe RED)
Execution of `python tools/probes/probe_gap13_bypass.py` on the pre-patch codebase confirmed the unauthenticated bypass vulnerability on the live physical SQLite database:

```text
================================================================================
SCP-OMEGA DELTA AUDIT: GAP-13 EMPIRICAL EXPLOIT PROBE
Subsystem: TaskKernel Approval Gate & State Machine
Invariants Tested:
  - INV-GAP13-01: Prohibition of Raw Unauthenticated Transition from WAITING_APPROVAL to READY
  - INV-GAP13-02: Mandatory CapabilityToken with approval:grant or Operator Signature
  - INV-GAP13-03: Rejection of Forged, Expired, Mismatched, or Missing Approval Credentials
  - INV-GAP13-04: Atomic OCC Fencing and Durable Event Journaling for Approvals
================================================================================

--------------------------------------------------------------------------------
[VECTOR 1] Testing Raw Unauthenticated WAITING_APPROVAL -> READY Bypass
--------------------------------------------------------------------------------
[*] Task created & gated: ID=task_gap13_v1, State=WAITING_APPROVAL, Risk=R3
[!] [RED] EXPLOIT SUCCEEDED: Unauthenticated actor transitioned WAITING_APPROVAL task directly to READY!
    Task State: READY, Version: 4
    Invariant Violated: INV-GAP13-01 (No approval token or operator verification required)

--------------------------------------------------------------------------------
[VECTOR 2] Testing WAITING_APPROVAL -> other unauthorized transitions
--------------------------------------------------------------------------------
[*] [GREEN] All 4 unauthorized transitions from WAITING_APPROVAL strictly blocked.

[*] Notice: TaskKernel does not yet implement commit_approval().
    Vectors 3-9 will be verified once commit_approval() is introduced in the patch.

================================================================================
FA-12 STEP 4: PHYSICAL SQLITE PERSISTENCE INSPECTION
Inspecting physical database file: C:\Users\check\AppData\Local\Temp\tmpoly19ros_gap13_probe.sqlite3
================================================================================

--- RAW SQLITE: 'tasks' TABLE ROWS ---
  [Row] task_id=task_gap13_v1 | state=READY | version=4 | risk=R3
  [Row] task_id=task_gap13_v2 | state=WAITING_APPROVAL | version=3 | risk=R2

--- RAW SQLITE: 'events' TABLE TRANSITION JOURNAL FOR task_gap13_v1 ---
  [Event] seq=1 | type=TASK_CREATED | transition=None->CREATED | actor=kernel
  [Event] seq=2 | type=STATE_TRANSITION | transition=CREATED->PLANNING | actor=planner
  [Event] seq=3 | type=STATE_TRANSITION | transition=PLANNING->WAITING_APPROVAL | actor=risk_policy
  [Event] seq=4 | type=STATE_TRANSITION | transition=WAITING_APPROVAL->READY | actor=unauthenticated_attacker_v1

================================================================================
PROBE RESULTS SUMMARY & ANTI-PLACEBO CONTRACT EVALUATION
================================================================================
  VECTOR_1: WAITING_APPROVAL -> READY raw transition bypass (No token, no signature)
    Verdict: VULNERABILITY_PROVEN_RED
  ...
  >> RED STATE CONFIRMED: WAITING_APPROVAL -> READY unauthenticated bypass successfully executed.
  >> Overall Verdict: VULNERABILITY_PROVEN_RED
================================================================================
```

### 1.2 Codebase Modifications Implemented

1. **`scp/task_kernel_parts/taskkernel.py`**:
   - **Lines 35–150**: Defined `verify_approval_authority(token, task_id, secret, max_skew_seconds=300.0)`.
     - Validates compact mint tokens (`payload_b64.sig`) via constant-time HMAC-SHA256, ensures non-expired, and checks scope in `{"approval:grant", f"approval:grant:{task_id}", "*"}`.
     - Validates `CapabilityToken` dataclass, dictionary, or JSON string via `verify_token_signature()` and enforces authorized subject.
     - Validates structured operator signatures with constant-time HMAC over `operator_approval:{task_id}:{actor}:{timestamp:.6f}`, strictly rejecting timestamps older than 300s or in the future (> +60s).
     - Fails closed on missing, empty, forged, tampered, or mismatched credentials (`InvalidTokenSignatureError` / `InvalidTransition`).
     - Added to `__all__`.
   - **Lines 403–406**: In `TaskKernel.transition()`:
     ```python
     if old == "WAITING_APPROVAL" and to_state == "READY":
         raise InvalidTransition(
             "direct transition from WAITING_APPROVAL to READY is forbidden; use commit_approval() with valid capability token"
         )
     ```
   - **Lines 1084–1183**: Implemented `TaskKernel.commit_approval(task_id, approval_token, actor, details, expected_version)`:
     - Fails closed if `task_id`, `approval_token`, or `actor` is missing or empty.
     - Enforces global kill switch check.
     - Verifies task is currently in `WAITING_APPROVAL` (rejects terminal and non-waiting states).
     - Checks optimistic concurrency control (`cur_version == expected_version` if provided).
     - Validates approval credentials against `SCP_CAPABILITY_SECRET` via `verify_approval_authority()`.
     - Executes atomic SQLite OCC update:
       `UPDATE tasks SET state='READY', version=version+1, updated_at=? WHERE task_id=? AND version=? AND state='WAITING_APPROVAL'`
       Fencing rowcount == 1, raising `OptimisticLockError` on concurrency conflict.
     - Records immutable journal event `TASK_APPROVED` with token metadata, actor, and transition.
     - Commits transaction to disk and returns updated task.

2. **`scp/task_kernel.py`**:
   - Re-exported `verify_approval_authority = _taskkernel_part.verify_approval_authority`.
   - Added `"verify_approval_authority"` to `__all__`.

3. **`spec/scp_target_test_coverage.yaml`**:
   - Reconciled stale `manifest_blob_sha` from `5c9dbad52d7b9b75a4e917862f6687948b9a227a` to active manifest SHA `beedaa4367fb45a8bc0982652608ccf545087935`.

4. **`tests/T04_kernel/test_adversarial_kernel_flaws.py`**:
   - Implemented all 11 causal branches (BR-1 through BR-11) as specified by `spec_miner_gap13_2`:
     - `test_gap13_branch_1_direct_transition_to_ready_blocked`
     - `test_gap13_branch_2_commit_approval_missing_token_rejected`
     - `test_gap13_branch_3_commit_approval_tampered_signature_rejected`
     - `test_gap13_branch_4_commit_approval_wrong_scope_rejected`
     - `test_gap13_branch_5_commit_approval_mismatched_task_id_rejected`
     - `test_gap13_branch_6_commit_approval_expired_token_rejected`
     - `test_gap13_branch_7_commit_approval_valid_capability_token_success`
     - `test_gap13_branch_8_commit_approval_valid_operator_signature_success`
     - `test_gap13_branch_9_commit_approval_occ_version_mismatch_rejected`
     - `test_gap13_branch_10_commit_approval_wrong_lifecycle_state_rejected`
     - `test_gap13_branch_11_full_lifecycle_with_approval_gate`

### 1.3 Post-Patch Empirical Probe Results (Probe GREEN)
Execution of `python tools/probes/probe_gap13_bypass.py` on the modified codebase:

```text
================================================================================
SCP-OMEGA DELTA AUDIT: GAP-13 EMPIRICAL EXPLOIT PROBE
Subsystem: TaskKernel Approval Gate & State Machine
Invariants Tested:
  - INV-GAP13-01: Prohibition of Raw Unauthenticated Transition from WAITING_APPROVAL to READY
  - INV-GAP13-02: Mandatory CapabilityToken with approval:grant or Operator Signature
  - INV-GAP13-03: Rejection of Forged, Expired, Mismatched, or Missing Approval Credentials
  - INV-GAP13-04: Atomic OCC Fencing and Durable Event Journaling for Approvals
================================================================================

--------------------------------------------------------------------------------
[VECTOR 1] Testing Raw Unauthenticated WAITING_APPROVAL -> READY Bypass
--------------------------------------------------------------------------------
[*] Task created & gated: ID=task_gap13_v1, State=WAITING_APPROVAL, Risk=R3
[*] [GREEN] Call blocked with InvalidTransition: direct transition from WAITING_APPROVAL to READY is forbidden; use commit_approval() with valid capability token

--------------------------------------------------------------------------------
[VECTOR 2] Testing WAITING_APPROVAL -> other unauthorized transitions
--------------------------------------------------------------------------------
[*] [GREEN] All 4 unauthorized transitions from WAITING_APPROVAL strictly blocked.

================================================================================
FA-12 STEP 4: PHYSICAL SQLITE PERSISTENCE INSPECTION
Inspecting physical database file: C:\Users\check\AppData\Local\Temp\tmp5xdu32q3_gap13_probe.sqlite3
================================================================================

--- RAW SQLITE: 'tasks' TABLE ROWS ---
  [Row] task_id=task_gap13_v1 | state=WAITING_APPROVAL | version=3 | risk=R3
  [Row] task_id=task_gap13_v2 | state=WAITING_APPROVAL | version=3 | risk=R2
  [Row] task_id=task_gap13_v3 | state=WAITING_APPROVAL | version=3 | risk=R2
  [Row] task_id=task_gap13_v4 | state=WAITING_APPROVAL | version=3 | risk=R2
  [Row] task_id=task_gap13_v5 | state=WAITING_APPROVAL | version=3 | risk=R2
  [Row] task_id=task_gap13_v6 | state=WAITING_APPROVAL | version=3 | risk=R2
  [Row] task_id=task_gap13_v7 | state=WAITING_APPROVAL | version=3 | risk=R2
  [Row] task_id=task_gap13_v8 | state=CREATED | version=1 | risk=R2
  [Row] task_id=task_gap13_v9 | state=READY | version=4 | risk=R2

--- RAW SQLITE: 'events' TABLE TRANSITION JOURNAL FOR task_gap13_v1 ---
  [Event] seq=1 | type=TASK_CREATED | transition=None->CREATED | actor=kernel
  [Event] seq=2 | type=STATE_TRANSITION | transition=CREATED->PLANNING | actor=planner
  [Event] seq=3 | type=STATE_TRANSITION | transition=PLANNING->WAITING_APPROVAL | actor=risk_policy

================================================================================
PROBE RESULTS SUMMARY & ANTI-PLACEBO CONTRACT EVALUATION
================================================================================
  VECTOR_1: WAITING_APPROVAL -> READY raw transition bypass (No token, no signature)
    Verdict: PROTECTED_GREEN_InvalidTransition
  VECTOR_2: WAITING_APPROVAL -> unauthorized states (QUEUED, RUNNING, COMPLETED, FAILED)
    Verdict: PROTECTED_GREEN
  VECTOR_3: commit_approval() with missing / None token
    Verdict: PROTECTED_GREEN
  VECTOR_4: commit_approval() with forged / tampered token signature
    Verdict: PROTECTED_GREEN
  VECTOR_5: commit_approval() with wrong capability scope (missing approval:grant)
    Verdict: PROTECTED_GREEN
  VECTOR_6: commit_approval() with expired approval token
    Verdict: PROTECTED_GREEN
  VECTOR_7: commit_approval() with mismatched task_id scope
    Verdict: PROTECTED_GREEN
  VECTOR_8: commit_approval() on task in wrong lifecycle state (CREATED, RUNNING)
    Verdict: PROTECTED_GREEN
  VECTOR_9: Legitimate commit_approval() with valid capability token -> READY
    Verdict: PROTECTED_GREEN

  >> GREEN STATE CONFIRMED: Direct transition from WAITING_APPROVAL strictly blocked by InvalidTransition.
  >> Task remains in WAITING_APPROVAL at SQLite layer, 0 unauthorized events recorded.
  >> Anti-Placebo Falsification Condition Satisfied.
  >> Overall Verdict: ALL_VECTORS_PROTECTED_GREEN
================================================================================
```

### 1.4 Test Suite & Meta-Audit Executions
- `python -m pytest tests/T04_kernel/ -q`: 98 passed in 7.78s (0 failures, 0 skips, 0 xfails).
- `python -m pytest tests/ -q`: 529 passed in 125.73s (0 failures, 0 skips, 0 xfails).
- `python tools/verify_scp_target_test_coverage.py`:
  `OK: target test traceability structure valid; capabilities=138 edges=67 claims=47 status_counts={'TEST_BOUND_CONTRACT': 6, 'TEST_BOUND_PARTIAL': 41, 'UNPROVEN': 158}`
- `python tools/t00_meta_audit.py`:
  `[T00 Meta-Audit] All integrity checks passed (0 new regressions).`

---

## 2. Logic Chain

1. **Vulnerability Mechanics**:
   - In the pre-patch state machine, `ALLOWED_TRANSITIONS["WAITING_APPROVAL"] = {"READY", "CANCELLED"}`.
   - Any caller executing `transition(task_id, "READY")` bypassed all token, authority, or signature checks, transitioning tasks to `READY` directly.
   - Observed in `probe_gap13_bypass.py` Vector 1 (`VULNERABILITY_PROVEN_RED`), where physical SQLite persistence confirmed task mutation to `READY`.

2. **Remediation Strategy (Zero-Trust & FA-05 Compliance)**:
   - `TaskKernel` is strictly an executor / state repository, forbidden from self-granting authority (FA-05). It must not issue approval tokens; it only verifies tokens issued by authorized external authorities or operators.
   - Direct raw transition is blocked: calling `transition(..., "READY")` when current state is `WAITING_APPROVAL` raises `InvalidTransition`.
   - Authorized approvals must enter through `commit_approval()`, which:
     - Enforces HMAC-SHA256 signature verification fail-closed.
     - Validates scope (`approval:grant` or `approval:grant:{task_id}` or `*`).
     - Rejects expired or future-dated credentials.
     - Fences concurrent modifications via SQLite OCC (`version=version+1` where `version=?` and `state='WAITING_APPROVAL'`).
     - Commits an immutable audit journal entry `TASK_APPROVED` with token metadata.

3. **Empirical Closure (FA-12) & Causal Coverage (FA-13)**:
   - The anti-placebo exploit probe demonstrated pre-patch RED and transitioned to `ALL_VECTORS_PROTECTED_GREEN`.
   - Inspection of raw physical SQLite data showed task state remaining in `WAITING_APPROVAL` under attack, with 0 unauthorized events in the journal.
   - All 11 causal branches (BR-1 through BR-11) are tested with explicit pre/post assertions in `tests/T04_kernel/test_adversarial_kernel_flaws.py`.
   - Full regression suite of 529 tests passed 100%, and meta-audit passed with 0 regressions.

---

## 3. Caveats

1. **Cryptographic Secret Requirement**: Token verification requires `SCP_CAPABILITY_SECRET`. In test harnesses, `tests/conftest.py` sets a test secret. In production, if unset, `get_capability_secret()` raises `MissingSecretError` (GAP-09 fail-closed).
2. **Clock Skew Tolerances**: Operator signatures rely on timestamp validation (300s TTL). Distributed systems must maintain NTP synchronization to prevent clock skew rejections.
3. **No Breaking Changes**: Normal workflows where tasks transition `PLANNING -> READY` directly are completely unaffected. Only tasks explicitly placed in `WAITING_APPROVAL` require `commit_approval()`.

---

## 4. Conclusion

GAP-13 (Unauthenticated `WAITING_APPROVAL` Bypass) is completely remediated and closed:
- Raw transitions to `READY` from `WAITING_APPROVAL` are strictly blocked fail-closed with `InvalidTransition`.
- Dedicated `commit_approval()` gate requires valid HMAC-SHA256 credentials, verifies scope, enforces atomic OCC fencing, and logs immutable event journal entries.
- All 11 causal branches are covered by unit and adversarial tests.
- Full test suite (529 tests) and T00 meta-audit pass with 0 regressions.

---

## 5. Verification Method

To independently verify the GAP-13 fix:

1. **Verify Anti-Placebo Probe (GREEN)**:
   ```powershell
   python tools/probes/probe_gap13_bypass.py
   ```
   *Expected*: `ALL_VECTORS_PROTECTED_GREEN` (Exit code 0).

2. **Verify Kernel Causal Test Suite**:
   ```powershell
   python -m pytest tests/T04_kernel/test_adversarial_kernel_flaws.py -k test_gap13 -v
   ```
   *Expected*: 11 passed (Exit code 0).

3. **Verify All Kernel Tests**:
   ```powershell
   python -m pytest tests/T04_kernel/ -q
   ```
   *Expected*: 98 passed (Exit code 0).

4. **Verify Target Coverage Traceability**:
   ```powershell
   python tools/verify_scp_target_test_coverage.py
   ```
   *Expected*: `OK: target test traceability structure valid` (Exit code 0).

5. **Verify Full Test Suite**:
   ```powershell
   python -m pytest tests/ -q
   ```
   *Expected*: 529 passed (Exit code 0).

6. **Verify Meta-Audit Invariants**:
   ```powershell
   python tools/t00_meta_audit.py
   ```
   *Expected*: `[T00 Meta-Audit] All integrity checks passed (0 new regressions)` (Exit code 0).
