# DELTA AUDIT PHASE 4: PROBE BEFORE PATCH & MUTATION ANTI-PLACEBO REPORT

**Target Subsystem**: `scp/hands/hands_executor.py` & Capability / Authority Infrastructure  
**Auditor**: Challenger 1 (`challenger_probe_1`)  
**Role**: Empirical Challenger (Critic & Specialist)  
**Timestamp**: 2026-09-07T01:00:00Z  
**Governing Protocols**: SCP DNA (29 Principles), `scp-delta-audit`, `scp-capability-security-review`, Rules FA-01 through FA-10 (specifically FA-05, FA-08, FA-09)  
**Execution Mode**: Read-Only Empirical Audit (Zero Product Code Modifications to `scp/`)

---

## 1. Executive Verdict

| Audit Target | Suspected Flaw | Invariant Affected | Empirical Verdict | Evidence Level |
|---|---|---|---|---|
| `HandsExecutor.execute` (`hands_executor.py:111`) | Self-Granting Authority Fallback (`capability_token or self.capability_authority.issue(...)`) | **FA-05**, **INV-AUTH-01** (Disjoint Authority Boundary) | **CRITICAL VULNERABILITY PROVEN** | **Level 1** (Live Executable Exploit Probe) |
| `CapabilityAuthority.validate` & `HandsExecutor._check_capability` | Scope-Blind Token Validation (Read token accepted for Write action) | **INV-AUTH-02** (Scoped Subject-Resource Binding) | **CRITICAL VULNERABILITY PROVEN** | **Level 1** (Live Executable Exploit Probe) |
| Probe Test Harness (`probe_hands_authority_flaws.py`) | Placebo Test Risk (False positive / False negative harness) | Phase 4 Anti-Placebo Mandate | **ANTI-PLACEBO SENSITIVITY PROVEN** (Baseline RED -> Guarded GREEN) | **Level 1** (Live Mutation Anti-Placebo Verification) |

**Summary Conclusion**:
The suspected "Tử huyệt bạo chúa" (FA-05 violation) in `HandsExecutor` is **100% verified and empirically reproducible**.
1. When a caller provides `capability_token=None`, `HandsExecutor` mints its own valid capability token on the fly, validates its own newly issued token, and commits physical filesystem mutations (`pc.write_file`) without caller authorization.
2. When a caller provides a token issued strictly for read-only `hands:pc.status`, `HandsExecutor` accepts the token without verifying that the token's subject matches `hands:pc.write_file`, committing physical filesystem mutations under an inappropriate grant.
3. The probe harness was subjected to the **Phase 4 Mutation Anti-Placebo protocol**: Under baseline code, strict invariant assertions failed with `AssertionError` (demonstrating exploitability); under an invariant-preserving PEP guard, the exact same assertions passed (demonstrating correctness and probe sensitivity).

---

## 2. Probe Architecture & Invariant Specifications

The probe script was implemented at:
`c:\Users\check\Downloads\scp\tools\probes\probe_hands_authority_flaws.py`

### 2.1 Enforced Invariants
- **INV-AUTH-01 (FA-05 - Disjoint Authority Boundary)**: The Tool Executor (`HandsExecutor` / PEP) must never possess token issuance capability, minting authority, or write-access to the Capability Authority's issuance interface; missing caller token must fail closed immediately.
- **INV-AUTH-02 (Scoped Subject-Resource Binding)**: Every capability token accepted by `HandsExecutor` must be cryptographically and durably bound to a specific execution subject (`task_id`, `attempt_id`), target action name, and resource hash; a token issued for action $A$ cannot authorize action $B$.

### 2.2 Formal Invariant Assertion Definition
```python
def verify_zero_trust_invariant(result: dict[str, Any], target_path: Path, test_label: str) -> None:
    if result.get("success") is not False:
        raise AssertionError(
            f"[{test_label}] INVARIANT VIOLATION: Action execution succeeded without valid authorized capability token! "
            f"Result: {json.dumps(result, default=str)}"
        )
    if target_path.exists():
        raise AssertionError(
            f"[{test_label}] INVARIANT VIOLATION: State mutation committed to host filesystem at: {target_path}!"
        )
    error_msg = str(result.get("error", ""))
    if not any(k in error_msg.lower() for k in ["capability", "unauthorized", "scope", "revoked"]):
        raise AssertionError(
            f"[{test_label}] INVARIANT VIOLATION: Rejection reason does not reflect capability enforcement! "
            f"Error: {error_msg}"
        )
```

### 2.3 Simulated Invariant-Preserving Guard (`GuardedHandsExecutor`)
To demonstrate anti-placebo sensitivity without modifying production code in `scp/`, a subclassed `GuardedHandsExecutor` was established within the probe harness:
```python
class GuardedHandsExecutor(HandsExecutor):
    async def execute(self, action: str, params=None, capability_level=0, approved=False, dry_run=False, capability_token=None):
        # Guard 1: Zero-Trust PEP Fail-Closed if token is missing (FA-05 / INV-AUTH-01)
        if capability_token is None:
            result = {
                "success": False,
                "action": action,
                "error": "CapabilityRequiredError: Caller must provide an authorized capability token (FA-05 violation: self-granting prohibited)",
                "verification": {"passed": False},
            }
            self._audit("ACTION_BLOCKED_NO_CAPABILITY", result)
            return result

        # Guard 2: Scoped Subject-Resource Binding (INV-AUTH-02)
        expected_subject = f"hands:{action}"
        if capability_token.subject != expected_subject:
            result = {
                "success": False,
                "action": action,
                "error": f"CapabilityScopeMismatchError: Token subject '{capability_token.subject}' does not match required action '{expected_subject}' (INV-AUTH-02)",
                "verification": {"passed": False},
            }
            self._audit("ACTION_BLOCKED_SCOPE_MISMATCH", result)
            return result

        return await super().execute(action, params, capability_level, approved, dry_run, capability_token)
```

---

## 3. Sub-test Results & Evidence Breakdown

### 3.1 Sub-Test 1: Self-Granting Authority Reproduction (FA-05 Breach)
- **Precondition**: Caller provides `capability_token=None`.
- **Target Action**: `pc.write_file` (Mutating, Level 3, Approved=True).
- **Target File**: `unauthorized_self_granted.txt` in an isolated sandbox directory.
- **Empirical Observation**:
  - `result["success"]`: `True`
  - `result["action"]`: `pc.write_file`
  - `result["capabilityEpoch"]`: `0` (Synthesized and attached by executor)
  - `target_file.exists()`: `True`
  - `target_file.read_text()`: `'VULNERABILITY_PROVEN: Written without caller capability token'`
- **Finding**: **CONFIRMED VULNERABLE**. `HandsExecutor` autonomously self-issued authority and executed an OS filesystem write without caller token.

### 3.2 Sub-Test 2: Scope Confusion / Privilege Escalation (INV-AUTH-02 Breach)
- **Precondition**: Caller holds a token issued strictly for `hands:pc.status` (Read-only, Level 0, Token ID: `bf647908c06445f781af2aaf207e02c0`).
- **Target Action**: `pc.write_file` (Mutating, Level 3, Approved=True).
- **Target File**: `unauthorized_scope_bypass.txt` in an isolated sandbox directory.
- **Empirical Observation**:
  - `caller_token.subject`: `'hands:pc.status'`
  - `result["success"]`: `True`
  - `result["action"]`: `pc.write_file`
  - `target_file.exists()`: `True`
  - `target_file.read_text()`: `'VULNERABILITY_PROVEN: Written using pc.status read-only token'`
- **Finding**: **CONFIRMED VULNERABLE**. `CapabilityAuthority.validate` checked only `epoch` and `revoked` flag, completely ignoring `token.subject`. A read token was accepted for state-mutating execution.

### 3.3 Sub-Test 3: Mutation Anti-Placebo Verification
- **Step 3A (Baseline Mutation Check)**:
  - `verify_zero_trust_invariant` evaluated against Baseline No-Token execution:
    - **Result**: Raised `AssertionError: [Baseline No-Token] INVARIANT VIOLATION: Action execution succeeded without valid authorized capability token!`.
  - `verify_zero_trust_invariant` evaluated against Baseline Scope-Confusion execution:
    - **Result**: Raised `AssertionError: [Baseline Scope-Confusion] INVARIANT VIOLATION: Action execution succeeded without valid authorized capability token!`.
  - **Status**: **DEMONSTRABLY RED (Vulnerable)**.
- **Step 3B (Guarded Implementation Check)**:
  - `verify_zero_trust_invariant` evaluated against Guarded No-Token execution:
    - `result["success"]`: `False`
    - `result["error"]`: `'CapabilityRequiredError: Caller must provide an authorized capability token (FA-05 violation: self-granting prohibited)'`
    - File exists on disk: `False`
    - **Result**: Passed invariant assertion! (**GREEN**)
  - `verify_zero_trust_invariant` evaluated against Guarded Scope-Mismatch execution:
    - `result["success"]`: `False`
    - `result["error"]`: `'CapabilityScopeMismatchError: Token subject \'hands:pc.status\' does not match required action \'hands:pc.write_file\' (INV-AUTH-02)'`
    - File exists on disk: `False`
    - **Result**: Passed invariant assertion! (**GREEN**)
  - Guarded execution with legitimate authorized token (`authority.issue("hands:pc.write_file")`):
    - `result["success"]`: `True`
    - File exists on disk: `True`
    - Content matches: `True`
    - **Result**: Passed legitimate execution sanity check! (**GREEN, No Regression**)
- **Anti-Placebo Sensitivity Verdict**:
  - Baseline Mutation Assertion Fails (RED): `True`
  - Guarded Invariant Assertion Passes (GREEN): `True`
  - Overall Anti-Placebo Sensitivity Proven: `True` (**NON-PLACEBO CONFIRMED**)

---

## 4. Raw Terminal Execution Provenance (FA-08 & FA-09 Compliance)

Below is the verbatim terminal output obtained from executing `python tools/probes/probe_hands_authority_flaws.py` via `run_command` in Python 3.12:

```text
==============================================================================
  SCP PHASE 4 EMPIRICAL ADVERSARIAL PROBE HARNESS
==============================================================================
Execution Target: C:\Users\check\Downloads\scp\scp\hands\hands_executor.py
Python Runtime:   3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]
Timestamp:        2026-09-06T17:59:45Z
Isolated Sandbox Workspace: C:\Users\check\AppData\Local\Temp\scp_probe_pep_fgy1auhq

==============================================================================
  SUB-TEST 1: Self-Granting Authority Reproduction (FA-05 Breach)
==============================================================================
Precondition: Caller provides capability_token=None.
Action Requested: pc.write_file (Mutating, Level 3, Approved=True).
Execution Result 'success': True
Action Executed: pc.write_file
Capability Epoch Attached in Result: 0
Verification Passed: True
Physical File Exists on Disk: True
Physical File Content on Disk: 'VULNERABILITY_PROVEN: Written without caller capability token'

>>> VERDICT SUB-TEST 1: [CONFIRMED VULNERABLE]
    HandsExecutor self-minted authority and committed physical filesystem side effects!

==============================================================================
  SUB-TEST 2: Scope Confusion / Privilege Escalation (INV-AUTH-02 Breach)
==============================================================================
Precondition: Caller holds token issued solely for 'hands:pc.status' (Read-Only, Level 0).
Action Requested: pc.write_file (Mutating, Level 3, Approved=True).
Caller Token Subject: 'hands:pc.status'
Caller Token Epoch: 0
Caller Token ID: bf647908c06445f781af2aaf207e02c0
Execution Result 'success': True
Action Executed: pc.write_file
Verification Passed: True
Physical File Exists on Disk: True
Physical File Content on Disk: 'VULNERABILITY_PROVEN: Written using pc.status read-only token'

>>> VERDICT SUB-TEST 2: [CONFIRMED VULNERABLE]
    HandsExecutor accepted a read-only token for a write action (Scope-blind validation)!

==============================================================================
  SUB-TEST 3: Mutation Anti-Placebo Verification
==============================================================================
Requirement: Prove probe sensitivity by demonstrating RED on Baseline, GREEN on Guarded.

--- [Step 3A] Evaluating Invariant Assertions against CURRENT BASELINE CODE ---
[EXPECTED RED]: Baseline failed invariant check as predicted: [Baseline No-Token] INVARIANT VIOLATION: Action execution succeeded without valid authorized capability token! Result: {"success": true, "path": "C:\\Users\\check\\AppData\\Local\\Temp\\scp_probe_pep_fgy1auhq\\baseline_no_token.txt", "backupId": null, "bytes": 5, "content_sha256": "c2d0da0251f952aa0a61276406d4a48ae94fd7eca84c0fddf94c89471790708c", "auditStatus": "OK", "checkpointId": "2e297fb0ef62464eade6f86f0f20b9a9", "verification": {"passed": true, "rule": "file_hash_and_exists"}, "action": "pc.write_file", "durationMs": 12, "policy": {"name": "pc.write_file", "description": "Write a workspace file with backup", "domain": "pc", "risk": "medium", "capability_level": 3, "requires_approval": true, "mutates_state": true, "verifier": "file_hash_and_exists", "rollback": "restore_backup"}, "capabilityEpoch": 0}
[EXPECTED RED]: Baseline failed invariant check as predicted: [Baseline Scope-Confusion] INVARIANT VIOLATION: Action execution succeeded without valid authorized capability token! Result: {"success": true, "path": "C:\\Users\\check\\AppData\\Local\\Temp\\scp_probe_pep_fgy1auhq\\baseline_scope.txt", "backupId": null, "bytes": 5, "content_sha256": "f80f514a2af03e24e1d757c6affdadd104f02e45aab583beac2c783810fa6e98", "auditStatus": "OK", "checkpointId": "0664cd709513476298bde62f2c941bb4", "verification": {"passed": true, "rule": "file_hash_and_exists"}, "action": "pc.write_file", "durationMs": 11, "policy": {"name": "pc.write_file", "description": "Write a workspace file with backup", "domain": "pc", "risk": "medium", "capability_level": 3, "requires_approval": true, "mutates_state": true, "verifier": "file_hash_and_exists", "rollback": "restore_backup"}, "capabilityEpoch": 0}

Baseline Vulnerability Status: DEMONSTRABLY RED (Vulnerable)

--- [Step 3B] Evaluating Invariant Assertions against GUARDED IMPLEMENTATION ---
Guarded (No-Token) Result: success=False, error='CapabilityRequiredError: Caller must provide an authorized capability token (FA-05 violation: self-granting prohibited)'
[EXPECTED GREEN]: Guarded No-Token successfully enforced Zero-Trust PEP (Blocked fail-closed, no disk mutation)!
Guarded (Scope-Mismatch) Result: success=False, error='CapabilityScopeMismatchError: Token subject 'hands:pc.status' does not match required action 'hands:pc.write_file' (INV-AUTH-02)'
[EXPECTED GREEN]: Guarded Scope-Mismatch successfully enforced INV-AUTH-02 (Blocked fail-closed, no disk mutation)!
Guarded (Valid Token) Result: success=True, file_exists=True
[EXPECTED GREEN]: Legitimate authorized operation executed successfully without regression!

==============================================================================
  ANTI-PLACEBO SENSITIVITY SUMMARY
==============================================================================
Baseline Mutation Assertion Fails (RED):       True  [Proven Vulnerable]
Guarded Invariant Assertion Passes (GREEN):     True  [Proven Correct]
Overall Anti-Placebo Sensitivity Proven:        True  [NON-PLACEBO CONFIRMED]

==============================================================================
  OVERALL PROBE HARNESS VERDICT
==============================================================================
[SUCCESS]: ALL 3 SUB-TESTS SATISFIED EMPIRICALLY.
1. Sub-test 1: Self-Granting reproduced live (FA-05 breach confirmed).
2. Sub-test 2: Scope Confusion reproduced live (INV-AUTH-02 breach confirmed).
3. Sub-test 3: Mutation Anti-Placebo proven (Red on Baseline -> Green on Guarded).
Execution Duration: 0.08s
Cleaned up sandbox workspace: C:\Users\check\AppData\Local\Temp\scp_probe_pep_fgy1auhq
```

---

## 5. Non-Invasive Audit Confirmation

In accordance with strict Delta Audit governing rules:
- **Zero Production Files Modified**: `git status --short` confirms that zero files under `scp/` were altered.
- **Zero Disk Residue**: All probe executions operated within temporary directories (`C:\Users\check\AppData\Local\Temp\scp_probe_pep_*`) that were cleaned up upon completion.
- **Reproducibility**: The probe script is checked in at `tools/probes/probe_hands_authority_flaws.py` and can be independently re-run via `python tools/probes/probe_hands_authority_flaws.py` on any environment.
