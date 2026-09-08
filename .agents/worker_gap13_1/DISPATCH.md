# DISPATCH — Worker GAP-13 #1 (Implementation & Causal Test Coverage)

## 🔒 Mandatory Binding
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## PRE-SESSION MANDATE
You MUST call `view_file` on:
1. `c:\Users\check\Downloads\scp\GA.md`
2. `c:\Users\check\Downloads\scp\.agents\GEMINI.md`
3. `c:\Users\check\Downloads\scp\.agents\AGENTS.md`
4. `c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md`
5. `c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md`

## Reference Inputs & Specifications
Carefully review:
- `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md` (authoritative user requirements)
- `c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md` (scope contracts)
- `c:\Users\check\Downloads\scp\.agents\explorer_gap13_2\handoff.md` (cryptographic & architecture design)
- `c:\Users\check\Downloads\scp\.agents\spec_miner_gap13_2\handoff.md` (Mermaid causal graph & 11-branch FA-13 coverage matrix)
- `c:\Users\check\Downloads\scp\tools\probes\probe_gap13_bypass.py` (anti-placebo exploit probe)

## Write Ownership
You own and have exclusive write permission to:
- `scp/task_kernel_parts/taskkernel.py`
- `scp/task_kernel.py` (if re-exporting `commit_approval` or updating transition docs)
- `tests/T04_kernel/test_adversarial_kernel_flaws.py`

## Implementation Tasks (Execute in order)
### Step 1: Pre-Patch Baseline & Probe RED Verification
Run `python tools/probes/probe_gap13_bypass.py` and confirm verbatim terminal output `VULNERABILITY_PROVEN_RED`.

### Step 2: Implement Code Remediation in `scp/task_kernel_parts/taskkernel.py`
1. **Raw Transition Guard**:
   In `TaskKernel.transition()`:
   ```python
   if old == "WAITING_APPROVAL" and to_state == "READY":
       raise InvalidTransition(
           "direct transition from WAITING_APPROVAL to READY is forbidden; use commit_approval() with valid capability token"
       )
   ```
2. **Helper `verify_approval_authority(token, task_id, secret, max_skew_seconds=300.0)`**:
   Implement fail-closed validation supporting:
   - Compact mint string token (`payload_b64.sig`) with scope `"approval:grant"`, `f"approval:grant:{task_id}"`, or `"*"`
   - `CapabilityToken` dataclass / dict / JSON string with subject matching approval scope
   - Operator signature dict (`actor`, `task_id`, `timestamp`, `signature`) signed with HMAC-SHA256
   - Rejections: None/empty -> `InvalidTokenSignatureError`, invalid/tampered signature -> `InvalidTokenSignatureError`, wrong scope -> `InvalidTransition` or `PermissionError`, task mismatch -> `InvalidTransition`, expired / future timestamp -> `InvalidTransition` / `InvalidTokenSignatureError`.
3. **Endpoint `TaskKernel.commit_approval()`**:
   Implement atomic approval commit:
   - Validate task exists, not killed, not in terminal state, current state == `WAITING_APPROVAL`.
   - OCC version check if `expected_version` is provided.
   - Validate token via `verify_approval_authority()`.
   - Atomic SQLite OCC execution:
     `UPDATE tasks SET state='READY', version=version+1, updated_at=? WHERE task_id=? AND version=? AND state='WAITING_APPROVAL'`
     Ensure `cur.rowcount == 1`, else raise `OptimisticLockError`.
   - Record immutable journal event `TASK_APPROVED` with token metadata, actor, and transition.
   - Commit transaction to disk and return updated task.

### Step 3: Implement FA-13 Causal Test Coverage in `tests/T04_kernel/test_adversarial_kernel_flaws.py`
Implement tests covering all 11 causal branches specified in `spec_miner_gap13_2/handoff.md`:
- BR-1: `test_gap13_branch_1_direct_transition_to_ready_blocked`
- BR-2: `test_gap13_branch_2_commit_approval_missing_token_rejected`
- BR-3: `test_gap13_branch_3_commit_approval_tampered_signature_rejected`
- BR-4: `test_gap13_branch_4_commit_approval_wrong_scope_rejected`
- BR-5: `test_gap13_branch_5_commit_approval_mismatched_task_id_rejected`
- BR-6: `test_gap13_branch_6_commit_approval_expired_token_rejected`
- BR-7: `test_gap13_branch_7_commit_approval_valid_capability_token_success`
- BR-8: `test_gap13_branch_8_commit_approval_valid_operator_signature_success`
- BR-9: `test_gap13_branch_9_commit_approval_occ_version_mismatch_rejected`
- BR-10: `test_gap13_branch_10_commit_approval_wrong_lifecycle_state_rejected`
- BR-11: `test_gap13_branch_11_full_lifecycle_with_approval_gate`

Strictly adhere to FA-01 and FA-02: DO NOT delete, skip, xfail, or loosen any assertions.

### Step 4: Verification & Reality Checks (FA-12)
1. Run `python tools/probes/probe_gap13_bypass.py` and verify it transitions to `ALL_VECTORS_PROTECTED_GREEN`.
2. Run `pytest tests/T04_kernel/ -q` and verify 100% pass (0 skips, 0 xfails).
3. Run `pytest tests/ -q` to ensure 0 regressions across the entire test suite.
4. Run `python tools/t00_meta_audit.py` to ensure 0 meta-audit regressions.

### Step 5: Deliver Handoff Report
Write full report in `c:\Users\check\Downloads\scp\.agents\worker_gap13_1\handoff.md` with:
- Observation (files changed, git diff summary, terminal logs)
- Logic Chain (remediation rationale)
- Caveats & Assumptions
- Conclusion (verdict on GAP-13 closure)
- Verification Method (exact commands executed and full results)
Report completion via `send_message`.
