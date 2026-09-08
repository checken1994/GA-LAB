# Handoff Report: R2 Execution Bypass (PCController) Survey & Investigation

**Author**: Explorer R2 (`teamwork_preview_explorer`)  
**Date**: 2026-09-08  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\explorer_r2`  
**Target Milestone**: R2_Execution_Bypass_Investigation  
**Parent Conversation ID**: `ddbf9e21-2e43-4b5e-a888-4fe21e00292d`

---

## 1. Observation

### Observation 1: PCController Execution Primitives Lack CapabilityToken Check
- **File**: `c:\Users\check\Downloads\scp\scp\pc_control\pc_controller.py`
- **Lines 184–207 (`_run_sync`)**:
  Spawns `powershell.exe` with `-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command <command>`.
- **Lines 208–221 (`execute`)**:
  ```python
  async def execute(self, command: str, capability_level: int = 0, approved: bool = False, timeout: int = 120) -> dict[str, Any]:
      decision = self.evaluate(command, capability_level, approved)
      base = {"command": command, "decision": asdict(decision), "workingDir": str(self.working_dir)}
      if not decision.allowed:
          self._audit("BLOCK", base)
          return {**base, "success": False, "output": "", "error": decision.reason}
      if not self._audit("EXECUTE_INTENT", {**base, "timeout": timeout}):
          return {**base, "success": False, "output": "", "error": "Audit storage unavailable; action blocked", "auditStatus": "DB_WRITE_FAILED"}
      result = await asyncio.to_thread(self._run_sync, command, timeout)
      post_audit_ok = self._audit("EXECUTE", {**base, **result})
      ...
  ```
  `capability_token` is completely absent from function parameters and execution checks.
- **Lines 236–275 (`write_file`)**:
  `write_file(self, path: str, content: str, capability_level: int = 0, approved: bool = False)` commits file replacement to host disk via `shutil.copy2` and `os.replace` without checking any `CapabilityToken`.
- **Lines 222–235 (`read_file`)**:
  `read_file(self, path: str, max_bytes: int = 200_000)` reads host files without checking any `CapabilityToken`.
- **Lines 293–303 (`clear_kill_switch`)**:
  `clear_kill_switch(self, approved: bool = False)` only checks boolean `approved` in RAM.

### Observation 2: Unified Broker / CapabilityAuthority & CapabilityToken HMAC-SHA256
- **Files**:
  - `scp/security/capability_epoch.py` (lines 87–248: `CapabilityAuthority`, lines 25–41: `CapabilityToken`)
  - `scp/core/capability_token.py` (lines 21–38: `compute_token_signature`, `verify_token_signature`, lines 40–54: `get_capability_secret`)
- **HMAC Implementation**:
  - Secret: sourced from `SCP_CAPABILITY_SECRET` (GAP-09 fail-closed via `MissingSecretError`).
  - Canonical format: `f"{subject}:{epoch}:{token_id}:{issued_at:.6f}".encode("utf-8")`.
  - Signature algorithm: `hmac.new(secret, canonical, hashlib.sha256).hexdigest()`.
  - Constant-time verification: `hmac.compare_digest(str(signature).strip(), expected)` raising `InvalidTokenSignatureError` fail-closed if tampered or unsigned (GAP-08).

### Observation 3: HandsExecutor Drops Capability Tokens When Calling PCController
- **File**: `scp/hands/hands_executor.py`
- **Lines 101–105 (`_pc_command`)**:
  `result = await self.controller.execute(command, capability_level=0, approved=False, timeout=30)` -> `capability_token` is NOT passed.
- **Line 255 (`pc.write_file`)**:
  `write_result = await self.controller.write_file(str(target), str(params.get("content", "")), capability_level=capability_level, approved=approved)` -> `capability_token` is NOT passed.
- **Line 154 (`pc.read_file`)**:
  `result = await self.controller.read_file(...)` -> `capability_token` is NOT passed.

### Observation 4: HTTP API Route Uses Static Token Bypass
- **File**: `scp/api/routes/pc_controller_routes.py`
- **Lines 61–66 (`_guard`)**:
  Only validates against static environment variable `SCP_PC_CONTROLLER_TOKEN` via `hmac.compare_digest`. No dynamic CapabilityToken (HMAC-SHA256, epoch, subject) is required or validated.

### Observation 5: Empirical Exploit Reproduction (FA-09)
- **Script**: `.agents/explorer_r2/probe_r2_execution_bypass.py`
- **Execution Command**: `python .agents/explorer_r2/probe_r2_execution_bypass.py`
- **Output**:
  ```text
  [PROBE R2] Testing PCController.execute() without CapabilityToken...
  [PROBE R2] execute result: success=True, returnCode=0
  [PROBE R2] stdout: minh\check
  [PROBE R2] -> VULNERABILITY CONFIRMED: Subprocess command executed without CapabilityToken verification!
  [PROBE R2] Testing PCController.write_file() without CapabilityToken...
  [PROBE R2] write_file result: success=True, backupId=None
  [PROBE R2] -> VULNERABILITY CONFIRMED: Host filesystem mutated without CapabilityToken verification!
  ```

---

## 2. Logic Chain

1. **Premise 1 (Zero-Trust PEP invariant)**: Per `scp-capability-security-review` § Quy trình review (rule 8), Policy Enforcement Points (PEPs) must reside immediately in front of drivers touching real hardware/OS. Relying solely on upstream callers (like `HandsExecutor`) violates Defense-in-Depth.
2. **Premise 2 (Direct accessibility)**: `PCController` can be imported and instantiated directly by any internal subsystem, or called via `pc_controller_routes.py` over HTTP.
3. **Deduction from Observation 1**: Because `PCController.execute()` and `PCController.write_file()` contain no token check, any caller with a reference to `PCController` can execute commands via `subprocess.run` (PowerShell) and mutate host files without obtaining a `CapabilityToken`.
4. **Empirical Confirmation (Observation 5)**: Calling `execute("whoami")` and `write_file(...)` directly with no token succeeded with `returnCode=0` and wrote files to disk, proving the execution bypass is real and exploitable in physical execution.
5. **Deduction from Observation 3 & 4 (Peripheral Gaps)**: Remediating `PCController` by adding a token check requires also updating `HandsExecutor` (which currently drops tokens before calling `self.controller`) and `pc_controller_routes.py` (which currently checks only static `SCP_PC_CONTROLLER_TOKEN`).

---

## 3. Caveats

1. **Read-Only Scope**: Per the explorer role, no production files in `scp/` or `tests/` were modified during this investigation.
2. **Windows Platform Dependency**: Subprocess execution in `PCController` explicitly targets `powershell.exe` on Windows. Linux/macOS environments would behave differently if PowerShell is absent, but the logic flaw (lack of token check before command dispatch) is platform-agnostic.
3. **No Other Unaudited Drivers**: Web control (`WebNavigator`) and process manager (`ManagedProcessManager`) were checked for references, but were not subjected to full penetration probing as they were outside R2's scope.

---

## 4. Conclusion

- **Assessment**: Vulnerability R2 is **CONFIRMED, SEVERE, AND ACTIONABLE**.
- **Root Cause**: `PCController` was implemented as a simple allowlist evaluator without integrating with `CapabilityAuthority`. It lacks a Policy Enforcement Point (PEP) for cryptographic HMAC-SHA256 capability tokens.
- **Actionable Remediation Strategy**:
  1. Inject `CapabilityAuthority` into `PCController.__init__`.
  2. Add `_verify_token(token, required_action)` to `PCController` enforcing presence, valid HMAC-SHA256 signature, matching epoch, and matching subject scope fail-closed.
  3. Update `PCController.execute`, `write_file`, `read_file`, `rollback`, and `clear_kill_switch` to require `capability_token`.
  4. Update `HandsExecutor` to forward `capability_token` across all calls to `self.controller`.
  5. Update `pc_controller_routes.py` to accept `capability_token` via header or payload.
  6. Add unit and regression tests in `tests/T03_capability/test_pc_controller_token_pep.py`.

---

## 5. Verification Method

To independently reproduce and verify this investigation:
1. Run the empirical exploit probe:
   ```powershell
   python .agents/explorer_r2/probe_r2_execution_bypass.py
   ```
   **Expected**: Exits with code 0 and logs `VULNERABILITY CONFIRMED` for both `execute` and `write_file`.
2. Inspect `scp/pc_control/pc_controller.py`:
   - Verify that `execute` (line 208) has no `capability_token` parameter.
   - Verify that `write_file` (line 236) has no `capability_token` parameter.
3. Inspect `scp/hands/hands_executor.py`:
   - Verify that line 102 calls `self.controller.execute(...)` without `capability_token`.
   - Verify that line 255 calls `self.controller.write_file(...)` without `capability_token`.
4. Run existing capability and kernel test suites:
   ```powershell
   python -m pytest tests/T03_capability/test_capability_token_hmac_signing.py -q
   python -m pytest tests/T03_capability/test_hands_authority_pep.py -q
   python -m pytest tests/T04_kernel/test_kernel_p1_regressions.py -q
   ```
   **Expected**: All currently passing tests continue to pass.
5. Invalidation Condition:
   If `PCController.execute` is shown to reject calls without an authorized HMAC-SHA256 token signed by `CapabilityAuthority`, this conclusion is invalidated.
