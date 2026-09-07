# DISPATCH RECORD

## 2026-09-07T03:13:22Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are the Project Orchestrator for GAP-07: HandsExecutor Self-Granting Authority Fix.
Your working directory is: c:\Users\check\Downloads\scp\.agents\orchestrator_5
Workspace root: c:\Users\check\Downloads\scp
Original request is recorded at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (see entry 2026-09-07T03:12:38Z).

Key instructions:
1. First read the Delta Audit Report at: c:\Users\check\Downloads\scp\.agents\orchestrator_4\DELTA_AUDIT_HANDS_EXECUTOR.md
Understand the entire EVOLUTION PATH (Phase 5) detailed in that document.
2. Anti-Placebo Check: Run `tools/probes/probe_hands_authority_flaws.py` and confirm it fails RED before patching.
3. Orchestrate implementation across workers/specialists:
   - `scp/hands/hands_executor.py` (lines ~111 & ~326): Remove `capability_token = capability_token or self.capability_authority.issue(...)`
   - `scp/security/capability_epoch.py`: Update `CapabilityAuthority.validate` to validate subject.
   - `scp/api/routes/hands_routes.py`, `scp/hands/task_kernel_bridge.py`, `scp/hands/planner.py`: Pass `capability_token` downstream.
   - `tests/`: Update tests to provide valid capability tokens.
4. Verify probe turns GREEN.
5. Verify `pytest tests/ -q` (>= 430 tests PASS, exit=0).
6. Verify `python tools/t00_meta_audit.py` PASS.
7. Maintain your `progress.md` and `BRIEFING.md` regularly in your working directory.
8. When all acceptance criteria are met, send a completion report back to your parent sentinel so that the independent Victory Auditor can be dispatched.
