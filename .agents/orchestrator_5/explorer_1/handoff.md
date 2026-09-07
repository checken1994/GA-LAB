# HANDOFF REPORT: HANDSEXECUTOR & CAPABILITY AUTHORITY CORE INVESTIGATION

**Author**: Explorer 1 (HandsExecutor & Authority Core Specialist)  
**Target Workspace**: `c:\Users\check\Downloads\scp`  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_1`  
**Governing Rules**: Zero-Trust PEP, Fail-Closed, Anti-Placebo, FA-01 through FA-10 (specifically FA-05)  
**Investigation Mode**: Read-Only Analysis (Zero production modifications)  
**Date**: 2026-09-07  

---

## 1. Observation

### 1.1 Anti-Placebo Probe Execution (Empirical Baseline Verification)
- **Command Executed**: `python tools/probes/probe_hands_authority_flaws.py`
- **Exit Code**: `0`
- **Verbatim Terminal Output**:
```text
==============================================================================
  SCP PHASE 4 EMPIRICAL ADVERSARIAL PROBE HARNESS
==============================================================================
Execution Target: C:\Users\check\Downloads\scp\scp\hands\hands_executor.py
Python Runtime:   3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]
Timestamp:        2026-09-07T03:14:45Z
Isolated Sandbox Workspace: C:\Users\check\AppData\Local\Temp\scp_probe_pep_ll83wzri

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
Caller Token ID: 0a94c83de80c4efa959fc5a7031b5fb3
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
[EXPECTED RED]: Baseline failed invariant check as predicted: [Baseline No-Token] INVARIANT VIOLATION: Action execution succeeded without valid authorized capability token! Result: {"success": true, ... "action": "pc.write_file", ...}
[EXPECTED RED]: Baseline failed invariant check as predicted: [Baseline Scope-Confusion] INVARIANT VIOLATION: Action execution succeeded without valid authorized capability token! Result: {"success": true, ... "action": "pc.write_file", ...}

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
```

### 1.2 Direct Code Inspections
- **File**: `scp/hands/hands_executor.py`
  - **Lines 110–115 (`execute`)**:
    ```python
    try:
        capability_token = capability_token or self.capability_authority.issue(f"hands:{action}")
    except CapabilityRevokedError as exc:
        result = {"success": False, "action": action, "error": str(exc), "verification": {"passed": False}}
        self._audit("ACTION_BLOCKED_CAPABILITY_REVOKED", result)
        return result
    ```
  - **Lines 324–328 (`rollback`)**:
    ```python
    async def rollback(self, checkpoint_id: str, capability_level: int = 3, approved: bool = False, capability_token: CapabilityToken | None = None) -> dict[str, Any]:
        try:
            capability_token = capability_token or self.capability_authority.issue("hands:rollback")
        except CapabilityRevokedError as exc:
            return {"success": False, "error": str(exc)}
    ```
  - **Lines 68–77 (`_check_capability`)**:
    ```python
    def _check_capability(self, definition: ActionDefinition, capability_level: int, approved: bool, capability_token: CapabilityToken | None) -> tuple[bool, str]:
        if not self.capability_authority.validate(capability_token):
            return False, "Capability token is revoked or stale"
        if self.controller.kill_switch_engaged():
            return False, "Kill switch is engaged"
        if capability_level < definition.capability_level:
            return False, f"Action requires capability >= {definition.capability_level}"
        if definition.requires_approval and not approved:
            return False, "Explicit approval required"
        return True, "Policy requirements satisfied"
    ```
  - **Lines 376–379 (`restore_capabilities`)**:
    ```python
    def restore_capabilities(self, reason: str = "operator_restore", actor: str = "operator") -> dict[str, Any]:
        result = self.capability_authority.restore(reason=reason, actor=actor)
        self._audit("CAPABILITIES_RESTORED", result)
        return result
    ```

- **File**: `scp/security/capability_epoch.py`
  - **Lines 108–114 (`validate`)**:
    ```python
    def validate(self, token: CapabilityToken | None) -> bool:
        if token is None:
            return False
        with self._lock:
            state = self._load()
            return not state["revoked"] and token.epoch == state["epoch"]
    ```

- **Protocol Boundaries Dropping Tokens**:
  - `scp/hands/task_kernel_bridge.py`:
    - Line 314: `execute(action, params, capability_level, approved, dry_run, request_key)` lacks `capability_token` parameter.
    - Line 338 & Line 482: Calls `await self.executor.execute(...)` without `capability_token`.
    - Line 99: `rollback(checkpoint_id, capability_level, approved)` lacks `capability_token` parameter and calls `self.executor.rollback` without token.
  - `scp/api/routes/hands_routes.py`:
    - Line 38: `HandsActionRequest` schema lacks `capabilityToken`.
    - Line 46: `HandsRollbackRequest` schema lacks `capabilityToken`.
  - `scp/hands/planner.py`:
    - Line 479: `await self.executor.execute(...)` drops `capability_token`.
  - `tests/T09_golden_task/test_golden_a_agent_os.py` & `tests/T04_kernel/test_kernel_p1_regressions.py`:
    - Call `bridge.execute()` without providing `capability_token`. Passes only due to line 111 self-issuance.

### 1.3 Baseline Test Suite Execution (Pre-Mutation Baseline)
- **Command Executed**: `pytest tests/ -q`
- **Exit Code**: `0`
- **Terminal Output**:
  ```text
  441 passed in 106.76s (0:01:46)
  ```
  Demonstrates that all 441 existing tests pass on the current baseline (exposing `PASS != TRUE` because tests pass without passing capability tokens due to line 111 auto-issuance).

---

## 2. Logic Chain

1. **Premise 1 (Observation 1.1 & 1.2)**: In `HandsExecutor.execute` (line 111) and `rollback` (line 326), when `capability_token is None`, the executor calls `self.capability_authority.issue()`.
2. **Premise 2 (Rule FA-05 & Invariant INV-AUTH-01)**: An executor (Policy Enforcement Point) must NEVER self-issue tokens. Callers must provide an authorized token issued by an independent authority (Policy Decision Point).
3. **Inference 1 (GAP-01 / FA-05 Breach)**: Current baseline code directly violates FA-05 and INV-AUTH-01 because the PEP acts as applicant, judge, and execution driver simultaneously.
4. **Premise 3 (Observation 1.1 & 1.2)**: `CapabilityAuthority.validate` checks only epoch integer and revocation boolean; it ignores `token.subject`.
5. **Inference 2 (GAP-02 / INV-AUTH-02 Breach)**: A token issued for benign read-only `hands:pc.status` has `token.epoch == state["epoch"]` and `not state["revoked"]`, which unconditionally validates for high-risk write operations like `pc.write_file`. This is an empirical scope confusion / privilege escalation flaw.
6. **Premise 4 (Observation 1.2)**: `HandsExecutor.restore_capabilities` exposes direct administrative un-quarantine capabilities at the tool driver level.
7. **Inference 3 (Administrative Quarantine Evasion)**: Any caller with access to the executor can un-revoke capabilities and advance the epoch, evading incident containment.
8. **Premise 5 (Observation 1.2)**: Callers across HTTP routes, kernel bridge, and planner currently drop or omit `capability_token`.
9. **Inference 4 (Coordinated Fix Requirement)**: Simply removing line 111 without updating callers will cause all bridge executions and golden tests to fail closed. Therefore, `capability_token` must be threaded through all boundary interfaces, and tests must supply valid tokens from a test authority.

---

## 3. Caveats

1. **Scope of Investigation**: This report provides read-only analysis and architectural specifications. Zero product files have been modified in this turn.
2. **Token Formats**: Note that `scp/core/capability_token.py` contains HMAC-signed tokens (`verify_token`), whereas `scp/security/capability_epoch.py` contains epoch-based tokens (`CapabilityToken`). The PEP in `HandsExecutor` uses `CapabilityAuthority` and `CapabilityToken` from `scp/security/capability_epoch.py`.
3. **HTTP Serialization**: For the HTTP API (`hands_routes.py`), incoming JSON `capabilityToken` may be parsed as a dict or reconstructed into `CapabilityToken`. The bridge/executor must accept either `CapabilityToken` directly or a valid dict mapping.

---

## 4. Conclusion & Concrete Fix Strategy

### 4.1 Specification for `HandsExecutor` (`scp/hands/hands_executor.py`)

1. **Delete Line 111 and replace with Fail-Closed PEP Gate**:
   ```python
   # Guard 1: Zero-Trust PEP Fail-Closed if token is missing (FA-05)
   if capability_token is None:
       result = {
           "success": False,
           "action": action,
           "error": "CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)",
           "verification": {"passed": False},
       }
       self._audit("ACTION_BLOCKED_UNAUTHORIZED", result)
       return result

   # Guard 2: Scoped Subject-Resource Binding (INV-AUTH-02)
   expected_subject = f"hands:{action}"
   if getattr(capability_token, "subject", None) != expected_subject:
       result = {
           "success": False,
           "action": action,
           "error": f"CapabilityScopeMismatchError: Token subject '{getattr(capability_token, 'subject', None)}' does not match required action '{expected_subject}' (INV-AUTH-02)",
           "verification": {"passed": False},
       }
       self._audit("ACTION_BLOCKED_SCOPE_MISMATCH", result)
       return result
   ```

2. **Delete Line 326 and replace in `rollback`**:
   ```python
   # Guard 1: Zero-Trust PEP Fail-Closed if token is missing (FA-05)
   if capability_token is None:
       result = {
           "success": False,
           "action": "rollback",
           "error": "CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)",
           "verification": {"passed": False},
       }
       self._audit("ROLLBACK_BLOCKED_UNAUTHORIZED", result)
       return result

   # Guard 2: Scoped Subject-Resource Binding (INV-AUTH-02)
   expected_subject = "hands:rollback"
   if getattr(capability_token, "subject", None) != expected_subject:
       result = {
           "success": False,
           "action": "rollback",
           "error": f"CapabilityScopeMismatchError: Token subject '{getattr(capability_token, 'subject', None)}' does not match required action '{expected_subject}' (INV-AUTH-02)",
           "verification": {"passed": False},
       }
       self._audit("ROLLBACK_BLOCKED_SCOPE_MISMATCH", result)
       return result
   ```

3. **Update `_check_capability`**:
   ```python
   def _check_capability(self, definition: ActionDefinition, capability_level: int, approved: bool, capability_token: CapabilityToken | None) -> tuple[bool, str]:
       if not self.capability_authority.validate(capability_token, required_subject=f"hands:{definition.name}"):
           return False, "Capability token is revoked, stale, or scope mismatch"
       if self.controller.kill_switch_engaged():
           return False, "Kill switch is engaged"
       if capability_level < definition.capability_level:
           return False, f"Action requires capability >= {definition.capability_level}"
       if definition.requires_approval and not approved:
           return False, "Explicit approval required"
       return True, "Policy requirements satisfied"
   ```

4. **Update Pre-Dispatch Check (Line 132)**:
   ```python
   if not self.capability_authority.validate(capability_token, required_subject=expected_subject):
       result = {"success": False, "action": action, "error": "Capability revoked before dispatch", "verification": {"passed": False}}
       self._audit("ACTION_BLOCKED_CAPABILITY_REVOKED", result)
       return result
   ```

5. **Deprecate or Restrict `restore_capabilities`**:
   Ensure `restore_capabilities` logs audit warning or requires administrative caller proof rather than allowing arbitrary worker execution.

### 4.2 Specification for `CapabilityAuthority` (`scp/security/capability_epoch.py`)

Update `validate` to accept and enforce `required_subject`:
```python
def validate(self, token: CapabilityToken | None, required_subject: str | None = None) -> bool:
    if token is None:
        return False
    if not isinstance(token, CapabilityToken):
        # Support duck-typing if valid dataclass-like attributes exist
        if not (hasattr(token, "subject") and hasattr(token, "epoch")):
            return False
    if required_subject is not None:
        if str(getattr(token, "subject", "")) != str(required_subject):
            return False
    with self._lock:
        state = self._load()
        return not state["revoked"] and getattr(token, "epoch", -1) == state["epoch"]
```

### 4.3 Specification for `TaskKernelHandsBridge` (`scp/hands/task_kernel_bridge.py`)

1. **Update `execute`**:
   ```python
   async def execute(
       self,
       action: str,
       params: dict[str, Any] | None = None,
       capability_level: int = 0,
       approved: bool = False,
       dry_run: bool = False,
       request_key: str | None = None,
       capability_token: CapabilityToken | None = None,
   ) -> dict[str, Any]:
   ```
   Forward `capability_token=capability_token` to `self.executor.execute(...)` at lines 338 and 482.

2. **Update `rollback`**:
   ```python
   async def rollback(
       self,
       checkpoint_id: str,
       capability_level: int = 3,
       approved: bool = False,
       capability_token: CapabilityToken | None = None,
   ) -> dict[str, Any]:
       return await self.executor.rollback(
           checkpoint_id, capability_level, approved, capability_token=capability_token
       )
   ```

### 4.4 Specification for `HandsRoutes` (`scp/api/routes/hands_routes.py`)

1. Add `capabilityToken: dict[str, Any] | None = None` to `HandsActionRequest` and `HandsRollbackRequest`.
2. Convert dict to `CapabilityToken` if passed, and forward to `_active_bridge().execute` and `_active_bridge().rollback`.

### 4.5 Specification for `HandsPlanner` (`scp/hands/planner.py`)

In `_run_plan_locked`, when executing each step:
Obtain or format the step capability token and forward to `self.executor.execute(..., capability_token=step_token)`.

### 4.6 Specification for Tests (`tests/`)

In `tests/T09_golden_task/test_golden_a_agent_os.py` and `tests/T04_kernel/test_kernel_p1_regressions.py`:
Callers instantiate/access the authority, issue a valid token for `hands:pc.write_file`:
```python
token = executor.capability_authority.issue(f"hands:{action}")
result = asyncio.run(bridge.execute(..., capability_token=token))
```
This preserves full test strictness and ensures legitimate operations succeed genuinely without placebo.

---

## 5. Verification Method

To independently verify the investigation and subsequent implementation:
1. **Probe Verification**:
   Run: `python tools/probes/probe_hands_authority_flaws.py`
   - Baseline: Fails RED on invariant checks.
   - After patch: Must pass GREEN on all invariant checks.
2. **Full Test Suite Verification**:
   Run: `pytest tests/ -q`
   All tests must pass (exit code 0).
3. **Meta Audit Verification**:
   Run: `python tools/t00_meta_audit.py`
   Ensures zero FA-01 to FA-10 violations.
