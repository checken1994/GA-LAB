# Handoff Report — Explorer 1 (explorer_reality_scan_1)
**Type**: Hard Handoff  
**Milestone**: Phase 2 (Reality Scan)  
**Target Subsystem**: `scp/hands/hands_executor.py` & Capability Authority PEP  
**Author**: `explorer_reality_scan_1`  
**Timestamp**: 2026-09-07T00:56:45Z  

---

## 1. Observation

1. **Self-Granting in Execution Dispatch**:
   In `scp/hands/hands_executor.py` lines 107-115:
   ```python
   async def execute(self, action: str, params: dict[str, Any] | None = None, capability_level: int = 0, approved: bool = False, dry_run: bool = False, capability_token: CapabilityToken | None = None) -> dict[str, Any]:
       params = params or {}
       started = time.perf_counter()
       try:
           capability_token = capability_token or self.capability_authority.issue(f"hands:{action}")
       except CapabilityRevokedError as exc:
   ```
   Direct observation: when `capability_token` is `None`, line 111 mints a token using the executor's internal authority `self.capability_authority.issue(f"hands:{action}")`.

2. **Self-Granting in Rollback Dispatch**:
   In `scp/hands/hands_executor.py` lines 324-328:
   ```python
   async def rollback(self, checkpoint_id: str, capability_level: int = 3, approved: bool = False, capability_token: CapabilityToken | None = None) -> dict[str, Any]:
       try:
           capability_token = capability_token or self.capability_authority.issue("hands:rollback")
       except CapabilityRevokedError as exc:
           return {"success": False, "error": str(exc)}
   ```
   Direct observation: `HandsExecutor.rollback()` also self-mints a token on line 326 when `capability_token` is `None`.

3. **Colocation of Administrative Authority in Worker**:
   In `scp/hands/hands_executor.py` lines 41, 53, and 371-379:
   - Line 53: `self.capability_authority = capability_authority or CapabilityAuthority(self.data_dir / "capability_state.json")`
   - Lines 371-379: `HandsExecutor` exposes `revoke_capabilities()` and `restore_capabilities()` directly on the executor class, allowing the executor to reset `revoked: False` and advance its own epoch.

4. **Scope-Blind Token Validation**:
   In `scp/security/capability_epoch.py` lines 108-114:
   ```python
   def validate(self, token: CapabilityToken | None) -> bool:
       if token is None:
           return False
       with self._lock:
           state = self._load()
           return not state["revoked"] and token.epoch == state["epoch"]
   ```
   Direct observation: `validate()` only checks the integer `epoch` and boolean `revoked`. It does not verify `token.subject`, parameters, action, or target path.

5. **Upstream Caller Token Omission**:
   - `scp/api/routes/hands_routes.py:38-44` (`HandsActionRequest`): Pydantic schema contains `action, params, capabilityLevel, approved, dryRun`, but NO `capability_token` or `capabilityToken`.
   - `scp/hands/task_kernel_bridge.py:314, 482`: `TaskKernelHandsBridge.execute` signature does not accept `capability_token`, and calls `await self.executor.execute(action, params, capability_level, approved, False)` with `capability_token=None`.
   - `scp/hands/planner.py:401, 479`: `HandsPlanner.run_plan` accepts string `capability_token: str = ""`, but line 479 omits it when calling `self.executor.execute(...)`.

6. **Live Terminal Execution Probes (FA-09 Verification)**:
   - **Probe 1 (Self-issuance reproduction)**: Ran Python probe calling `exe.execute('pc.write_file', {'path': str(target), 'content': 'pwned_without_token'}, capability_level=3, approved=True, capability_token=None)`.
     *Raw Terminal Output*:
     ```text
     Execution success: True
     Action executed: pc.write_file
     Token epoch attached in result: 0
     File exists on disk: True
     File content: pwned_without_token
     ```
   - **Probe 2 (Cross-action scope bypass)**: Minted token for `hands:pc.status`, passed into `exe.execute('pc.write_file', ..., capability_token=token_for_status)`.
     *Raw Terminal Output*:
     ```text
     Token subject: hands:pc.status
     Executed with status token: True
     Target file exists: True
     ```
   - **Probe 3 (Quarantine self-restoration)**: Called `exe.revoke_capabilities()` followed by `exe.restore_capabilities()`.
     *Raw Terminal Output*:
     ```text
     Status after revoke: True
     Status after restore: False
     Executed after rogue restore: True
     Target file exists: True
     ```

---

## 2. Logic Chain

1. **Step 1 (Mandate Definition)**:
   Rule **FA-05** defines: *"KHÔNG self-grant authority. Executor không tự issue token. Caller phải cung cấp token đã được cấp bởi authority riêng biệt."*
2. **Step 2 (Self-Granting Invariant Breach)**:
   Observations 1 and 2 prove that `HandsExecutor` acts as its own token authority: when `capability_token` is omitted (`None`), lines 111 and 326 invoke `self.capability_authority.issue(...)` to create a valid token for itself.
3. **Step 3 (PEP Neutralization)**:
   Because the token is minted from `self.capability_authority` against the current state file, `_check_capability()` line 69 (`self.capability_authority.validate(capability_token)`) evaluates to `True`. The Policy Enforcement Point is neutralized.
4. **Step 4 (Scope Confusion)**:
   Observation 4 and Probe 2 prove that `CapabilityAuthority.validate` never verifies that `token.subject == f"hands:{action}"`. Therefore, any token granted for a benign read-only operation grants access to arbitrary mutating operations.
5. **Step 5 (Structural Dependency on Vulnerability)**:
   Observation 5 proves that upstream routes and the TaskKernel bridge cannot pass tokens. The system's current test suite (`test_golden_a_agent_os.py`, `test_kernel_p1_regressions.py`) only passes because of this self-granting backdoor. This confirms **DNA #22 (`PASS ≠ TRUE`)**.

---

## 3. Caveats

1. **Read-Only Investigation**: In compliance with the mission instructions, **zero product code was modified**. All probes were non-destructive scripts running in isolated temporary directories.
2. **Local vs Remote Distribution**: The audit inspected local execution on Windows/PowerShell and local browser targets. Distributed multi-worker scenarios where `CapabilityAuthority` is hosted on a remote server will require additional network token validation (e.g. HMAC/JWT tokens from `scp/core/capability_token.py`).
3. **Product Code Stability**: Removing the fallback at line 111 immediately will break tests that call `bridge.execute(...)` without a token. Upstream caller signatures must be upgraded simultaneously with the PEP fix.

---

## 4. Conclusion

- The suspicion of an FA-05 violation in `HandsExecutor` is **100% PROVEN**.
- `HandsExecutor` in `scp/hands/hands_executor.py` self-grants authority at line 111 (`execute`) and line 326 (`rollback`).
- The complete Line-by-Line Call Graph, Evidence Table, and live terminal reproduction logs are fully documented in `reality_scan_report.md`.
- Phase 2: Reality Scan is **COMPLETE** and ready for handoff to Phase 3 (Causal Gap Analysis) and Phase 4 (Probe Before Patch).

---

## 5. Verification Method

To independently reproduce and verify these findings:
1. **Static AST Verification**:
   Inspect `scp/hands/hands_executor.py` lines 111 and 326 using `view_file`. Verify the syntax `capability_token = capability_token or self.capability_authority.issue(...)`.
2. **Interactive Terminal Probe**:
   Execute the following command in PowerShell:
   ```powershell
   python -c "import asyncio, tempfile, shutil; from pathlib import Path; from scp.hands.hands_executor import HandsExecutor; from scp.pc_control.pc_controller import PCController; async def check(): tmp = Path(tempfile.mkdtemp()); exe = HandsExecutor(controller=PCController(working_dir=tmp)); f = tmp / 'verify.txt'; res = await exe.execute('pc.write_file', {'path': str(f), 'content': 'verified'}, capability_level=3, approved=True, capability_token=None); print('SUCCESS:', res['success']); print('FILE_WRITTEN:', f.exists()); shutil.rmtree(tmp); asyncio.run(check())"
   ```
   Expected output confirming vulnerability:
   ```text
   SUCCESS: True
   FILE_WRITTEN: True
   ```
3. **Invalidation Condition**:
   If `exe.execute(..., capability_token=None)` raises a fail-closed exception (e.g. `PermissionDeniedError`) and refuses to execute, this finding is invalidated. Under current codebase, it unconditionally succeeds.
