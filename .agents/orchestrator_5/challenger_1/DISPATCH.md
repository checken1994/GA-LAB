## 2026-09-07T07:10:04Z

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are Challenger 1: PEP Adversarial Penetration Challenger.
Your working directory is: c:\Users\check\Downloads\scp\.agents\orchestrator_5\challenger_1
Workspace root: c:\Users\check\Downloads\scp
Original user request is recorded at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (read this file first!).
Scope document: c:\Users\check\Downloads\scp\.agents\orchestrator_5\SCOPE.md
Delta Audit Report: c:\Users\check\Downloads\scp\.agents\orchestrator_4\DELTA_AUDIT_HANDS_EXECUTOR.md
Worker 2 Handoff: c:\Users\check\Downloads\scp\.agents\orchestrator_5\worker_2\handoff.md

Your tasks:
1. Empirically verify the PEP gate by executing adversarial penetration attacks against `HandsExecutor.execute` and `HandsExecutor.rollback`:
   - Attack 1: Pass `capability_token=None` for mutating action (`pc.write_file`) -> Must fail closed (`CapabilityRequiredError`), verify NO file written to disk.
   - Attack 2: Pass malformed token (empty string, random string, dict missing fields, wrong epoch) -> Must fail closed.
   - Attack 3: Scope Escalation Attack: Issue token strictly for `hands:pc.status` and pass to `execute("pc.write_file", ...)` -> Must fail closed (`CapabilityScopeMismatchError`), verify NO file written to disk.
   - Attack 4: Revocation Attack: Issue valid token, call `cap_auth.revoke()`, attempt dispatch -> Must fail closed.
   - Attack 5: Rollback Attack: Attempt rollback with None, malformed, or wrong subject -> Must fail closed.
2. Execute your attacks live via an adversarial script or inline python commands and capture terminal output.
3. Record your verdict (**APPROVE** if all attacks are successfully repelled fail-closed, or **REJECT** if any bypass succeeds) in `c:\Users\check\Downloads\scp\.agents\orchestrator_5\challenger_1\handoff.md` and send message to orchestrator.
