## 2026-09-07T07:20:43Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are Explorer 6 (Iteration 2): Bridge Policy Denial Test Coverage Specialist.
Your working directory is: c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_6
Workspace root: c:\Users\check\Downloads\scp
Original user request is recorded at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (read this file first!).
Scope document: c:\Users\check\Downloads\scp\.agents\orchestrator_5\SCOPE.md

Iteration 1 Gate Feedback (Challenger 2 & Reviewer 2 Hand-off):
- Read: c:\Users\check\Downloads\scp\.agents\orchestrator_5\challenger_2\handoff.md
- Read: c:\Users\check\Downloads\scp\.agents\orchestrator_5\reviewer_2\handoff.md

Your tasks:
1. Design a comprehensive regression test in `tests/T03_capability/test_hands_authority_pep.py` that exercises `TaskKernelHandsBridge.execute()` directly:
   - Call `bridge.execute("pc.write_file", params={"path": str(target), "content": "test"}, capability_token=None)`
   - Assert `result.get("success") is False`
   - Assert `result.get("kernel", {}).get("requiresRecovery") is False`
   - Assert `result.get("kernel", {}).get("taskState") == "FAILED"`
   - Assert no `OptimisticLockError` in result error string
   - Assert `target.exists() is False`
2. Produce a complete test specification and code snippet in `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_6\handoff.md`.
3. Report back via send_message when done.
