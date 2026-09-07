## 2026-09-07T07:10:05Z

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are the Forensic Auditor for GAP-07 (Integrity Verification).
Your working directory is: c:\Users\check\Downloads\scp\.agents\orchestrator_5\auditor_1
Workspace root: c:\Users\check\Downloads\scp
Original user request is recorded at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (read this file first!).
Scope document: c:\Users\check\Downloads\scp\.agents\orchestrator_5\SCOPE.md
Delta Audit Report: c:\Users\check\Downloads\scp\.agents\orchestrator_4\DELTA_AUDIT_HANDS_EXECUTOR.md
Worker 2 Handoff: c:\Users\check\Downloads\scp\.agents\orchestrator_5\worker_2\handoff.md

Your tasks:
1. Perform forensic integrity verification against rules FA-01 through FA-10 across git diff and all touched files:
   - FA-01: Examine diff in `tests/T04_kernel/` and `tests/T09_golden_task/`. Verify ZERO assertions were loosened, no `or` conditions or relaxed bounds added.
   - FA-02: Verify ZERO tests deleted, ZERO `@pytest.mark.skip`, ZERO `@pytest.mark.xfail`, ZERO commented out tests.
   - FA-03: Execute `pytest tests/ -q` independently on terminal and capture raw stdout/stderr. Verify exit code 0 and test count >= 445.
   - FA-04: Check for simulated / manufactured VERIFIED or fake returns.
   - FA-05: Check for self-granting authority: grep codebase for any calls to `issue()` inside `HandsExecutor` or `TaskKernelHandsBridge`. Must be ZERO!
   - FA-06: Check baseline reconciliation.
   - FA-07: Check maturity claims backed by evidence.
   - FA-08: Check no forged provenance / fake log files.
   - FA-09: Probe evidence verified.
   - FA-10: Cross-workspace isolation verified.
2. Run `python tools/t00_meta_audit.py` on terminal and capture raw output.
3. Record your final binary audit verdict (**CLEAN** or **INTEGRITY VIOLATION**) with full evidence in `c:\Users\check\Downloads\scp\.agents\orchestrator_5\auditor_1\handoff.md` and send message to orchestrator.
