# BRIEFING — 2026-09-07T03:21:00Z

## Mission
Investigate and map the caller pipeline (hands_routes.py, task_kernel_bridge.py, planner.py) that invokes HandsExecutor to thread Zero-Trust capability tokens without parameter dropping.

## 🔒 My Identity
- Archetype: explorer
- Roles: Caller Protocols & Bridges Specialist
- Working directory: c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_2
- Original parent: 967399d1-d666-4dce-899b-4c2468b6dd91
- Milestone: GAP-07 Caller Protocols & Bridges Investigation

## 🔒 Key Constraints
- Read-only investigation — do NOT implement / do NOT mutate product code
- Zero-Trust and Fail-Closed principles
- Adhere to FA-01 through FA-10
- FORBIDDEN from self-granting authority or simulating PASS results
- Boundaries at Database/Hardware level, not via RAM/Variables

## Current Parent
- Conversation ID: 967399d1-d666-4dce-899b-4c2468b6dd91
- Updated: 2026-09-07T03:14:09Z

## Investigation State
- **Explored paths**:
  - `scp/api/routes/hands_routes.py` (lines 1-258: schemas and handlers)
  - `scp/hands/task_kernel_bridge.py` (lines 1-692: execute, rollback, _policy_blocked_before_dispatch)
  - `scp/hands/planner.py` (lines 1-843: run_plan, _run_plan_locked, run_dag, _run_dag_step, rollback_plan)
  - `scp/security/capability_epoch.py` (lines 1-145: CapabilityToken, CapabilityAuthority)
  - `scp/core/capability_token.py` (lines 1-57: mint_token, verify_token)
  - `tests/T09_golden_task/test_golden_a_agent_os.py`
  - `tests/T04_kernel/test_kernel_p1_regressions.py`
  - `tools/probes/probe_hands_authority_flaws.py`
- **Key findings**:
  1. `HandsActionRequest`, `HandsRollbackRequest`, and `PlannerRollbackRequest` in `hands_routes.py` completely omit capability token fields.
  2. `hands_execute` and `hands_rollback` drop capability tokens before calling the bridge.
  3. `TaskKernelHandsBridge.execute` and `rollback` lack `capability_token` parameter and forward `None` to `executor.execute` / `rollback`.
  4. The bridge must NOT mint tokens (Zero-Trust separation of concerns); callers must pass tokens to the bridge.
  5. `_policy_blocked_before_dispatch` in `task_kernel_bridge.py` does not match `CapabilityRequiredError` or `CapabilityScopeMismatchError`, causing unauthorized pre-dispatch rejections to fall through to `UNKNOWN` state instead of `FAILED`.
  6. `HandsPlanner._run_plan_locked`, `_run_dag_step`, and `rollback_plan` drop `capability_token` when calling `self.executor.execute` and `rollback`.
  7. `verify_token` in `planner.py` throws `TypeError` if passed a `CapabilityToken` dataclass object instead of a string.
  8. A shared helper `parse_capability_token` in `capability_epoch.py` resolves tokens from `CapabilityToken`, `dict` (camelCase/snake_case), or JSON string, failing closed to `None` when invalid.
- **Unexplored areas**:
  - None within explorer_2 scope.

## Key Decisions Made
- Fully documented mapping of function signatures, arguments, and defaults across all three files.
- Documented two critical edge-case bugs: `_policy_blocked_before_dispatch` false-fallthrough and `verify_token` TypeError.

## Artifact Index
- `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_2\DISPATCH.md` — Incoming instructions
- `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_2\BRIEFING.md` — Working memory and status
- `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_2\progress.md` — Heartbeat log
- `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_2\handoff.md` — Final 5-component report
