## 2026-09-07T07:00:28Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You are Worker 2: Core Implementer for GAP-07 (HandsExecutor Self-Granting Authority Eradication).
Your working directory is: c:\Users\check\Downloads\scp\.agents\orchestrator_5\worker_2
Workspace root: c:\Users\check\Downloads\scp
Original request is recorded at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (read this file first!).
Scope document: c:\Users\check\Downloads\scp\.agents\orchestrator_5\SCOPE.md

You have exclusive write ownership of these files:
- scp/security/capability_epoch.py
- scp/hands/hands_executor.py
- scp/hands/task_kernel_bridge.py
- scp/api/routes/hands_routes.py
- scp/hands/planner.py
- tests/T04_kernel/test_kernel_p1_regressions.py
- tests/T09_golden_task/test_golden_a_agent_os.py
- tests/T03_capability/test_hands_authority_pep.py

Read the detailed handoff reports from the 3 Explorers before modifying any files:
- c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_1\handoff.md (HandsExecutor & Authority Core)
- c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_2\handoff.md (Caller Protocols & Bridges)
- c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_3\handoff.md (Test Suite Impact & Migration Map)

Implementation Instructions:
1. `scp/security/capability_epoch.py`:
   - Add `parse_capability_token(token: Any) -> CapabilityToken | None` supporting `CapabilityToken`, dict (both snake_case and camelCase), JSON str, or returning None fail-closed. Add `to_dict()` on `CapabilityToken`.
   - Update `CapabilityAuthority.validate(self, token: CapabilityToken | None, required_subject: str | None = None) -> bool`:
     - If `token is None` -> `return False`.
     - Duck-typing check: must have `subject` and `epoch`.
     - If `required_subject is not None`: enforce `str(getattr(token, "subject", "")) == str(required_subject)`.
     - Under `self._lock`: check `not state["revoked"] and getattr(token, "epoch", -1) == state["epoch"]`.

2. `scp/hands/hands_executor.py`:
   - Permanently delete fallback `issue()` at line 111 (in `execute`) and line 326 (in `rollback`).
   - In `execute()`:
     - If `capability_token is None`: fail closed immediately returning `{"success": False, "action": action, "error": "CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)", "verification": {"passed": False}}`. Audit as `ACTION_BLOCKED_UNAUTHORIZED`.
     - Subject check: `expected_subject = f"hands:{action}"`. If `getattr(capability_token, "subject", None) != expected_subject`: fail closed returning `{"success": False, "action": action, "error": f"CapabilityScopeMismatchError: Token subject '{getattr(capability_token, 'subject', None)}' does not match required action '{expected_subject}' (INV-AUTH-02)", "verification": {"passed": False}}`. Audit as `ACTION_BLOCKED_SCOPE_MISMATCH`.
   - In `_check_capability()`: call `self.capability_authority.validate(capability_token, required_subject=f"hands:{definition.name}")`.
   - In line 132 pre-dispatch check: call `self.capability_authority.validate(capability_token, required_subject=expected_subject)`.
   - In `rollback()`: If `capability_token is None`: fail closed with `CapabilityRequiredError`. Check `subject == "hands:rollback"`.

3. `scp/hands/task_kernel_bridge.py`:
   - In `execute()`: accept `capability_token: CapabilityToken | Any = None`. Parse with `parse_capability_token`. Pass `capability_token=token` to `self.executor.execute(...)` for non-mutating/dry-run and mutating execution.
   - In `rollback()`: accept `capability_token: CapabilityToken | Any = None`. Parse with `parse_capability_token`. Pass to `self.executor.rollback(..., capability_token=token)`.
   - In `_policy_blocked_before_dispatch()`: add markers `"capabilityrequired"`, `"capability required"`, `"capabilityscopemismatch"`, `"scope mismatch"`, `"caller must provide an authorized capability token"`, `"unauthorized"` so policy rejections fail cleanly into `FAILED` rather than `UNKNOWN`.

4. `scp/api/routes/hands_routes.py`:
   - In `HandsActionRequest`, `HandsRollbackRequest`, and `PlannerRollbackRequest`: add `capabilityToken: Any = Field(default=None, description="Zero-Trust capability token")`.
   - In `hands_execute`, `hands_rollback`, and `planner_rollback`: parse token and pass to bridge / planner.

5. `scp/hands/planner.py`:
   - In `run_plan` and `_run_plan_locked`: accept `capability_token: Any = ""`. Resolve step token and pass `capability_token=parsed_step_token` to `self.executor.execute(...)`.
   - In `_run_dag_step` and `rollback_plan`: thread capability token to executor.

6. `tests/`:
   - Update `tests/T04_kernel/test_kernel_p1_regressions.py`:
     - Update `_bridge_with_executor` to initialize `CapabilityAuthority` and return it.
     - In `test_bridge_duplicate_request_returns_replayed_response`: issue token `hands:pc.write_file` and pass to `bridge.execute()`.
     - In `test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch`: update `slow_execute` signature to accept `capability_token=None, **kwargs`; issue token and pass to `bridge.execute()`.
   - Update `tests/T09_golden_task/test_golden_a_agent_os.py`:
     - In `test_golden_a_agent_os_real_execution_flow`: initialize `CapabilityAuthority`, issue token `hands:pc.write_file`, and pass to `bridge.execute()`.
   - Create `tests/T03_capability/test_hands_authority_pep.py implementing the 4 invariant tests (missing token, scope mismatch, revoked epoch, rollback requires token).

7. Verification:
   - Run `python tools/probes/probe_hands_authority_flaws.py` -> verify GREEN.
   - Run `pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py tests/T03_capability/ -v`.
   - Run `pytest tests/ -q` -> must be >= 441 passed, exit code 0.
   - Run `python tools/t00_meta_audit.py` -> must PASS.

8. Write handoff report in `c:\Users\check\Downloads\scp\.agents\orchestrator_5\worker_2\handoff.md` and notify orchestrator via send_message.
