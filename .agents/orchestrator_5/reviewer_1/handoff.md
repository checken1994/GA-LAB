# HANDOFF REPORT: ZERO-TRUST AUTHORITY & PEP REVIEW (GAP-07)

**Reviewer**: Reviewer 1 (Zero-Trust Authority & PEP Reviewer / Adversarial Critic)  
**Target Workspace**: `c:\Users\check\Downloads\scp`  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\orchestrator_5\reviewer_1`  
**Date**: 2026-09-07T14:21:00+07:00  
**Parent Agent**: `parent` (`967399d1-d666-4dce-899b-4c2468b6dd91`)  
**Verdict**: **APPROVE**  
**Governing Invariants**: INV-AUTH-01 (Disjoint Authority Boundary), INV-AUTH-02 (Scoped Subject Binding), INV-AUTH-03 (Fail-Closed Pre-Dispatch PEP Gate), FA-01 through FA-10  
**Handoff Type**: Hard (Review complete)

---

## 1. Observation

### 1.1 Source Code Verification (AST & Logic Inspection)

1. **`scp/hands/hands_executor.py`**:
   - **Zero Self-Granting `issue()` Calls**: Verified via full-text and AST search across `scp/hands/` that `issue()` is 100% eradicated (0 occurrences).
   - **`execute()` PEP Fail-Closed Gate** (lines 110–129):
     ```python
     if capability_token is None:
         result = {
             "success": False,
             "action": action,
             "error": "CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)",
             "verification": {"passed": False},
         }
         self._audit("ACTION_BLOCKED_UNAUTHORIZED", result)
         return result

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
     - Verified: Triggers before action lookup, before `_check_capability()`, before dry-run evaluation, and before any driver (`PCController`, `WebNavigator`, or `ManagedProcessManager`) is called. Zero disk, process, or network side-effects occur.
   - **`rollback()` PEP Fail-Closed Gate** (lines 341–365):
     - Line 341: Rejects `capability_token is None` with `CapabilityRequiredError` and audits `ROLLBACK_BLOCKED_UNAUTHORIZED`.
     - Line 351: Enforces `getattr(capability_token, "subject", None) == "hands:rollback"` or rejects with `CapabilityScopeMismatchError` and audits `ROLLBACK_BLOCKED_SCOPE_MISMATCH`.
     - Line 362: Re-validates against `self.capability_authority.validate(capability_token, required_subject="hands:rollback")`.
     - Verified: Occurs before reading `checkpoints.jsonl` and before executing `shutil.copy2` or `unlink`.

2. **`scp/security/capability_epoch.py`**:
   - **`CapabilityToken` serialization** (lines 25–31): Implements `to_dict()`.
   - **`parse_capability_token(token: Any) -> CapabilityToken | None`** (lines 34–73):
     - Safely parses `CapabilityToken`, JSON strings, and dictionaries (handling both `snake_case` and `camelCase` keys).
     - Fails closed returning `None` for: `None`, empty string, non-JSON strings, JSON non-dicts (lists, primitives, null, bool), dicts missing `epoch`, non-integer `epoch`, or malformed types.
   - **`CapabilityAuthority.validate(self, token: CapabilityToken | None, required_subject: str | None = None) -> bool`** (lines 158–169):
     - Verifies `token is not None`.
     - Verifies duck-typing attributes `hasattr(token, "subject") and hasattr(token, "epoch")`.
     - If `required_subject is not None`: enforces exact match `str(getattr(token, "subject", "")) == str(required_subject)`.
     - Under `self._lock`: verifies `not state["revoked"] and getattr(token, "epoch", -1) == state["epoch"]`.

3. **Protocol Threading Across Component Boundaries**:
   - **`scp/hands/task_kernel_bridge.py`**:
     - `execute()` (lines 281–297, 427): Accepts `capability_token`, deserializes via `parse_capability_token`, and forwards to `self.executor.execute(..., capability_token=token)` for both read/dry-run and mutating execution.
     - `rollback()` (lines 80–95): Accepts `capability_token`, deserializes, and forwards to `self.executor.rollback(..., capability_token=token)`.
     - `_policy_blocked_before_dispatch()` (lines 135–154): Includes markers for capability/scope/unauthorized errors to cleanly transition blocked tasks in TaskKernel without corrupting state into `UNKNOWN`.
   - **`scp/api/routes/hands_routes.py`**:
     - `HandsActionRequest` and `HandsRollbackRequest` accept `capabilityToken: Any = None`.
     - `hands_execute`, `hands_rollback`, and `planner_rollback` parse `capabilityToken` and pass it downstream.
   - **`scp/hands/planner.py`**:
     - `run_plan`, `_run_plan_locked`, `_run_dag_step`, and `rollback_plan` forward parsed step/plan tokens to `executor.execute` and `executor.rollback`.

### 1.2 Test Execution & Empirical Terminal Verification

1. **Targeted PEP Invariant Test Suite**:
   Command: `pytest tests/T03_capability/test_hands_authority_pep.py -v`
   Result:
   ```text
   tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rejects_missing_token_fail_closed PASSED [ 25%]
   tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rejects_scope_mismatch_fail_closed PASSED [ 50%]
   tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rejects_revoked_epoch PASSED [ 75%]
   tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rollback_requires_token PASSED [100%]
   ============================== 4 passed in 0.86s ==============================
   ```

2. **Full Workspace Pytest Suite**:
   Command: `pytest tests/ --basetemp=reports/pytest-basetemp-clean -q`
   Result:
   ```text
   ........................................................................ [ 16%]
   ........................................................................ [ 32%]
   ........................................................................ [ 48%]
   ........................................................................ [ 64%]
   ........................................................................ [ 80%]
   ........................................................................ [ 97%]
   .............                                                            [100%]
   445 passed in 131.28s (0:02:11)
   Exit code: 0
   ```

3. **Test-Integrity Regression Authority**:
   Command: `python tools/t00_meta_audit.py`
   Result:
   ```text
   [T00 Meta-Audit] Starting Test-Integrity Regression Authority...
   [T00 Meta-Audit] Trusted Base: origin/main
   [T00 Meta-Audit] Collecting baseline pytest nodeids (origin/main)...
   [T00 Meta-Audit] Collecting candidate pytest nodeids...
   [T00 Meta-Audit] All integrity checks passed (0 new regressions).
   Exit code: 0
   ```

4. **Git Test Assertions & Diffs**:
   Command: `git diff tests/`
   Verified: No assertions in `test_kernel_p1_regressions.py` or `test_golden_a_agent_os.py` were weakened, bypassed, skipped, or removed. Callers were updated strictly to acquire and provide genuine tokens from `CapabilityAuthority`.

---

## 2. Logic Chain

1. **Premise 1 (Self-Granting Elimination)**: From Observation 1.1, the previous lines 111 and 326 of `HandsExecutor` that invoked `self.capability_authority.issue(...)` when `capability_token is None` have been completely removed. No alternative code paths generate tokens within `HandsExecutor`. Thus, Invariant **INV-AUTH-01** (Disjoint Authority Boundary) and Rule **FA-05** are satisfied.
2. **Premise 2 (Fail-Closed Deny-by-Default)**: In both `execute()` and `rollback()`, the very first branch checks if `capability_token is None`. If true, an unauthorized result with `success=False` and `verification: {"passed": False}` is returned immediately. Observation 1.2 Sub-test 1 and Sub-test 4 confirm that zero files are written to disk when `capability_token is None`.
3. **Premise 3 (Scoped Subject Validation)**: Both `HandsExecutor` and `CapabilityAuthority.validate` explicitly enforce that `token.subject == f"hands:{action}"` (or `"hands:rollback"`). Observation 1.2 Sub-test 2 confirms that presenting a read token (`hands:pc.status`) when invoking `pc.write_file` is rejected fail-closed with `CapabilityScopeMismatchError`, satisfying Invariant **INV-AUTH-02**.
4. **Premise 4 (Token Parsing Robustness)**: `parse_capability_token` guards against all malformed payloads (JSON syntax errors, non-dict JSON, missing/invalid epoch) by returning `None`, which then triggers the fail-closed missing token gate.
5. **Premise 5 (Regression & Integrity Freedom)**: The full test suite passed with 445 tests (exit code 0), and `tools/t00_meta_audit.py` confirmed 0 new test integrity regressions, satisfying rules **FA-01**, **FA-02**, and **FA-03**.

---

## 3. Caveats

1. **Pytest Basetemp Directory Contention**:
   When running the entire test suite via `pytest tests/ -q` using the default `--basetemp=reports/pytest-basetemp` defined in `pytest.ini`, test `tests/T09_golden_task/test_golden_b_epistemic_loop.py` can intermittently encounter `FileNotFoundError` due to Windows NTFS filesystem handle locking or stale artifacts left by earlier tests. When executed with a dedicated or clean `--basetemp` (e.g. `reports/pytest-basetemp-clean`), all 4 tests in `test_golden_b_epistemic_loop.py` and all 445 tests in the workspace pass 100% GREEN. This is an environment/harness artifact, not a defect in `HandsExecutor` or PEP code.
2. **In-Memory Duck-Typing vs Cryptographic Signatures**:
   `CapabilityToken` currently validates subject and epoch match against the disk-backed state file `capability_state.json`. It does not yet incorporate HMAC cryptographic signatures like `scp/core/capability_token.py`. For in-process callers, this relies on Python object boundaries; for external HTTP API callers, all inputs must deserialize through `parse_capability_token` and match the disk epoch. Full token unification remains an open roadmap item as documented in the Delta Audit report.
3. **`restore_capabilities()` on Executor**:
   `HandsExecutor` still retains administrative delegation methods `revoke_capabilities()` and `restore_capabilities()`. However, because `restore()` increments the epoch (`epoch + 1`) and `HandsExecutor` has no `issue()` method, calling `restore_capabilities()` cannot be used by the executor to self-grant execution permissions.

---

## 4. Conclusion

The implementation of GAP-07 in `scp/security/capability_epoch.py`, `scp/hands/hands_executor.py`, and supporting caller boundaries strictly satisfies all acceptance criteria, invariants INV-AUTH-01, INV-AUTH-02, and INV-AUTH-03, and project rules FA-01 through FA-10.

**Final Verdict**: **APPROVE**

---

## 5. Verification Method

To independently verify this verdict:

```powershell
# 1. Run the PEP invariant test suite
pytest tests/T03_capability/test_hands_authority_pep.py -v

# 2. Run the full workspace test suite with a clean basetemp
pytest tests/ --basetemp=reports/pytest-basetemp-clean -q

# 3. Run the Meta-Audit integrity authority
python tools/t00_meta_audit.py
```

### Invalidation Conditions
- Any call to `HandsExecutor.execute()` or `HandsExecutor.rollback()` succeeds when `capability_token=None`.
- Any call to `HandsExecutor.execute("pc.write_file", capability_token=status_token)` succeeds or mutates disk.
- Any regression in the 445-test suite or any failure in `tools/t00_meta_audit.py`.
