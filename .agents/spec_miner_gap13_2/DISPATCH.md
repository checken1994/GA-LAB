# DISPATCH — Spec Miner GAP-13 #2 (Replacement: Causal Graph & FA-13 Test Coverage Matrix)

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
Resume from interruption of `spec_miner_gap13_1`:
Read:
- `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md`
- `c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md`
- `c:\Users\check\Downloads\scp\.agents\explorer_gap13_2\handoff.md`
- `c:\Users\check\Downloads\scp\tools\probes\probe_gap13_bypass.py` (already created by predecessor)

Your role: Read-only specification and test investigator.
Tasks:
1. Run and verify `tools/probes/probe_gap13_bypass.py` on live SQLite, capturing actual terminal output confirming RED (exploit succeeds pre-patch).
2. Synthesize the complete Mermaid Causal Graph for the TaskKernel Approval Gate (FA-12).
3. Formulate the comprehensive FA-13 Coverage Matrix for `tests/T04_kernel/test_adversarial_kernel_flaws.py` covering:
   - Branch 1: Direct unauthenticated transition from WAITING_APPROVAL -> READY (must raise InvalidTransition).
   - Branch 2: Missing / None / empty approval token (must raise InvalidTokenSignatureError or KernelError).
   - Branch 3: Forged / tampered token signature (must raise InvalidTokenSignatureError).
   - Branch 4: Valid signature but wrong capability scope (lacking approval:grant) (must raise InvalidTransition or PermissionError).
   - Branch 5: Valid signature but mismatched task_id scope (must raise InvalidTransition).
   - Branch 6: Expired token (must raise InvalidTokenSignatureError or InvalidTransition).
   - Branch 7: Valid CapabilityToken with approval:grant -> transitions to READY, commits SQLite state, increments version, records TASK_APPROVED event.
   - Branch 8: Valid Operator Signature -> transitions to READY, commits SQLite state, increments version, records TASK_APPROVED event.
   - Branch 9: OCC version mismatch during commit_approval -> raises OptimisticLockError.
   - Branch 10: Task in non-WAITING_APPROVAL state (e.g. CREATED, RUNNING) -> raises InvalidTransition.
   - Branch 11: Caller audit: check if any callers (e.g. ask_kernel_adapter, test files) use WAITING_APPROVAL -> READY.
4. Output your full report to `c:\Users\check\Downloads\scp\.agents\spec_miner_gap13_2\handoff.md` and report back via `send_message`.

## 2026-09-08T06:20:35Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

PRE-SESSION MANDATE: You MUST call view_file on:
1. c:\Users\check\Downloads\scp\GA.md
2. c:\Users\check\Downloads\scp\.agents\GEMINI.md
3. c:\Users\check\Downloads\scp\.agents\AGENTS.md
4. c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
5. c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md

Your working directory is: c:\Users\check\Downloads\scp\.agents\spec_miner_gap13_2
Read your instructions in: c:\Users\check\Downloads\scp\.agents\spec_miner_gap13_2\DISPATCH.md
Also read authoritative user request in: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md,
project scope in: c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md,
and previous explorer handoff in: c:\Users\check\Downloads\scp\.agents\explorer_gap13_2\handoff.md.

Your mission:
You are the replacement Spec Miner for GAP-13. Predecessor created tools/probes/probe_gap13_bypass.py.
Execute tools/probes/probe_gap13_bypass.py on live SQLite, obtain raw terminal execution evidence confirming RED (exploit succeeds).
Construct the full Mermaid Causal Graph for the TaskKernel Approval Gate (FA-12).
Construct the FA-13 Coverage Matrix covering all 11 causal branches and downstream callers.
Output your comprehensive report to c:\Users\check\Downloads\scp\.agents\spec_miner_gap13_2\handoff.md and report back via send_message.

