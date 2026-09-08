# DISPATCH — Challenger GAP-13 #2 (Lifecycle State Machine & Boundary Stress)

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

Your role: Adversarial verifier. You MUST attack the state machine boundaries and lifecycle transitions:
1. Lifecycle boundary exploitation:
   - For every possible state in TaskKernel (`CREATED`, `PLANNING`, `READY`, `QUEUED`, `LEASED`, `RUNNING`, `WAITING_TOOL`, `CHECKPOINTED`, `VERIFYING`, `COMPLETED`, `FAILED`, `CANCELLED`, `UNKNOWN`, `RECOVERING`, `RECONCILING`):
     Attempt to call `commit_approval()` with valid, legitimately signed capability tokens.
     Verify that `commit_approval()` strictly raises `InvalidTransition` for all states other than `WAITING_APPROVAL`.
   - Attempt to call `transition(task_id, "READY")` from all non-allowed states, specifically confirming `WAITING_APPROVAL -> READY` is blocked under all combinations of actor, reason, and parameters.
2. Global kill switch integration:
   - When global kill is active (`kernel.set_global_kill(True)`), does `commit_approval()` raise `KillSwitchActive` before modifying the database or checking tokens?
3. Terminal state immutability:
   - Ensure tasks in `COMPLETED`, `FAILED`, `CANCELLED` can never be resurrected or approved.
4. Output your adversarial findings and explicit verdict (`CONFIRMED_CORRECT` / `VULNERABILITY_FOUND`) to `c:\Users\check\Downloads\scp\.agents\challenger_gap13_2\handoff.md` and report back via `send_message`.

## 2026-09-08T06:41:52Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

PRE-SESSION MANDATE: You MUST call view_file on:
1. c:\Users\check\Downloads\scp\GA.md
2. c:\Users\check\Downloads\scp\.agents\GEMINI.md
3. c:\Users\check\Downloads\scp\.agents\AGENTS.md
4. c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
5. c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md

Your working directory is: c:\Users\check\Downloads\scp\.agents\challenger_gap13_2
Read your instructions in: c:\Users\check\Downloads\scp\.agents\challenger_gap13_2\DISPATCH.md
Also read authoritative user request in: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
and project scope in: c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md
and worker handoff in: c:\Users\check\Downloads\scp\.agents\worker_gap13_1\handoff.md

Your mission:
Adversarial challenge on TaskKernel State Machine Boundaries:
1. Attack commit_approval() from all non-WAITING_APPROVAL lifecycle states (CREATED, PLANNING, QUEUED, LEASED, RUNNING, COMPLETED, FAILED, CANCELLED).
2. Attack raw transition() from WAITING_APPROVAL with arbitrary parameters, reasons, and actors.
3. Attack global kill switch activation during approval.
4. Ensure state transitions fail closed under all illegal paths.
Deliver handoff report with explicit verdict (CONFIRMED_CORRECT / VULNERABILITY_FOUND) to c:\Users\check\Downloads\scp\.agents\challenger_gap13_2\handoff.md and report back via send_message.

