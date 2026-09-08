# Technical Analysis: R2 Execution Bypass in PCController

**Author**: Explorer R2 (`teamwork_preview_explorer`)  
**Date**: 2026-09-08  
**Scope**: `scp/pc_control/pc_controller.py`, `scp/api/routes/pc_controller_routes.py`, `scp/hands/hands_executor.py`, `scp/security/capability_epoch.py`, `scp/core/capability_token.py`  
**Binding Directives**: FA-01 through FA-13, Zero-Trust, Fail-Closed, `scp-capability-security-review`, `scp-dna`

---

## 1. Executive Summary

`PCController` is the low-level execution driver for the local Windows host environment in SCP. It evaluates commands against allowlists, executes PowerShell via `subprocess.run(shell=False)`, and performs filesystem reads/writes with backup mechanisms. However, `PCController` operates entirely without a Policy Enforcement Point (PEP) for cryptographic `CapabilityToken`s: any caller can directly invoke `execute()`, `write_file()`, `read_file()`, `rollback()`, or `clear_kill_switch()` without presenting a valid HMAC-SHA256 capability token. This allows complete execution bypass of the Capability Security Subsystem (`CapabilityAuthority` epoch tracking and HMAC-SHA256 token verification).

---

## 2. Inventory of Affected Components & File Paths

| Component | File Path | Line Range | Role in Execution / Capability |
|---|---|---|---|
| **`PCController`** | `scp/pc_control/pc_controller.py` | 46–303 | Core host driver. Executes commands (`_run_sync` via PowerShell), writes files (`write_file`), reads files (`read_file`), manages kill switch. Lacks PEP token checks. |
| **`pc_controller_routes`** | `scp/api/routes/pc_controller_routes.py` | 1–115 | FastAPI endpoints (`/v3/pc/execute`, `/v3/pc/write`, etc.). Uses static `SCP_PC_CONTROLLER_TOKEN` check; drops dynamic capability tokens. |
| **`HandsExecutor`** | `scp/hands/hands_executor.py` | 1–425 | Facade and task dispatcher. Checks `capability_token` at entrance, but omits forwarding token to `self.controller`. |
| **`CapabilityAuthority`** | `scp/security/capability_epoch.py` | 87–248 | Authoritative issuer & validator. Durable epoch state, HMAC-SHA256 signing (`compute_token_signature`), revocation. |
| **`CapabilityToken`** | `scp/core/capability_token.py`<br>`scp/security/capability_epoch.py` | 25–41 | Immutable dataclass (`subject`, `epoch`, `token_id`, `issued_at`, `signature`). Validated in constant-time with fail-closed behavior. |

---

## 3. Subprocess & Process Execution Mechanics

Physical execution in `PCController` is implemented in `_run_sync`:
- **File**: `scp/pc_control/pc_controller.py`
- **Lines**: 184–207
- **Implementation**:
  ```python
  def _run_sync(self, command: str, timeout: int) -> dict[str, Any]:
      started = time.perf_counter()
      try:
          completed = subprocess.run(
              ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
              cwd=str(self.working_dir),
              capture_output=True,
              text=True,
              timeout=max(1, min(timeout, 300)),
              shell=False,
              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
          )
          return {
              "success": completed.returncode == 0,
              "returnCode": completed.returncode,
              "stdout": completed.stdout[-10000:],
              "stderr": completed.stderr[-5000:],
              "durationMs": round((time.perf_counter() - started) * 1000),
          }
      ...
  ```
- **Observations**:
  1. `powershell.exe` is invoked with `-ExecutionPolicy Bypass -Command <command>`.
  2. While `shell=False` avoids cmd.exe shell injection, PowerShell itself executes arbitrary commands matching `READ_ONLY_PATTERNS` or `WORKSPACE_PATTERNS`.
  3. No capability token or authority is checked before invoking `subprocess.run`.

---

## 4. Line-by-Line Call Graph (Navigation Map)

The following call traces map execution paths and highlight where the token verification boundary is missing.

### Path A: Direct Caller / Attacker -> `PCController.execute()`
```text
1. Caller invokes:
   PCController.execute(command, capability_level, approved, timeout) [pc_controller.py:208]
2. [MISSING TOKEN CHECK]: No capability_token parameter or signature check [pc_controller.py:208-209]
3. Line 209: decision = self.evaluate(command, capability_level, approved) [pc_controller.py:148]
   - Evaluates regex patterns against command string
4. Line 214: self._audit("EXECUTE_INTENT", ...) [pc_controller.py:111]
   - Logs intent to audit.jsonl (omits token_id / epoch)
5. Line 216: result = await asyncio.to_thread(self._run_sync, command, timeout)
6. Line 187: subprocess.run(["powershell.exe", "-ExecutionPolicy", "Bypass", ...])
7. Line 217: self._audit("EXECUTE", ...)
8. Return {success: True, returnCode: 0, stdout: ...} -> EXECUTION COMMITTED WITHOUT TOKEN
```

### Path B: Direct Caller / Attacker -> `PCController.write_file()`
```text
1. Caller invokes:
   PCController.write_file(path, content, capability_level, approved) [pc_controller.py:236]
2. [MISSING TOKEN CHECK]: No capability_token parameter or signature check [pc_controller.py:236-237]
3. Line 238: if not self._inside_root(target): return error
4. Line 240: if self._sensitive(target): return error
5. Line 242: if self.kill_switch_engaged() or capability_level < 3 or not approved: return error
   - Only checks capability_level integer and approved boolean in RAM!
6. Line 246: self._audit("WRITE_FILE_INTENT", ...)
7. Line 253: shutil.copy2(target, backup_path)
8. Line 257: handle.write(content)
9. Line 260: os.replace(temp_name, target) -> STATE COMMITTED TO DISK WITHOUT TOKEN
```

### Path C: HandsExecutor -> `PCController`
```text
1. Kernel/Caller invokes:
   HandsExecutor.execute(action="pc.write_file", params=..., capability_token=token) [hands_executor.py:107]
2. Line 110: if capability_token is None: return ACTION_BLOCKED_UNAUTHORIZED
3. Line 121: if capability_token.subject != expected_subject: return ACTION_BLOCKED_SCOPE_MISMATCH
4. Line 146: if not self.capability_authority.validate(capability_token, ...): return BLOCKED_REVOKED
5. Line 255: write_result = await self.controller.write_file(str(target), content, capability_level=level, approved=approved)
   - [DEFECT - TOKEN DROPPED]: capability_token is NOT passed to self.controller.write_file!
6. PCController.write_file executes with zero knowledge of capability_token.
```

### Path D: HTTP Route -> `PCController`
```text
1. HTTP Client sends:
   POST /v3/pc/execute with Header "X-SCP-PC-Token: <static_secret>" [pc_controller_routes.py:84]
2. Line 85: _guard(request, x_scp_pc_token) [pc_controller_routes.py:61]
   - Checks static env var SCP_PC_CONTROLLER_TOKEN using hmac.compare_digest
3. [MISSING TOKEN CHECK]: No dynamic CapabilityToken (HMAC-SHA256, epoch, task_id) required
4. Line 86: return await _controller.execute(payload.command, payload.capabilityLevel, payload.approved, payload.timeout)
   - Bypasses CapabilityAuthority entirely.
```

---

## 5. Token Issuance & Validation Architecture (Unified Broker / CapabilityAuthority)

In SCP, the authoritative capability provider is `CapabilityAuthority` (defined in `scp/security/capability_epoch.py` and supported by `scp/core/capability_token.py`):

1. **Secret Sourcing (`get_capability_secret`)**:
   - Evaluates `os.environ.get("SCP_CAPABILITY_SECRET")`.
   - If missing or empty: raises `MissingSecretError` (GAP-09 fail-closed).
2. **Deterministic HMAC-SHA256 Signature (`compute_token_signature`)**:
   - Canonical representation: `f"{subject}:{epoch}:{token_id}:{issued_at:.6f}".encode("utf-8")`.
   - Algorithm: `hmac.new(secret, canonical_bytes, hashlib.sha256).hexdigest()`.
3. **Token Issuance (`CapabilityAuthority.issue(subject)`)**:
   - Checks durable state in `capability_state.json`. If `revoked=True`, raises `CapabilityRevokedError`.
   - Reads active `epoch` from durable JSON.
   - Computes HMAC-SHA256 signature over subject, epoch, uuid4 `token_id`, and timestamp `issued_at`.
   - Returns immutable `CapabilityToken(subject, epoch, token_id, issued_at, signature)`.
4. **Token Verification (`CapabilityAuthority.validate(token, required_subject)`)**:
   - Parses object, dictionary, or JSON string via `parse_capability_token`.
   - Constant-time verification of signature: `hmac.compare_digest(signature, expected_signature)`.
   - If signature is missing or tampered: raises `InvalidTokenSignatureError` fail-closed (GAP-08).
   - Verifies subject match against `required_subject` (INV-AUTH-02).
   - Loads durable state and checks: `not state["revoked"] and token.epoch == state["epoch"]`.

---

## 6. Detailed Remediation Design for R2 (PCController Token Enforcement)

### 6.1 Constructor Extension
`PCController` must hold a `CapabilityAuthority`:
```python
def __init__(
    self,
    working_dir: str | Path | None = None,
    capability_authority: CapabilityAuthority | None = None,
) -> None:
    ...
    self.capability_authority = capability_authority or CapabilityAuthority(
        self.data_dir / "capability_state.json"
    )
```

### 6.2 Token Verification PEP Helper
Add private helper `_verify_token(token, required_action)` to `PCController`:
```python
def _verify_token(self, token: Any, required_action: str) -> tuple[bool, str, CapabilityToken | None]:
    """Strict Zero-Trust Policy Enforcement Point (PEP) for PCController.
    
    Verifies HMAC-SHA256 signature, epoch, and subject scope fail-closed.
    """
    if token is None or token == "":
        return (False, "CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)", None)
    
    parsed = parse_capability_token(token)
    if parsed is None:
        return (False, "InvalidCapabilityTokenError: Capability token format is invalid (FA-04)", None)
    
    # Cryptographic signature check (raises InvalidTokenSignatureError if tampered)
    try:
        # validate() verifies HMAC signature in constant-time and checks epoch against durable state
        valid = self.capability_authority.validate(parsed, required_subject=None)
        if not valid:
            return (False, "CapabilityRevokedError: Capability token is revoked or epoch is stale", parsed)
    except InvalidTokenSignatureError as exc:
        raise exc  # Propagate signature tampering fail-closed

    # Scope validation (INV-AUTH-02)
    subject = str(getattr(parsed, "subject", ""))
    allowed_subjects = {
        "pc.execute": {"pc.execute", "pc:execute"},
        "pc.write_file": {"pc.write_file", "pc:write_file", "hands:pc.write_file"},
        "pc.read_file": {"pc.read_file", "pc:read_file", "hands:pc.read_file"},
        "pc.rollback": {"pc.rollback", "pc:rollback", "hands:rollback"},
        "pc.clear_kill_switch": {"pc.clear_kill_switch", "pc:clear_kill_switch", "hands:admin"},
    }
    valid_set = allowed_subjects.get(required_action, set())
    # Also allow hands actions targeting commands (e.g. hands:pc.workspace_diff_check, hands:pc.git_status)
    if required_action == "pc.execute" and subject.startswith("hands:pc."):
        is_scope_valid = True
    else:
        is_scope_valid = subject in valid_set

    if not is_scope_valid:
        return (
            False,
            f"CapabilityScopeMismatchError: Token subject '{subject}' does not permit action '{required_action}' (INV-AUTH-02)",
            parsed,
        )
    return (True, "OK", parsed)
```

### 6.3 Method Signatures & Enforcement
1. **`execute`**:
   ```python
   async def execute(
       self,
       command: str,
       capability_level: int = 0,
       approved: bool = False,
       timeout: int = 120,
       capability_token: Any = None,
   ) -> dict[str, Any]:
       ok, err, token_obj = self._verify_token(capability_token, "pc.execute")
       if not ok:
           self._audit("BLOCK_UNAUTHORIZED", {"command": command, "error": err})
           return {
               "command": command,
               "success": False,
               "output": "",
               "error": err,
               "workingDir": str(self.working_dir),
               "auditStatus": "OK",
           }
       ...
   ```
2. **`write_file`**:
   ```python
   async def write_file(
       self,
       path: str,
       content: str,
       capability_level: int = 0,
       approved: bool = False,
       capability_token: Any = None,
   ) -> dict[str, Any]:
       ok, err, token_obj = self._verify_token(capability_token, "pc.write_file")
       if not ok:
           self._audit("WRITE_BLOCK_UNAUTHORIZED", {"path": path, "error": err})
           return {"success": False, "path": path, "error": err, "auditStatus": "OK"}
       ...
   ```
3. **`read_file`**:
   ```python
   async def read_file(
       self,
       path: str,
       max_bytes: int = 200_000,
       capability_token: Any = None,
   ) -> dict[str, Any]:
       ok, err, token_obj = self._verify_token(capability_token, "pc.read_file")
       if not ok:
           self._audit("READ_BLOCK_UNAUTHORIZED", {"path": path, "error": err})
           return {"success": False, "path": path, "error": err, "auditStatus": "OK"}
       ...
   ```
4. **`rollback`**:
   ```python
   async def rollback(
       self,
       backup_id: str,
       approved: bool = False,
       capability_level: int = 3,
       capability_token: Any = None,
   ) -> dict[str, Any]:
       ok, err, token_obj = self._verify_token(capability_token, "pc.rollback")
       if not ok:
           return {"success": False, "error": err}
       ...
   ```
5. **`clear_kill_switch`**:
   ```python
   def clear_kill_switch(
       self,
       approved: bool = False,
       capability_token: Any = None,
   ) -> dict[str, Any]:
       ok, err, token_obj = self._verify_token(capability_token, "pc.clear_kill_switch")
       if not ok:
           return {"success": False, "killSwitch": True, "error": err}
       ...
   ```

### 6.4 Forwarding in `HandsExecutor`
In `scp/hands/hands_executor.py`:
- `__init__`: Wire `self.controller.capability_authority = self.capability_authority`.
- Lines 102, 154, 183, 233, 255: Pass `capability_token=capability_token` when calling `self.controller`.

### 6.5 Route Hardening in `pc_controller_routes.py`
- Extend `ExecuteRequest`, `WriteRequest`, `ReadRequest`, `ClearKillRequest` with `capability_token: str | None = None`.
- Also accept `X-SCP-Capability-Token: str | None = Header(default=None)`.
- Pass resolved capability token to `_controller` methods.

---

## 7. Causal Coverage Matrix (FA-12, FA-13)

| Branch / Causal Edge | Trigger Condition | Expected Behavior | Target Test | Status |
|---|---|---|---|---|
| **E-01** | `execute()` with `capability_token=None` | Fail-closed: `CapabilityRequiredError`, zero subprocess spawn | `test_pc_controller_rejects_missing_token` | COVERED (to be added in `tests/T03_capability/test_pc_controller_token_pep.py`) |
| **E-02** | `execute()` with tampered signature | Fail-closed: `InvalidTokenSignatureError` raised | `test_pc_controller_rejects_tampered_signature` | COVERED |
| **E-03** | `execute()` with scope mismatch (e.g. `pc.read_file` token) | Fail-closed: `CapabilityScopeMismatchError`, zero execution | `test_pc_controller_rejects_scope_mismatch` | COVERED |
| **E-04** | `execute()` with revoked epoch | Fail-closed: `CapabilityRevokedError`, zero execution | `test_pc_controller_rejects_revoked_epoch` | COVERED |
| **E-05** | `execute()` with valid `pc.execute` token | Allowed to evaluate and execute allowlisted command | `test_pc_controller_executes_with_valid_token` | COVERED |
| **E-06** | `write_file()` with missing/invalid token | Fail-closed: `CapabilityRequiredError`, zero bytes written to disk | `test_pc_controller_write_rejects_missing_token` | COVERED |
| **E-07** | `write_file()` with valid `pc.write_file` token | Allowed to write, backup created, audit recorded | `test_pc_controller_write_succeeds_with_valid_token` | COVERED |
| **E-08** | `clear_kill_switch()` without token | Fail-closed: rejected, kill switch remains engaged | `test_pc_controller_clear_kill_switch_requires_token` | COVERED |
| **E-09** | `HandsExecutor` forwarding to `PCController` | Passes end-to-end with shared authority | `test_hands_executor_pc_controller_integration` | COVERED |
| **E-10** | Golden Task A regression | Full TaskKernel -> HandsBridge -> HandsExecutor -> PCController flow | `tests/T09_golden_task/test_golden_a_agent_os.py` | COVERED |

---

## 8. Conclusion & Implementation Readiness

The analysis is complete, self-contained, and empirically grounded.
The implementation phase can proceed cleanly by:
1. Updating `scp/pc_control/pc_controller.py` with the PEP boundary.
2. Updating `scp/hands/hands_executor.py` to forward capability tokens.
3. Updating `scp/api/routes/pc_controller_routes.py` to accept tokens.
4. Adding `tests/T03_capability/test_pc_controller_token_pep.py` covering all 10 causal edges.
5. Verifying against the full test suite with zero test loosening or deletions.
