## 2026-09-08T01:22:38Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are Explorer 2 (teamwork_preview_explorer).
Your working directory is: c:\Users\check\Downloads\scp\.agents\explorer_2

AUTHORITATIVE DOCUMENTS TO READ FIRST:
- c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (MANDATORY: read this first!)
- c:\Users\check\Downloads\scp\.agents\orchestrator_9\SCOPE.md
- c:\Users\check\Downloads\scp\.agents\orchestrator_8\handoff.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md

EXPLORATION MISSION:
You are a READ-ONLY explorer. Do NOT modify any code.
Focus on Downstream Callers across the codebase:
1. Audit `scp/ask_kernel_adapter.py`:
   - Find `fail()` method (around line 430).
   - Inspect caller arguments, active lease, worker/actor identity, and current call to `kernel.transition(..., "FAILED")`.
   - Determine how `fail()` should invoke `kernel.commit_failed()`. What `indictment_ref`, `failure_classification`, and `details` should it pass?
2. Audit `scp/hands/task_kernel_bridge.py`:
   - Locate all calls to `transition(..., "FAILED")` (e.g. lines 445, 582).
   - Analyze how lease, actor, and error information are handled at these call sites.
   - Determine how `commit_failed()` should be called here.
3. Comprehensive Codebase Scan:
   - Search the ENTIRE `scp/` tree for ANY other calls to `transition(` with `"FAILED"`.
   - Check if there are scheduler, worker, hands, or orchestrator components calling `transition(..., "FAILED")`.
   - Map all call sites that must be migrated to `commit_failed()`.
4. Deliver a comprehensive report in `c:\Users\check\Downloads\scp\.agents\explorer_2\handoff.md` and notify orchestrator via send_message.
