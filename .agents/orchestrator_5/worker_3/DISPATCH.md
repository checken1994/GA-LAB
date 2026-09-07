## 2026-09-07T07:25:36Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You are Worker 3: Remediation Implementer for Iteration 2 (GAP-07).
Your working directory is: c:\Users\check\Downloads\scp\.agents\orchestrator_5\worker_3
Workspace root: c:\Users\check\Downloads\scp
Original request is recorded at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (read this file first!).
Scope document: c:\Users\check\Downloads\scp\.agents\orchestrator_5\SCOPE.md

You have exclusive write ownership of these files:
- scp/hands/task_kernel_bridge.py
- scp/hands/planner.py
- tests/T03_capability/test_hands_authority_pep.py

Read the detailed handoff reports from Explorers 4, 5, 6:
- c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_4\handoff.md (Bridge Lease Double-Release)
- c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_5\handoff.md (Planner Step Token Preservation)
- c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_6\handoff.md (Bridge Policy Denial Regression Test)

Implementation Tasks:
1. In `scp/hands/task_kernel_bridge.py`:
   - In lines ~445-455 (the policy rejection block inside `execute()`):
     Delete `self.kernel.release(task_id, lease.lease_id)` because `self.kernel.transition(task_id, "FAILED", ...)` already atomically releases the active lease in the SQLite database transaction.
   - In `_public_kernel()`: ensure `requiresRecovery` is `False` for clean `FAILED` tasks, and `taskState` reflects `task.get("state")`.
2. In `scp/hands/planner.py`:
   - In `_validate_step()`: preserve `raw.get("capabilityToken") or raw.get("capability_token")`. Normalize via `parse_capability_token()`: if parsed, store `parsed.to_dict()`, otherwise store raw.
   - In `_run_dag_locked`: ensure step-level capability check correctly evaluates `step_token`.
3. In `tests/T03_capability/test_hands_authority_pep.py`:
   - Add `test_bridge_execute_missing_token_clean_policy_denial_no_recovery` as designed by Explorer 6.
   - Verify it tests `bridge.execute("pc.write_file", ..., capability_token=None)` returning `success=False`, `requiresRecovery=False`, `taskState="FAILED"`, and no `OptimisticLockError`.
4. Verification:
   - Run `pytest tests/T03_capability/test_hands_authority_pep.py -v` (must all pass).
   - Run `pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py -v` (must all pass).
   - Run `pytest tests/ -q` (must be >= 445 passed, exit code 0).
   - Run `python tools/t00_meta_audit.py` (must pass with 0 new regressions).
5. Document results and raw terminal outputs in `c:\Users\check\Downloads\scp\.agents\orchestrator_5\worker_3\handoff.md` and report back via send_message.
