# Handoff Report — Spec Miner 1 (spec_miner_invariants_1)
**Type**: Hard Handoff  
**Milestone**: Phase 1 (Target Manifest), Phase 3 (Causal Gap Analysis), Phase 5 (Evolution Path)  
**Target Subsystem**: `scp/hands/hands_executor.py` & Capability Authority  
**Author**: `spec_miner_invariants_1`  
**Timestamp**: 2026-09-07T00:54:50Z  

---

## 1. Observation

1. **Self-Granting in Execution**:
   In `scp/hands/hands_executor.py` lines 107-115:
   ```python
   async def execute(self, action: str, params: dict[str, Any] | None = None, capability_level: int = 0, approved: bool = False, dry_run: bool = False, capability_token: CapabilityToken | None = None) -> dict[str, Any]:
       params = params or {}
       started = time.perf_counter()
       try:
           capability_token = capability_token or self.capability_authority.issue(f"hands:{action}")
       except CapabilityRevokedError as exc:
   ```
   When `capability_token is None`, line 111 directly calls `self.capability_authority.issue(f"hands:{action}")`, manufacturing its own authorization token.

2. **Self-Granting in Rollback**:
   In `scp/hands/hands_executor.py` lines 324-328:
   ```python
   async def rollback(self, checkpoint_id: str, capability_level: int = 3, approved: bool = False, capability_token: CapabilityToken | None = None) -> dict[str, Any]:
       try:
           capability_token = capability_token or self.capability_authority.issue("hands:rollback")
   ```
   Line 326 similarly self-issues a capability token for rollback if none is provided.

3. **Colocation of Authority Administration in Executor**:
   In `scp/hands/hands_executor.py` lines 53 and 371-379:
   ```python
   self.capability_authority = capability_authority or CapabilityAuthority(self.data_dir / "capability_state.json")
   ...
   def revoke_capabilities(self, reason: str = "operator_revoke", actor: str = "operator") -> dict[str, Any]:
       return self.capability_authority.revoke(reason=reason, actor=actor)
   def restore_capabilities(self, reason: str = "operator_restore", actor: str = "operator") -> dict[str, Any]:
       return self.capability_authority.restore(reason=reason, actor=actor)
   ```
   The Executor instantiates a local writable authority by default and provides methods allowing the executor to restore its own authority.

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
   `validate` checks ONLY epoch and revocation flag. It completely ignores `token.subject` and parameters. In `HandsExecutor._check_capability` (line 69), `self.capability_authority.validate(capability_token)` is called without checking whether the token's subject matches `action` or the resource target.

5. **Protocol Disconnect at API & Kernel Bridge**:
   In `scp/api/routes/hands_routes.py` lines 38-44:
   `HandsActionRequest` does NOT declare any `capabilityToken` field.
   In `scp/hands/task_kernel_bridge.py` line 314 & 482:
   `TaskKernelHandsBridge.execute` does not receive or pass `capability_token`, invoking:
   `result = await self.executor.execute(action, params, capability_level, approved, False)`
   Every single production execution through the router and bridge relies on the self-granting fallback.

6. **Golden Test Execution Reality**:
   Running `pytest tests/T09_golden_task/test_golden_a_agent_os.py -q` returns `1 passed in 0.66s`. Line 44 calls `bridge.execute(action="pc.write_file", ...)`. The test passes despite not providing any capability token, demonstrating `PASS != TRUE`: the green status was achieved purely through self-granting authority.

---

## 2. Logic Chain

1. **Step 1 (FA-05 Definition)**: Rule FA-05 states: *"KHÔNG self-grant authority. Executor không tự issue token. Caller phải cung cấp token đã được cấp bởi authority riêng biệt."*
2. **Step 2 (Self-Granting Invariant)**: Invariant INV-AUTH-01 requires complete separation between the token issuer (PDP) and executor (PEP). The PEP must reject any request lacking an externally provided token.
3. **Step 3 (Mechanisms of Breach)**: Observation 1 and Observation 2 prove that `HandsExecutor` acts as both issuer and executor. When caller passes `capability_token=None`, `HandsExecutor` issues a token to itself.
4. **Step 4 (Validation Bypass)**: Because `validate()` only checks the epoch integer, and the token was just created with the current epoch, `validate()` always returns True.
5. **Step 5 (Structural Compulsion)**: Observation 5 shows that upstream callers cannot supply a token even if they wanted to, making self-granting the sole mechanism allowing the system to run.
6. **Step 6 (Scope Escalation)**: Observation 4 proves that any valid token (e.g. for `pc.status`) can be reused for `pc.write_file`, violating INV-AUTH-02.

---

## 3. Caveats

1. **Scope of Audit**: This audit investigated `HandsExecutor`, `TaskKernelHandsBridge`, `HandsPlanner`, `hands_routes.py`, `capability_epoch.py`, and `pc_controller.py`. Local PC actions and browser actions were mapped; remote multi-node executor distribution was not tested.
2. **Read-Only Constraint**: In strict compliance with the mandate *"TUYỆT ĐỐI KHÔNG SỬA CODE SẢN PHẨM Ở GIAI ĐOẠN NÀY"*, no product code changes were applied.
3. **Concurrency Under Windows**: HYP-01 (Windows file lock collisions on `capability_state.json`) was identified by static review of `os.replace` but not stressed under 100+ parallel threads.

---

## 4. Conclusion

- The suspicion raised in `ORIGINAL_REQUEST.md` is **100% CONFIRMED**.
- `HandsExecutor` suffers from a critical FA-05 violation: self-granting capability tokens in `execute()` and `rollback()`.
- Four mandatory invariants (INV-AUTH-01 to INV-AUTH-04) have been formalized in `target_manifest_and_gaps.md`.
- A 5-phase Evolution Path has been structured to decouple issuance from execution, upgrade the API/bridge protocol, enforce scoped validation, and eradicate self-granting fallbacks.

---

## 5. Verification Method

To independently verify these findings:
1. **Static Inspection**:
   - Run `grep_search` on `scp/hands/hands_executor.py` for `capability_authority.issue`. Observe lines 111 and 326.
   - Run `grep_search` on `scp/api/routes/hands_routes.py` for `class HandsActionRequest`. Observe absence of token.
2. **Direct Reproduction Command**:
   Execute the following in python to observe self-authorization:
   ```python
   import asyncio
   from pathlib import Path
   from scp.hands.hands_executor import HandsExecutor
   from scp.pc_control.pc_controller import PCController

   async def probe():
       tmp = Path("data/probe_test")
       tmp.mkdir(parents=True, exist_ok=True)
       exe = HandsExecutor(controller=PCController(working_dir=tmp))
       res = await exe.execute("pc.write_file", {"path": str(tmp / "test.txt"), "content": "pwn"}, capability_level=3, approved=True, capability_token=None)
       print("Self-granted success:", res["success"])
       assert res["success"] is True  # Falsifies Zero-Trust!
   asyncio.run(probe())
   ```
3. **Golden Test Inspection**:
   - Inspect `tests/T09_golden_task/test_golden_a_agent_os.py:44-52`. Confirm no capability token is passed, yet test passes due to line 111.
