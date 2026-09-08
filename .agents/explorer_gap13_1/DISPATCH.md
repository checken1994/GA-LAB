# DISPATCH — Explorer GAP-13 #1 (TaskKernel Mechanics & Transition Guards)

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
Read `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md` and `c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md`.
Your role: Read-only exploration agent. Do NOT modify source code files.
Investigate `scp/task_kernel_parts/taskkernel.py`:
1. Analyze how `transition()` currently handles `WAITING_APPROVAL -> READY`. Where is the unauthenticated bypass vulnerability (GAP-13)?
2. Inspect how GAP-11 (`commit_completed()`) and GAP-12 (`commit_failed()`) were implemented in `TaskKernel`:
   - How does `transition()` block direct transitions to COMPLETED and FAILED?
   - How are `commit_completed()` and `commit_failed()` implemented with lease check, OCC version check, DB storage updates, and append-only event logging?
3. Design the architecture and interface contract for `commit_approval()`:
   - Signature: `commit_approval(self, task_id, approval_token, actor, ...)`
   - Pre-conditions: task in `WAITING_APPROVAL`, valid capability token with `approval:grant` or operator signature, OCC version fencing.
   - Post-conditions: transition to `READY`, DB durability, event journaling.
   - How `transition()` must raise `InvalidTransition` if someone tries raw `transition(task_id, "READY")` while in `WAITING_APPROVAL`.
4. Output report to `c:\Users\check\Downloads\scp\.agents\explorer_gap13_1\handoff.md`.

## 2026-09-08T02:07:22Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

PRE-SESSION MANDATE: You MUST call view_file on:
1. c:\Users\check\Downloads\scp\GA.md
2. c:\Users\check\Downloads\scp\.agents\GEMINI.md
3. c:\Users\check\Downloads\scp\.agents\AGENTS.md
4. c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
5. c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md

Your working directory is: c:\Users\check\Downloads\scp\.agents\explorer_gap13_1
Read your instructions in: c:\Users\check\Downloads\scp\.agents\explorer_gap13_1\DISPATCH.md
Also read authoritative user request in: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
and project scope in: c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md

Your mission:
Investigate TaskKernel mechanics in scp/task_kernel_parts/taskkernel.py. Analyze how transition() handles WAITING_APPROVAL -> READY unauthenticated bypass. Review GAP-11 (commit_completed) and GAP-12 (commit_failed) implementations. Design the commit_approval() architecture with lease/token checks, OCC version fencing, event journaling, and DB durability.
Output your comprehensive findings to c:\Users\check\Downloads\scp\.agents\explorer_gap13_1\handoff.md and report back via send_message.

