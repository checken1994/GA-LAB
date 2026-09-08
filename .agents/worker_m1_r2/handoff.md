# Handoff Report: R2 Execution Bypass Remediation in PCController

**Author**: Worker M1 (`teamwork_preview_worker`)  
**Date**: 2026-09-08  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\worker_m1_r2`  
**Target Milestone**: M1: R2 Execution Bypass Remediation  
**Parent Conversation ID**: `ddbf9e21-2e43-4b5e-a888-4fe21e00292d`  
**Binding Directives**: FA-01 through FA-13, Zero-Trust, Fail-Closed, `scp-capability-security-review`, `scp-dna`

---

## 1. Observation

### Observation 1: Baseline Vulnerability State
- Prior to remediation, `PCController` (`scp/pc_control/pc_controller.py`) lacked any Policy Enforcement Point (PEP) validating cryptographic `CapabilityToken`s.
- Subprocess command execution (`_run_sync` via PowerShell) and file mutations (`write_file`) executed without requiring a valid capability token.
- Running Explorer R2's exploit probe `.agents/explorer_r2/probe_r2_execution_bypass.py` previously exited with 0, confirming that unauthenticated callers could execute commands and mutate the filesystem.

### Observation 2: Code Modifications Applied
The following minimal, targeted modifications were applied across the 4 owned files:

1. **`scp/pc_control/pc_controller.py`**:
   - Injected `CapabilityAuthority` into constructor `__init__(self, working_dir=None, capability_authority=None)`.
   - Defined fail-closed `_verify_token(self, token: Any, required_action: str = "pc.execute") -> CapabilityToken`:
     - Checks token presence; if missing/empty, audits `TOKEN_REJECTED` and raises `PermissionError("CapabilityRequiredError: Action '{required_action}' requires an authorized capability token (FA-05)")`.
     - Parses token format; if unparseable, raises `InvalidTokenSignatureError("InvalidCapabilityTokenError: Capability token format is invalid (FA-04)")`.
     - Validates constant-time HMAC-SHA256 signature and active epoch via `CapabilityAuthority.validate()`. If signature is tampered or unsigned, `InvalidTokenSignatureError` is raised fail-closed. If epoch is stale or revoked, `PermissionError("CapabilityRevokedError: Capability token is revoked or epoch is stale")` is raised.
     - Strictly enforces subject scope against allowed action mappings (`pc.execute`, `pc.write_file`, `pc.read_file`, `pc.rollback`, `pc.clear_kill_switch`, plus `hands:pc.*` commands).
   - Guarded `execute()`, `read_file()`, `write_file()`, `rollback()`, and `clear_kill_switch()` to strictly call `_verify_token()` BEFORE any subprocess dispatch or disk mutation.
   - Enhanced audit ledger records (`EXECUTE_INTENT`, `EXECUTE`, `WRITE_FILE_INTENT`, `WRITE_FILE`) to commit `tokenId` and `epoch`.

2. **`scp/hands/hands_executor.py`**:
   - In `__init__`, ensured `self.controller.capability_authority` is synchronized with `self.capability_authority`.
   - In `_pc_command()`, added `capability_token: CapabilityToken | None = None` parameter and forwarded `capability_token=capability_token` to `self.controller.execute()`.
   - In `execute()`, added extraction of `capability_token` from `params.get("capability_token") or params.get("capabilityToken")` if omitted from kwargs.
   - In `execute()`, forwarded `capability_token=capability_token` when dispatching `pc.read_file`, `pc.process_snapshot`, `pc.service_snapshot`, `pc.workspace_diff_check`, `pc.git_status`, and `pc.write_file`.

3. **`scp/api/routes/pc_controller_routes.py`**:
   - Added `capability_token: str | None = None` and `capabilityToken: str | None = None` to `PlanRequest`, `ExecuteRequest`, `ReadRequest`, `WriteRequest`, and `ClearKillRequest`.
   - Added header dependency `x_scp_capability_token: str | None = Header(default=None)` across all execution endpoints.
   - Forwarded resolved `token` to `_controller` methods.
   - Wrapped endpoint dispatches in `try ... except (PermissionError, InvalidTokenSignatureError)` mapping security denials to `HTTPException(status_code=403, detail=str(exc))`.

4. **`tests/T03_capability/test_pc_controller_token_pep.py`**:
   - Created comprehensive test suite containing 15 unit and regression tests.

### Observation 3: Exploit Probe Blocked (FA-09 & FA-12)
- Re-running `.agents/explorer_r2/probe_r2_execution_bypass.py` now exits with non-zero exit code (1) and verbatim traceback:
  ```text
  PermissionError: CapabilityRequiredError: Action 'pc.execute' requires an authorized capability token (FA-05)
  ```
  The bypass exploit is completely neutralized.

### Observation 4: Test Suite Execution Results (FA-03)
- Command: `python -m pytest tests/T03_capability/test_pc_controller_token_pep.py -v`
  Output: `15 passed in 1.59s`
- Command: `python -m pytest tests/T03_capability/ -v`
  Output: `100 passed in 2.70s`
- Command: `python -m pytest tests/T03_capability/test_xff_guard_contract.py -v`
  Output: `5 passed in 0.95s`

---

## 2. Logic Chain

1. **Premise 1 (Policy Enforcement Point at Driver Boundary)**: Per Zero-Trust and `scp-capability-security-review`, drivers that execute OS processes or mutate the physical filesystem (`PCController`) must enforce authorization immediately before calling system APIs, not solely rely on upstream callers.
2. **Premise 2 (Durable Cryptographic Authentication)**: A capability token must carry an HMAC-SHA256 signature verified against `SCP_CAPABILITY_SECRET`, a matching authority epoch, and a scoped subject matching the intended action (`INV-AUTH-02`).
3. **Deduction from Observation 2**:
   - `PCController._verify_token` enforces that every call to `execute`, `write_file`, `read_file`, `rollback`, and `clear_kill_switch` presents an authentic token.
   - Any missing token, forged signature, mismatched scope, or stale epoch raises `PermissionError` or `InvalidTokenSignatureError` before any subprocess is spawned or file is touched.
4. **Deduction from Observation 3 & 4**:
   - The exploit probe that previously achieved execution bypass is now blocked fail-closed with `PermissionError`.
   - All 15 unit and regression tests in `test_pc_controller_token_pep.py` and all 100 tests in `tests/T03_capability/` pass with zero failures and zero test loosening.

---

## 3. Causal Coverage Matrix (FA-12, FA-13)

| ID | Causal Branch / Edge | Trigger Condition | Expected Result | Covering Test | Verdict |
|---|---|---|---|---|---|
| C-01 | Missing token on `execute` | `execute(command, capability_token=None)` | Raises `PermissionError` fail-closed, no process spawned | `test_pc_controller_execute_rejects_missing_token` | COVERED / PASS |
| C-02 | Tampered signature on `execute` | `execute(command, capability_token=tampered)` | Raises `InvalidTokenSignatureError` fail-closed | `test_pc_controller_execute_rejects_tampered_signature` | COVERED / PASS |
| C-03 | Scope mismatch on `execute` | `execute(command, capability_token=read_token)` | Raises `PermissionError` fail-closed | `test_pc_controller_execute_rejects_scope_mismatch` | COVERED / PASS |
| C-04 | Revoked epoch on `execute` | `execute(command, capability_token=revoked_token)` | Raises `PermissionError` fail-closed | `test_pc_controller_execute_rejects_revoked_epoch` | COVERED / PASS |
| C-05 | Valid token on `execute` | `execute(command, capability_token=valid_token)` | Executes command, returnCode=0, audit recorded with tokenId | `test_pc_controller_execute_succeeds_with_valid_token` | COVERED / PASS |
| C-06 | Missing token on `write_file` | `write_file(path, content, capability_token=None)` | Raises `PermissionError` fail-closed, zero bytes on disk | `test_pc_controller_write_rejects_missing_token` | COVERED / PASS |
| C-07 | Tampered token on `write_file` | `write_file(path, content, capability_token=tampered)` | Raises `InvalidTokenSignatureError` fail-closed, zero bytes on disk | `test_pc_controller_write_rejects_tampered_token` | COVERED / PASS |
| C-08 | Valid token on `write_file` | `write_file(path, content, capability_token=valid_token)` | Writes content to disk, backup created, audit recorded | `test_pc_controller_write_succeeds_with_valid_token` | COVERED / PASS |
| C-09 | Missing token on `read_file` | `read_file(path, capability_token=None)` | Raises `PermissionError` fail-closed | `test_pc_controller_read_rejects_missing_token` | COVERED / PASS |
| C-10 | Valid token on `read_file` | `read_file(path, capability_token=valid_token)` | Returns content from disk, audit recorded | `test_pc_controller_read_succeeds_with_valid_token` | COVERED / PASS |
| C-11 | Missing token on `clear_kill_switch` | `clear_kill_switch(approved=True, capability_token=None)` | Raises `PermissionError` fail-closed, kill switch remains engaged | `test_pc_controller_clear_kill_switch_requires_token` | COVERED / PASS |
| C-12 | Valid token on `clear_kill_switch` | `clear_kill_switch(approved=True, capability_token=valid_token)` | Clears kill switch, audit recorded | `test_pc_controller_clear_kill_switch_requires_token` | COVERED / PASS |
| C-13 | `HandsExecutor` token forwarding | `HandsExecutor.execute(action="pc.write_file", capability_token=token)` | Passes token to controller, file written to disk | `test_hands_executor_forwards_token_to_controller` | COVERED / PASS |
| C-14 | `HandsExecutor` token extraction from params | `HandsExecutor.execute(action="pc.write_file", params={"capability_token": ...})` | Extracts and forwards token, file written | `test_hands_executor_extracts_token_from_params` | COVERED / PASS |
| C-15 | API route missing capability token | POST `/v3/pc/execute` with missing capability token | Returns HTTP 403 Forbidden | `test_pc_controller_routes_rejects_missing_capability_token` | COVERED / PASS |
| C-16 | API route valid capability token | POST `/v3/pc/execute` with valid header capability token | Returns HTTP 200 OK | `test_pc_controller_routes_succeeds_with_valid_capability_token` | COVERED / PASS |

---

## 4. Caveats

- **Scope Boundary**: As Worker M1, modifications were strictly confined to the 4 assigned files. Subsystems undergoing concurrent remediation by Worker M2 (R3 VerifierReceipt in TaskKernel) and Worker M3 (R6 AutoFix shadow rollback) were not touched.
- **PowerShell Host**: PowerShell is invoked as the underlying shell on Windows. The token PEP boundary is evaluated in Python immediately prior to `subprocess.run`, making the PEP check platform-agnostic.
- **No Test Loosening**: Zero tests were modified, deleted, or skipped. All assertions remain strict and fail-closed.

---

## 5. Conclusion

Vulnerability **R2: Execution Bypass in PCController** has been completely and genuinely remediated:
1. `PCController` is now a verified Policy Enforcement Point (PEP).
2. Any execution without a genuine HMAC-SHA256 capability token fails closed immediately.
3. `HandsExecutor` propagates capability tokens without loss.
4. HTTP routes require and validate dynamic capability tokens.
5. All 16 causal branches have passing tests in `tests/T03_capability/test_pc_controller_token_pep.py`.

---

## 6. Verification Method

To independently verify this remediation:
1. Run the R2 PEP test suite:
   ```powershell
   python -m pytest tests/T03_capability/test_pc_controller_token_pep.py -v
   ```
   **Expected**: 15 passed in ~1.6s.
2. Run the full T03 capability test suite:
   ```powershell
   python -m pytest tests/T03_capability/ -q
   ```
   **Expected**: 100 passed in ~2.7s.
3. Run the exploit probe to verify it is blocked:
   ```powershell
   python .agents/explorer_r2/probe_r2_execution_bypass.py
   ```
   **Expected**: Fails with `PermissionError: CapabilityRequiredError: Action 'pc.execute' requires an authorized capability token (FA-05)`.
4. Run empirical verification script:
   ```powershell
   python .agents/worker_m1_r2/probe_r2_remediation_verified.py
   ```
   **Expected**: Exits with code 0 and logs `FA-12 EMPIRICAL VERIFICATION COMPLETE: ALL GATES PASS`.
5. Invalidation Condition:
   If `PCController.execute("whoami")` succeeds without presenting a valid `CapabilityToken`, this verdict is invalidated.
