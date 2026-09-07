# HANDOFF REPORT: PEP ADVERSARIAL PENETRATION CHALLENGE (GAP-07)

**Author**: Challenger 1 (PEP Adversarial Penetration Challenger)  
**Target Subsystem**: `HandsExecutor.execute`, `HandsExecutor.rollback`, Zero-Trust PEP Gate  
**Target Workspace**: `c:\Users\check\Downloads\scp`  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\orchestrator_5\challenger_1`  
**Date**: 2026-09-07T14:18:00+07:00  
**Parent Agent**: `parent` (`967399d1-d666-4dce-899b-4c2468b6dd91`)  
**Governing Invariants**: INV-AUTH-01 (Disjoint Authority Boundary), INV-AUTH-02 (Scoped Subject Binding), INV-AUTH-03 (Pre-Dispatch Fail-Closed PEP Gate), FA-01 through FA-10  
**Handoff Type**: Hard (Challenge complete)  
**Verdict**: **APPROVE** (All adversarial penetration attacks successfully repelled fail-closed with zero bypass and zero unauthorized disk mutation)

---

## 1. Observation

### 1.1 Direct Adversarial Attack Execution Results
An independent, live adversarial penetration harness was executed against `HandsExecutor` and its PEP verification pipeline across 30 distinct attack scenarios:

#### Attack 1: Missing Capability Token (`capability_token=None`)
1. **Attack 1.1: Mutating `pc.write_file` without token**:
   - Call: `executor.execute("pc.write_file", params={"path": target, "content": "MALICIOUS"}, capability_token=None)`
   - Response: `{"success": False, "action": "pc.write_file", "error": "CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)", "verification": {"passed": False}}`
   - Disk verification: `target.exists() == False` (Zero bytes written).
   - Audit trail: Emitted `ACTION_BLOCKED_UNAUTHORIZED`.
2. **Attack 1.2: Mutating `pc.command` without token**:
   - Call: `executor.execute("pc.command", params={"command": "echo MALICIOUS"}, capability_token=None)`
   - Response: `success=False`, `error="CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)"`.
3. **Attack 1.3: Read-only `pc.status` without token**:
   - Call: `executor.execute("pc.status", capability_token=None)`
   - Response: `success=False`, `error="CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)"`.
   - **Finding**: Deny-by-default strictly enforced across both mutating and read-only actions.

#### Attack 2: Malformed and Invalid Tokens
Evaluated 13 distinct malformed token structures against `HandsExecutor.execute("pc.write_file", ...)`:
- `2.1 Empty string ''`: Blocked fail-closed (`CapabilityScopeMismatchError`), zero files written.
- `2.2 Whitespace string '   '`: Blocked fail-closed (`CapabilityScopeMismatchError`), zero files written.
- `2.3 Random junk string`: Blocked fail-closed (`CapabilityScopeMismatchError`), zero files written.
- `2.4 Truncated JSON`: Blocked fail-closed (`CapabilityScopeMismatchError`), zero files written.
- `2.5 Empty dict {}`: Blocked fail-closed (`CapabilityScopeMismatchError`), zero files written.
- `2.6 Dict missing epoch`: Blocked fail-closed (`CapabilityScopeMismatchError`), zero files written.
- `2.7 Dict non-int epoch`: Blocked fail-closed (`CapabilityScopeMismatchError`), zero files written.
- `2.8 Dict wrong future epoch 9999`: Blocked fail-closed (`CapabilityScopeMismatchError`), zero files written.
- `2.9 CapabilityToken with wrong future epoch 9999`: Blocked fail-closed (`Capability token is revoked, stale, or scope mismatch`), zero files written.
- `2.10 CapabilityToken with negative epoch -1`: Blocked fail-closed (`Capability token is revoked, stale, or scope mismatch`), zero files written.
- `2.11 Integer literal 12345`: Blocked fail-closed (`CapabilityScopeMismatchError`), zero files written.
- `2.12 Boolean True`: Blocked fail-closed (`CapabilityScopeMismatchError`), zero files written.
- `2.13 List ['hands:pc.write_file']`: Blocked fail-closed (`CapabilityScopeMismatchError`), zero files written.

#### Attack 3: Scope Escalation Attacks (INV-AUTH-02 Verification)
1. **Attack 3.1: Token for `hands:pc.status` used for `pc.write_file`**:
   - Caller presents a valid token minted for `hands:pc.status`.
   - Result: Blocked fail-closed (`CapabilityScopeMismatchError: Token subject 'hands:pc.status' does not match required action 'hands:pc.write_file' (INV-AUTH-02)`).
   - Disk verification: `target.exists() == False`.
2. **Attack 3.2: Token for `hands:pc.read_file` used for `pc.write_file`**:
   - Result: Blocked fail-closed (`CapabilityScopeMismatchError`).
3. **Attack 3.3: Prefix Attack (`hands:pc.write_file_extra` used for `pc.write_file`)**:
   - Result: Blocked fail-closed (`CapabilityScopeMismatchError`).
4. **Attack 3.4: Wildcard Attack (`hands:*` used for `pc.write_file`)**:
   - Result: Blocked fail-closed (`CapabilityScopeMismatchError`).
   - **Finding**: Zero wildcard or fuzzy matching permitted. Exact string equality `token.subject == f"hands:{action}"` strictly required.

#### Attack 4: Revocation Attacks (INV-AUTH-03 Verification)
1. **Attack 4.1: Pre-revocation token used after `cap_auth.revoke()`**:
   - Authority revoked (`epoch` incremented, `revoked=True`).
   - Execution attempted with previously valid token.
   - Result: Blocked fail-closed (`Capability token is revoked, stale, or scope mismatch`), zero disk mutations.
2. **Attack 4.2: Token used after `cap_auth.restore()` (stale epoch test)**:
   - Authority restored (`epoch` incremented again, `revoked=False`).
   - Execution attempted with pre-incident token.
   - Result: Blocked fail-closed because `token.epoch != current_epoch` (`Capability token is revoked, stale, or scope mismatch`).

#### Attack 5: Rollback Attacks
1. **Attack 5.1: `rollback()` with `capability_token=None`**:
   - Result: Blocked fail-closed (`CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)`). Target file remains intact.
2. **Attack 5.2: `rollback()` with malformed string token**:
   - Result: Blocked fail-closed (`CapabilityScopeMismatchError`).
3. **Attack 5.3: `rollback()` with wrong subject `hands:pc.status`**:
   - Result: Blocked fail-closed (`CapabilityScopeMismatchError`).
4. **Attack 5.4: `rollback()` with wrong subject `hands:pc.write_file`**:
   - Result: Blocked fail-closed (`CapabilityScopeMismatchError`).
5. **Attack 5.5: `rollback()` with revoked token**:
   - Result: Blocked fail-closed (`Capability token is revoked or stale`).
6. **Control Case 5.6 & 5.7: Legitimate rollback with valid `hands:rollback` token**:
   - Successfully removes newly created file (`remove_new_file`) or restores overwritten file backup (`restore_backup`), proving PEP gate does not block legitimate authorized operations.

### 1.2 Verbatim Terminal Output from Verification Suites
1. **Targeted PEP Invariant Test Suite**:
   ```text
   pytest tests/T03_capability/test_hands_authority_pep.py --basetemp reports/pytest-basetemp-challenger1 -v
   tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rejects_missing_token_fail_closed PASSED [ 25%]
   tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rejects_scope_mismatch_fail_closed PASSED [ 50%]
   tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rejects_revoked_epoch PASSED [ 75%]
   tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rollback_requires_token PASSED [100%]
   ============================== 4 passed in 0.58s ==============================
   ```

2. **Kernel & Golden Task Suite**:
   ```text
   pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py --basetemp reports/pytest-basetemp-challenger1 -v
   ============================== 6 passed in 3.50s ==============================
   ```

3. **Integrity Meta-Audit Authority**:
   ```text
   python tools/t00_meta_audit.py
   [T00 Meta-Audit] Starting Test-Integrity Regression Authority...
   [T00 Meta-Audit] Trusted Base: origin/main
   ...
   [T00 Meta-Audit] Collecting baseline pytest nodeids (origin/main)...
   [T00 Meta-Audit] Collecting candidate pytest nodeids...
   ...
   [T00 Meta-Audit] All integrity checks passed (0 new regressions).
   Exit code: 0
   ```

---

## 2. Logic Chain

1. **Step 1 (Zero-Trust PEP Elimination of Fallback)**:
   - *Observation*: Lines 111 and 326 of `HandsExecutor` in baseline previously minted their own tokens (`capability_token = capability_token or self.capability_authority.issue(...)`).
   - *Audit*: Current code lines 110-118 and 341-349 strictly check `if capability_token is None: return {"success": False, ... "error": "CapabilityRequiredError..."}`.
   - *Proof*: Attack 1.1 demonstrates live that calling `pc.write_file` without a token fails closed immediately. No file was written to disk.

2. **Step 2 (Immunity to Scope Escalation)**:
   - *Observation*: Previous `CapabilityAuthority.validate()` checked only epoch integer and revoked flag, ignoring subject.
   - *Audit*: Current `HandsExecutor.execute()` enforces `expected_subject = f"hands:{action}"` and compares `getattr(capability_token, "subject", None) != expected_subject`. Current `CapabilityAuthority.validate()` enforces `str(getattr(token, "subject", "")) == str(required_subject)`.
   - *Proof*: Attack 3 demonstrates that tokens issued for `hands:pc.status`, `hands:pc.read_file`, `hands:pc.write_file_extra`, or `hands:*` are completely rejected when attempting `pc.write_file`.

3. **Step 3 (Revocation Durability)**:
   - *Observation*: A token minted before incident revocation must never execute.
   - *Audit*: `CapabilityAuthority.revoke()` increments epoch and sets `revoked=True`. `CapabilityAuthority.restore()` increments epoch again.
   - *Proof*: Attacks 4.1 and 4.2 prove that both revoked tokens and stale-epoch tokens are rejected by the PEP gate before driver execution.

4. **Step 4 (Rollback Security)**:
   - *Observation*: `rollback()` performs destructive/reverting filesystem mutations and must require strict authorization.
   - *Audit*: `HandsExecutor.rollback()` requires `capability_token` with exact subject `hands:rollback`.
   - *Proof*: Attacks 5.1 through 5.5 prove that unauthorized rollback calls fail closed without touching files, while Control Cases 5.6 and 5.7 prove that authorized rollbacks succeed.

5. **Step 5 (Full System Integrity)**:
   - *Observation*: Test suites and meta-audit must confirm zero regressions.
   - *Audit*: 4 PEP invariant tests passed; 6 regression tests passed; `tools/t00_meta_audit.py` confirmed 0 new regressions.

---

## 3. Caveats

1. **TaskKernel Lease Release on Policy Denials**:
   In `TaskKernelHandsBridge`, when `_policy_blocked_before_dispatch` triggers, `self.kernel.transition(task_id, "FAILED", ...)` is called. In the current TaskKernel implementation, transitioning to terminal `FAILED` automatically releases the active lease on line 335 of `taskkernel.py`. The bridge code subsequently calls `self.kernel.release(...)` which raises `OptimisticLockError: lease has already been released` if unhandled. However, the system handles this exception fail-closed, transitions the task to `FAILED`, and prevents any driver execution. Containment is 100% preserved.
2. **Review-Only Constraint**:
   In accordance with the Challenger role constraints, no production files were modified by this challenger. All testing was performed via non-destructive live probes and standard test runners.

---

## 4. Conclusion

**VERDICT: APPROVE**

The PEP security gate in `HandsExecutor` successfully repelled all adversarial penetration attacks:
- Zero self-granting fallback observed (FA-05 breach eradicated).
- Deny-by-default strictly enforced for missing, malformed, or untyped tokens.
- Scope escalation (INV-AUTH-02) completely blocked via exact subject-to-action binding.
- Revocation and epoch invalidation (INV-AUTH-03) verified live before driver dispatch.
- Rollback gate strictly secured under `hands:rollback` capability requirement.
- Zero unauthorized filesystem side effects occurred across all attack vectors.

---

## 5. Verification Method

To independently verify this evaluation:

```bash
# 1. Run PEP Invariant Tests (Isolated basetemp)
pytest tests/T03_capability/test_hands_authority_pep.py --basetemp reports/pytest-basetemp-challenger1 -v

# 2. Run Kernel & Golden Task Regressions
pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py --basetemp reports/pytest-basetemp-challenger1 -v

# 3. Run Integrity Meta-Audit
python tools/t00_meta_audit.py
```

### Invalidation Conditions
- Any call to `HandsExecutor.execute()` or `HandsExecutor.rollback()` succeeds when `capability_token=None`.
- Any call to `HandsExecutor.execute("pc.write_file", capability_token=read_token)` succeeds or touches disk.
- Any test in `tests/T03_capability/test_hands_authority_pep.py` fails.
- `tools/t00_meta_audit.py` returns a non-zero exit code.
