# HANDOFF REPORT: GAP-07 HANDSEXECUTOR SELF-GRANTING AUTHORITY ERADICATION

**Author**: Worker 2 (Core Implementer)  
**Target Workspace**: `c:\Users\check\Downloads\scp`  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\orchestrator_5\worker_2`  
**Date**: 2026-09-07T14:10:00+07:00  
**Parent Agent**: `parent` (`967399d1-d666-4dce-899b-4c2468b6dd91`)  
**Governing Invariants**: INV-AUTH-01 (Disjoint Authority Boundary), INV-AUTH-02 (Scoped Subject Binding), INV-AUTH-03 (Pre-Dispatch Fail-Closed PEP Gate), FA-01 through FA-10  
**Handoff Type**: Hard (Task complete)  

---

## 1. Observation

### 1.1 Direct Code Changes Across Product Files
The following modifications were implemented across the 5 production files and 3 test files in our exclusive write ownership:

1. **`scp/security/capability_epoch.py`**:
   - Added `to_dict(self) -> dict[str, Any]` method to `CapabilityToken` dataclass (lines 25–31).
   - Implemented `parse_capability_token(token: Any) -> CapabilityToken | None` (lines 34–73) providing fail-closed parsing across `CapabilityToken` instances, JSON strings, dicts (handling both `snake_case` and `camelCase`), and returning `None` for invalid or empty inputs.
   - Updated `CapabilityAuthority.validate(self, token: CapabilityToken | None, required_subject: str | None = None) -> bool` (lines 158–169):
     - Validates `token is not None`.
     - Validates duck-typing attributes `hasattr(token, "subject") and hasattr(token, "epoch")`.
     - Enforces `str(getattr(token, "subject", "")) == str(required_subject)` when `required_subject is not None`.
     - Under `self._lock`: verifies `not state["revoked"] and getattr(token, "epoch", -1) == state["epoch"]`.

2. **`scp/hands/hands_executor.py`**:
   - Permanently eradicated fallback `issue()` calls in `execute()` (former line 111) and `rollback()` (former line 326).
   - In `execute()` (lines 110–129):
     - Precondition 1: If `capability_token is None`: immediately fails closed returning `{"success": False, "action": action, "error": "CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)", "verification": {"passed": False}}` and audits `ACTION_BLOCKED_UNAUTHORIZED`.
     - Precondition 2: `expected_subject = f"hands:{action}"`. If `getattr(capability_token, "subject", None) != expected_subject`: immediately fails closed returning `{"success": False, "action": action, "error": f"CapabilityScopeMismatchError: Token subject '{getattr(capability_token, 'subject', None)}' does not match required action '{expected_subject}' (INV-AUTH-02)", "verification": {"passed": False}}` and audits `ACTION_BLOCKED_SCOPE_MISMATCH`.
   - In `_check_capability()` (lines 68–77): delegates to `self.capability_authority.validate(capability_token, required_subject=f"hands:{definition.name}")`.
   - In pre-dispatch check (lines 146–149): delegates to `self.capability_authority.validate(capability_token, required_subject=expected_subject)`.
   - In `rollback()` (lines 340–366):
     - Requires `capability_token is not None` or fails closed with `CapabilityRequiredError` and audits `ROLLBACK_BLOCKED_UNAUTHORIZED`.
     - Requires `getattr(capability_token, "subject", None) == "hands:rollback"` or fails closed with `CapabilityScopeMismatchError` and audits `ROLLBACK_BLOCKED_SCOPE_MISMATCH`.
     - Validates with `self.capability_authority.validate(capability_token, required_subject=expected_subject)` or fails closed with `Capability token is revoked or stale`.

3. **`scp/hands/task_kernel_bridge.py`**:
   - In `execute()` (lines 281–297, 427): accepts `capability_token: CapabilityToken | Any = None`, deserializes via `parse_capability_token`, and forwards `capability_token=token` to `self.executor.execute(...)` for both non-mutating/dry-run and mutating execution.
   - In `rollback()` (lines 80–95): accepts `capability_token: CapabilityToken | Any = None`, deserializes via `parse_capability_token`, and forwards `capability_token=token` to `self.executor.rollback(...)`.
   - In TaskKernel checkpointing (line 406): records `token.epoch if token else self._capability_epoch(self.executor)` into the task checkpoint.
   - In `_policy_blocked_before_dispatch()` (lines 135–154): added policy rejection markers: `"capabilityrequired"`, `"capability required"`, `"capabilityscopemismatch"`, `"scope mismatch"`, `"caller must provide an authorized capability token"`, `"unauthorized"`. This prevents PEP rejections from falsely cascading into TaskKernel `UNKNOWN` status.

4. **`scp/api/routes/hands_routes.py`**:
   - Added `capabilityToken: Any = Field(default=None, description="Zero-Trust capability token")` to `HandsActionRequest`, `HandsRollbackRequest`, and `PlannerRollbackRequest`.
   - In `hands_execute`, `hands_rollback`, and `planner_rollback`: parses `capabilityToken` via `parse_capability_token` and forwards downstream to `_active_bridge().execute()`, `_active_bridge().rollback()`, and `_planner.rollback_plan()`.

5. **`scp/hands/planner.py`**:
   - In `run_plan` and `_run_plan_locked`: accepts `capability_token: Any = ""`. Resolves per-step token from step definition (`capabilityToken`/`capability_token`), dictionary mapping by `stepId` or `action`, or plan token fallback. Deserializes with `parse_capability_token` and passes `capability_token=parsed_step_token` to `self.executor.execute(...)`.
   - In `_run_dag_step`: resolves step token and forwards `capability_token=parsed_step_token` to `self.executor.execute(...)`.
   - In `rollback_plan`: accepts `capability_token: Any = None`, deserializes via `parse_capability_token`, and forwards to `self.executor.rollback(..., capability_token=parsed_token)`.

### 1.2 Test Suite Updates & Invariant Test Addition
1. **`tests/T04_kernel/test_kernel_p1_regressions.py`**:
   - Updated helper `_bridge_with_executor(tmp_path)` to initialize `CapabilityAuthority` with local state path and return `(bridge, workspace, cap_auth)`.
   - In `test_bridge_duplicate_request_returns_replayed_response`: issues authorized token `hands:pc.write_file` from `cap_auth` and supplies `capability_token=token` to both initial dispatch and duplicate replay dispatch. Preserves all 9 assertions.
   - In `test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch`: updated `slow_execute` signature to accept `capability_token=None, **kwargs` and forward it. Issues authorized token `hands:pc.write_file` and supplies `capability_token=token`. Preserves all 7 assertions.
2. **`tests/T09_golden_task/test_golden_a_agent_os.py`**:
   - In `test_golden_a_agent_os_real_execution_flow`: instantiates `CapabilityAuthority`, issues authorized token `hands:pc.write_file`, and passes `capability_token=token` to both initial execution and replay idempotency execution. Preserves all 14 assertions.
3. **`tests/T03_capability/test_hands_authority_pep.py` (New Invariant Test Suite)**:
   - `test_hands_executor_rejects_missing_token_fail_closed`: Verifies that `execute(action="pc.write_file", capability_token=None)` returns `success=False`, `error` containing `CapabilityRequiredError`, and does NOT create the target file on disk.
   - `test_hands_executor_rejects_scope_mismatch_fail_closed`: Verifies that passing a read token (`hands:pc.status`) to `pc.write_file` returns `success=False`, `error` containing `CapabilityScopeMismatchError`, and does NOT create the target file on disk.
   - `test_hands_executor_rejects_revoked_epoch`: Verifies that revoking authority invalidates subsequent write executions fail-closed with error containing `revoked` or `stale`.
   - `test_hands_executor_rollback_requires_token`: Verifies that `rollback()` without token fails with `CapabilityRequiredError`, with wrong token fails with `CapabilityScopeMismatchError`, and with genuine `hands:rollback` token succeeds and rolls back state.

### 1.3 Empirical Test Execution Results (Verbatim Terminal Output)

1. **Targeted PEP Invariant Suite**:
   Command: `pytest tests/T03_capability/test_hands_authority_pep.py -v`
   ```text
   tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rejects_missing_token_fail_closed PASSED [ 25%]
   tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rejects_scope_mismatch_fail_closed PASSED [ 50%]
   tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rejects_revoked_epoch PASSED [ 75%]
   tests/T03_capability/test_hands_authority_pep.py::test_hands_executor_rollback_requires_token PASSED [100%]
   ============================== 4 passed in 0.92s ==============================
   ```

2. **Affected Regression Suite (T04 & T09)**:
   Command: `pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py -v`
   ```text
   tests/T04_kernel/test_kernel_p1_regressions.py::test_bridge_duplicate_request_returns_replayed_response PASSED [ 16%]
   tests/T04_kernel/test_kernel_p1_regressions.py::test_orphan_sweep_keeps_fresh_lease_and_reconciles_stale_one PASSED [ 33%]
   tests/T04_kernel/test_kernel_p1_regressions.py::test_checkpoint_event_does_not_poison_rebuild_projection PASSED [ 50%]
   tests/T04_kernel/test_kernel_p1_regressions.py::test_checkpoint_still_rejects_invalid_state PASSED [ 66%]
   tests/T04_kernel/test_kernel_p1_regressions.py::test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch PASSED [ 83%]
   tests/T09_golden_task/test_golden_a_agent_os.py::test_golden_a_agent_os_real_execution_flow PASSED [100%]
   ============================== 6 passed in 3.26s ==============================
   ```

3. **Full Capability Suite (T03)**:
   Command: `pytest tests/T03_capability/ -v`
   ```text
   ============================= 47 passed in 1.69s ==============================
   ```

4. **Full Workspace Pytest Suite**:
   Command: `pytest tests/ -q`
   ```text
   445 passed in 108.46s (0:01:48)
   Exit code: 0
   ```

5. **Integrity Meta-Audit Authority**:
   Command: `python tools/t00_meta_audit.py`
   ```text
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

1. **Step 1 (Root Cause & Anti-Pattern)**: From Observation 1.1, the previous baseline had `capability_token = capability_token or self.capability_authority.issue(...)` in `HandsExecutor.execute` (line 111) and `HandsExecutor.rollback` (line 326). This violated Rule FA-05 ("Tử huyệt bạo chúa") because the executor (PEP) acted as applicant, minting authority, and execution engine simultaneously.
2. **Step 2 (Scope Confusion)**: Furthermore, `CapabilityAuthority.validate` checked only `token.epoch == state["epoch"]` and `not state["revoked"]`, ignoring `token.subject`. Consequently, a read-only token (`hands:pc.status`) was accepted for high-risk write operations (`pc.write_file`), violating Invariant INV-AUTH-02.
3. **Step 3 (Propagation Pipeline)**: Callers across HTTP API routes (`hands_routes.py`), TaskKernel bridge (`task_kernel_bridge.py`), and planner (`planner.py`) dropped or omitted `capability_token`. Removing line 111 without updating callers would fail closed all legitimate workflows.
4. **Step 4 (Implementation Coherence)**:
   - Added universal `parse_capability_token` handling all serialization formats fail-closed.
   - Enforced strict subject matching in `CapabilityAuthority.validate` and PEP entry points (`hands:{action}` and `hands:rollback`).
   - Threaded tokens across the entire pipeline.
   - Updated `_policy_blocked_before_dispatch` to recognize authorization failure strings so PEP denials transition kernel tasks to `FAILED` rather than corrupting into `UNKNOWN`.
5. **Step 5 (Strictness & Zero-Regression Proof)**:
   - Updated callers in `tests/T04_kernel/` and `tests/T09_golden_task/` to issue authoritative tokens from `CapabilityAuthority`.
   - Preserved all existing assertions (FA-01 compliance).
   - Added 4 new PEP invariant tests in `tests/T03_capability/test_hands_authority_pep.py`.
   - Full test suite passed with 445 tests (441 baseline + 4 new tests, zero failures, zero skipped, exit code 0).
   - Meta-audit passed with 0 new regressions.

---

## 3. Caveats

1. **Probe Script Semantic Distinction**:
   `tools/probes/probe_hands_authority_flaws.py` was authored during Phase 4 as an exploit-reproduction probe that tests whether `HandsExecutor` is vulnerable by verifying that it writes files without a token. Now that `HandsExecutor` is guarded and strictly rejects executions without tokens, running that specific reproduction probe reports `[NOT REPRODUCED]`, confirming that the vulnerability has been eradicated. The durable, regression-safe test suite guarding this behavior is `tests/T03_capability/test_hands_authority_pep.py`, which passes 100% GREEN.
2. **Unrelated Spec Changes**:
   Working tree changes in `spec/scp_future_target_manifest.yaml` and `spec/scp_future_cause_effect_matrix_v4_0_2.overlay.json` (updating skill count to 14) originated prior to this worker's turn. In accordance with "preserve unrelated user changes", these files were left intact.
3. **No Caveats on Execution Integrity**:
   All 8 files under exclusive write ownership were updated cleanly, compiled, verified against terminal executions, and audited with zero regressions.

---

## 4. Conclusion

GAP-07 (HandsExecutor Self-Granting Authority Eradication) is 100% resolved and verified:
1. Self-granting authority (`issue()` fallback) is completely eliminated from `HandsExecutor`.
2. PEP fail-closed enforcement requires a valid caller-provided token for both `execute()` and `rollback()`.
3. Scoped subject-to-action binding is strictly verified against `hands:{action}` and `hands:rollback`.
4. The caller pipeline (`hands_routes.py`, `task_kernel_bridge.py`, `planner.py`) cleanly propagates capability tokens without parameter dropping.
5. All 445 test cases pass cleanly, and T00 Meta-Audit reports 0 integrity regressions.

---

## 5. Verification Method

To independently reproduce and verify this completion:

```bash
# 1. Verify PEP Invariant Tests (4 tests pass in ~1s)
pytest tests/T03_capability/test_hands_authority_pep.py -v

# 2. Verify Kernel & Golden Task Regressions (6 tests pass in ~3s)
pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py -v

# 3. Verify Full Capability Test Suite (47 tests pass in ~2s)
pytest tests/T03_capability/ -v

# 4. Verify Full Test Suite (445 tests pass, exit code 0)
pytest tests/ -q

# 5. Verify Meta-Audit Integrity Authority (0 new regressions, exit code 0)
python tools/t00_meta_audit.py
```

### Invalidation Conditions
- Any call to `HandsExecutor.execute()` or `HandsExecutor.rollback()` succeeds when `capability_token is None`.
- Any call to `HandsExecutor.execute("pc.write_file", capability_token=status_token)` succeeds (scope confusion).
- Any assertion in `test_kernel_p1_regressions.py` or `test_golden_a_agent_os.py` is weakened, skipped, or deleted.
- Total passing test count falls below 445.
- `python tools/t00_meta_audit.py` returns a non-zero exit code.
