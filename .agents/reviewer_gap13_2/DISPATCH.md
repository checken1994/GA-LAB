# DISPATCH — Reviewer GAP-13 #2 (Cryptographic & Interface Review)

## 🔒 Mandatory Binding
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

## PRE-SESSION MANDATE
You MUST call `view_file` on:
1. `c:\Users\check\Downloads\scp\GA.md`
2. `c:\Users\check\Downloads\scp\.agents\GEMINI.md`
3. `c:\Users\check\Downloads\scp\.agents\AGENTS.md`
4. `c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md`
5. `c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md`

## Mission & Inputs
Read:
- `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md`
- `c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md`
- `c:\Users\check\Downloads\scp\.agents\worker_gap13_1\handoff.md`
- Code in `scp/task_kernel_parts/taskkernel.py`, `scp/core/capability_token.py`, `scp/security/capability_epoch.py`

Your tasks:
1. Perform deep cryptographic and interface verification:
   - Does `verify_approval_authority()` correctly use constant-time comparison (`hmac.compare_digest`) for all token and signature formats?
   - Is secret management fail-closed via `get_capability_secret()` (GAP-09)?
   - Are operator signatures bounded by maximum clock skew (300s TTL) and future timestamp rejections?
   - Does `TaskKernel` avoid self-granting authority (FA-05)?
   - Check `spec/scp_target_test_coverage.yaml` traceability structure.
2. Run reality verification:
   - `pytest tests/T03_capability/ -q`
   - `pytest tests/T04_kernel/ -q`
   - `python tools/verify_scp_target_test_coverage.py`
3. Write your handoff report with explicit verdict (`APPROVE` or `REQUEST_CHANGES`) to `c:\Users\check\Downloads\scp\.agents\reviewer_gap13_2\handoff.md` and report back via `send_message`.

## 2026-09-08T06:41:52Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

PRE-SESSION MANDATE: You MUST call view_file on:
1. c:\Users\check\Downloads\scp\GA.md
2. c:\Users\check\Downloads\scp\.agents\GEMINI.md
3. c:\Users\check\Downloads\scp\.agents\AGENTS.md
4. c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
5. c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md

Your working directory is: c:\Users\check\Downloads\scp\.agents\reviewer_gap13_2
Read your instructions in: c:\Users\check\Downloads\scp\.agents\reviewer_gap13_2\DISPATCH.md
Also read authoritative user request in: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
and project scope in: c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md
and worker handoff in: c:\Users\check\Downloads\scp\.agents\worker_gap13_1\handoff.md

Your mission:
Review the cryptographic token and authority verification in GAP-13:
1. Verify constant-time comparison in verify_approval_authority(), secret fail-closed handling, operator signature TTL, and FA-05 (no self-granting authority).
2. Check spec/scp_target_test_coverage.yaml traceability structure.
3. Run verification commands (pytest tests/T03_capability/, pytest tests/T04_kernel/, verify_scp_target_test_coverage.py).
Deliver handoff report with explicit verdict (APPROVE / REQUEST_CHANGES) to c:\Users\check\Downloads\scp\.agents\reviewer_gap13_2\handoff.md and report back via send_message.

