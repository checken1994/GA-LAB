# DISPATCH — Reviewer GAP-13 #1 (Correctness & Invariant Review)

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
- Code diff in `scp/task_kernel_parts/taskkernel.py`, `scp/task_kernel.py`, `tests/T04_kernel/test_adversarial_kernel_flaws.py`

Your tasks:
1. Review the patch against specifications:
   - Does `transition()` strictly block `WAITING_APPROVAL -> READY` with `InvalidTransition`?
   - Does `commit_approval()` enforce fail-closed verification, OCC version fencing (`rowcount == 1`), and immutable event journaling (`TASK_APPROVED`)?
   - Are all 11 causal branches (BR-1 to BR-11) covered in `test_adversarial_kernel_flaws.py` without loosening assertions or skipping tests (FA-01, FA-02)?
2. Run reality verification:
   - `python tools/probes/probe_gap13_bypass.py` (must pass `ALL_VECTORS_PROTECTED_GREEN`)
   - `pytest tests/T04_kernel/ -q` (all pass)
   - `python tools/t00_meta_audit.py` (PASS, 0 regressions)
3. Write your handoff report with explicit verdict (`APPROVE` or `REQUEST_CHANGES`) to `c:\Users\check\Downloads\scp\.agents\reviewer_gap13_1\handoff.md` and report back via `send_message`.

## 2026-09-08T06:41:52Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

PRE-SESSION MANDATE: You MUST call view_file on:
1. c:\Users\check\Downloads\scp\GA.md
2. c:\Users\check\Downloads\scp\.agents\GEMINI.md
3. c:\Users\check\Downloads\scp\.agents\AGENTS.md
4. c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
5. c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md

Your working directory is: c:\Users\check\Downloads\scp\.agents\reviewer_gap13_1
Read your instructions in: c:\Users\check\Downloads\scp\.agents\reviewer_gap13_1\DISPATCH.md
Also read authoritative user request in: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
and project scope in: c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md
and worker handoff in: c:\Users\check\Downloads\scp\.agents\worker_gap13_1\handoff.md

Your mission:
Review the GAP-13 implementation:
1. Inspect scp/task_kernel_parts/taskkernel.py, scp/task_kernel.py, and tests/T04_kernel/test_adversarial_kernel_flaws.py.
2. Verify transition() blocking, commit_approval() OCC fencing and journaling, and 11 causal tests.
3. Run verification commands (probe_gap13_bypass.py, pytest tests/T04_kernel/, t00_meta_audit.py).
Deliver handoff report with explicit verdict (APPROVE / REQUEST_CHANGES) to c:\Users\check\Downloads\scp\.agents\reviewer_gap13_1\handoff.md and report back via send_message.

