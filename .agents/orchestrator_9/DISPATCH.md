## 2026-09-08T01:21:32Z

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are the Project Orchestrator (orchestrator_9).
Your working directory is: c:\Users\check\Downloads\scp\.agents\orchestrator_9

PRE-SESSION MANDATE:
Before taking any action, you MUST use view_file to inspect:
1. c:\Users\check\Downloads\scp\GA.md
2. c:\Users\check\Downloads\scp\.agents\GEMINI.md
3. c:\Users\check\Downloads\scp\.agents\AGENTS.md
4. Relevant skills: .agents/skills/scp-dna/SKILL.md, .agents/skills/scp-task-kernel-review/SKILL.md, .agents/skills/scp-reality-verifier/SKILL.md

AUDIT & EVOLUTION PATH REFERENCE:
The Delta Audit on GAP-12 and Phase 5 Remediation Blueprint was established in:
- c:\Users\check\Downloads\scp\.agents\orchestrator_8\handoff.md
- Existing GAP-12 probe: c:\Users\check\Downloads\scp\tools\probes\probe_gap12_delta_audit.py
- Authoritative user request: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md

TASK REQUIREMENTS:
Proceed to remediate GAP-12 based on the Evolution Path Blueprint:

### R1. Restrict Direct FAILED Transitions
- In `scp/task_kernel_parts/taskkernel.py`, inside `transition()`, block direct transitions to `FAILED` (analogous to `COMPLETED`), raising `InvalidTransition`.
- Moving state to FAILED must strictly pass through the gate `commit_failed()`.

### R2. Introduce `commit_failed()` Endpoint
- Add `commit_failed(self, task_id, lease_id, actor, failure_classification, indictment_ref, details)` to `TaskKernel`.
- Requirements for `commit_failed`:
  1. Validate lease is valid and `actor` matches lease owner (update `_assert_lease()` to check `actor`).
  2. Check retry budget (`attempts < max_attempts`): if retryable and attempts remain, transition to `UNKNOWN` / `RETRY_SCHEDULED`. If exhausted or fatal failure, transition to `FAILED`.
  3. Enforce persisting `indictment_ref` and failure details to database (events/tasks) completely.

### R3. Migrate Downstream Callers
- Update `scp/ask_kernel_adapter.py` (specifically `fail()`) to call `commit_failed()` instead of `transition(..., "FAILED")`.
- Update `scp/hands/task_kernel_bridge.py` to use `commit_failed()`.
- Ensure changes are completely backward-compatible at the database level.

### R4. Causal-Driven Test Coverage (FA-13)
- Update `tests/T04_kernel/test_adversarial_kernel_flaws.py`.
- Create/update tests covering the entire Causal Graph for `commit_failed()`, including retryable and exhausted branches.
- Apply similarly for related callers (AskKernelAdapter, TaskKernelBridge).
- Ensure no existing tests break. If broken due to intentional contract upgrade, fix according to FA-01/FA-02.

ACCEPTANCE CRITERIA:
- `pytest tests/ -q` PASS 100%, no skips/xfails.
- `python tools/t00_meta_audit.py` PASS (0 regressions).
- Reality Check (FA-12): Re-run probes/adversarial tests on live SQLite. All 4 attack vectors of GAP-12 must be blocked (GREEN).
- Maintain progress.md and BRIEFING.md in your working directory.
- Deliver full handoff.md upon completion.
