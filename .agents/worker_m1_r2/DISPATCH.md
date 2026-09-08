## 2026-09-08T12:36:26Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Identity: You are Worker M1 (teamwork_preview_worker).
Your working directory is: c:\Users\check\Downloads\scp\.agents\worker_m1_r2
Original user request file: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
Scope document: c:\Users\check\Downloads\scp\.agents\orchestrator_1\SCOPE.md
Explorer R2 analysis: c:\Users\check\Downloads\scp\.agents\explorer_r2\analysis.md
Explorer R2 handoff: c:\Users\check\Downloads\scp\.agents\explorer_r2\handoff.md

FILE WRITE OWNERSHIP: You exclusively own:
- c:\Users\check\Downloads\scp\scp\pc_control\pc_controller.py
- c:\Users\check\Downloads\scp\scp\hands\hands_executor.py
- c:\Users\check\Downloads\scp\scp\api\routes\pc_controller_routes.py
- c:\Users\check\Downloads\scp\tests\T03_capability\test_pc_controller_token_pep.py
Do NOT touch any other files outside this boundary.

Mission: Implement R2: Execution Bypass Remediation in PCController.
Key implementation tasks:
1. In `scp/pc_control/pc_controller.py`:
   - Inject `CapabilityAuthority` (or allow optional passing in `__init__`, resolving default or creating authority using `SCP_CAPABILITY_SECRET`).
   - Define a robust, fail-closed `_verify_token(self, token: Any, required_action: str = "pc.execute") -> CapabilityToken` method that validates HMAC-SHA256 signature, matching epoch, and subject scope via `CapabilityAuthority.validate()`. Raise `InvalidTokenSignatureError` (or `PermissionError`) immediately if token is missing, expired, tampered, or invalid.
   - Update `execute()`, `write_file()`, `read_file()`, `rollback()`, and `clear_kill_switch()` to accept `capability_token: CapabilityToken | str | None = None` and strictly enforce `self._verify_token()` BEFORE any subprocess invocation or disk mutation.
2. In `scp/hands/hands_executor.py`:
   - Ensure `HandsExecutor` extracts `capability_token` from execution params/context and forwards it when calling `self.controller.execute()`, `self.controller.write_file()`, and `self.controller.read_file()`.
3. In `scp/api/routes/pc_controller_routes.py`:
   - Enforce dynamic `CapabilityToken` validation from request headers/payload in addition to or replacing static token bypass.
4. In `tests/T03_capability/test_pc_controller_token_pep.py`:
   - Write comprehensive unit & regression tests verifying:
     - Rejection of calls without token (fail-closed, raises error).
     - Rejection of tampered / forged tokens (HMAC signature mismatch).
     - Rejection of expired / bad epoch tokens.
     - Acceptance and successful execution when provided a genuine token signed by `CapabilityAuthority`.
     - End-to-end integration with `HandsExecutor`.
5. Run tests via `run_command`:
   - Run `python -m pytest tests/T03_capability/test_pc_controller_token_pep.py -v`
   - Run existing capability tests: `python -m pytest tests/T03_capability/ -q`
6. Prepare Coverage Matrix per FA-13 and verify all causal branches.
7. Write complete handoff report to `c:\Users\check\Downloads\scp\.agents\worker_m1_r2\handoff.md` and send message to parent.

## 2026-09-08T12:39:42Z
**Context**: Server restart recovery for Worker M1 (R2 Remediation).
**Content**: The host server has restarted. Please resume your implementation immediately from where you stopped.
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables. DO NOT CHEAT.
Tasks:
1. Implement token PEP in `scp/pc_control/pc_controller.py` (_verify_token with CapabilityAuthority, fail-closed).
2. Ensure `scp/hands/hands_executor.py` forwards capability_token.
3. Update `scp/api/routes/pc_controller_routes.py` for token verification.
4. Write tests in `tests/T03_capability/test_pc_controller_token_pep.py` and run them via run_command.
5. Create Coverage Matrix (FA-13) and write handoff to `.agents/worker_m1_r2/handoff.md`.
**Action**: Resume execution, run tests, and report back when complete.
