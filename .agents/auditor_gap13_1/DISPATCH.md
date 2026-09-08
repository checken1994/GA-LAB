# DISPATCH — Forensic Auditor GAP-13 #1 (Zero-Tolerance Integrity Audit)

## 🔒 Mandatory Binding
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

## PRE-SESSION MANDATE
You MUST call `view_file` on:
1. `c:\Users\check\Downloads\scp\GA.md`
2. `c:\Users\check\Downloads\scp\.agents\GEMINI.md`
3. `c:\Users\check\Downloads\scp\.agents\AGENTS.md`
4. `c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md`
5. `c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md`

## Mission & Scope
Read:
- `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md`
- `c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md`
- `c:\Users\check\Downloads\scp\.agents\worker_gap13_1\handoff.md`
- Modified source files: `scp/task_kernel_parts/taskkernel.py`, `scp/task_kernel.py`, `tests/T04_kernel/test_adversarial_kernel_flaws.py`

Your role: Forensic Auditor (`teamwork_preview_auditor`).
Perform an exhaustive forensic audit on the GAP-13 patch:
1. **Anti-Cheat Forensics (Zero Tolerance)**:
   - Check AST and source code for hardcoded test values, dummy/mock returns, or conditional branches that check `if "test" in task_id:` or bypass checks for test runners.
   - Verify `verify_approval_authority()` genuinely executes HMAC-SHA256 calculation and verification.
   - Verify `commit_approval()` genuinely performs SQLite database query execution and version increments at the DB level, not in memory variables.
2. **FA Rules Forensic Sweep**:
   - FA-01: Verify no assertions in `tests/` were loosened, removed, or made lenient.
   - FA-02: Verify zero tests were deleted, skipped (`@pytest.mark.skip`), xfailed (`@pytest.mark.xfail`), or commented out.
   - FA-04: Verify no simulated or manufactured VERIFIED results.
   - FA-05: Verify TaskKernel does NOT self-grant authority or issue tokens.
   - FA-08: Verify no forged provenance or simulated output logs.
   - FA-09: Verify probe was executed and captured real terminal stdout/stderr.
   - FA-12: Verify physical SQLite data persistence inspection was executed.
   - FA-13: Verify all 11 causal branches are covered by real assertions.
3. **Run Independent Audits**:
   - `python tools/t00_meta_audit.py`
   - `python tools/verify_scp_target_test_coverage.py`
   - `python -m pytest tests/T04_kernel/ -q`
4. Deliver your audit report and explicit verdict (`CLEAN` or `INTEGRITY VIOLATION`) to `c:\Users\check\Downloads\scp\.agents\auditor_gap13_1\handoff.md` and report back via `send_message`.

## 2026-09-08T06:41:52Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

PRE-SESSION MANDATE: You MUST call view_file on:
1. c:\Users\check\Downloads\scp\GA.md
2. c:\Users\check\Downloads\scp\.agents\GEMINI.md
3. c:\Users\check\Downloads\scp\.agents\AGENTS.md
4. c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
5. c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md

Your working directory is: c:\Users\check\Downloads\scp\.agents\auditor_gap13_1
Read your instructions in: c:\Users\check\Downloads\scp\.agents\auditor_gap13_1\DISPATCH.md
Also read authoritative user request in: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
and project scope in: c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md
and worker handoff in: c:\Users\check\Downloads\scp\.agents\worker_gap13_1\handoff.md

Your mission:
Forensic Integrity Audit for GAP-13:
1. Audit AST and source code in scp/task_kernel_parts/taskkernel.py, scp/task_kernel.py, tests/T04_kernel/test_adversarial_kernel_flaws.py for any hardcoded results, dummy facades, simulated passes, or bypasses.
2. Verify strict adherence to FA-01 (no loosened assertions), FA-02 (no deleted/skipped/xfailed tests), FA-04 (no manufactured green), FA-05 (no self-granting authority), FA-08 (no fake provenance), FA-09 (probe verified), FA-12 (empirical DB closure), FA-13 (causal matrix coverage).
3. Run t00_meta_audit.py, verify_scp_target_test_coverage.py, pytest tests/T04_kernel/.
Deliver forensic audit report with explicit verdict (CLEAN / INTEGRITY VIOLATION) to c:\Users\check\Downloads\scp\.agents\auditor_gap13_1\handoff.md and report back via send_message.
