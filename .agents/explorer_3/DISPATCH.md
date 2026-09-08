## 2026-09-08T01:22:38Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are Explorer 3 (teamwork_preview_explorer).
Your working directory is: c:\Users\check\Downloads\scp\.agents\explorer_3

AUTHORITATIVE DOCUMENTS TO READ FIRST:
- c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (MANDATORY: read this first!)
- c:\Users\check\Downloads\scp\.agents\orchestrator_9\SCOPE.md
- c:\Users\check\Downloads\scp\.agents\orchestrator_8\handoff.md
- c:\Users\check\Downloads\scp\tools\probes\probe_gap12_delta_audit.py
- c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md

EXPLORATION MISSION:
You are a READ-ONLY explorer. Do NOT modify any code.
Focus on Test Suites, Probes, FA-12 Empirical Closure, and FA-13 Causal Coverage:
1. Probe Analysis:
   - Inspect `tools/probes/probe_gap12_delta_audit.py`.
   - Verify how it tests Vector 1 (PLANNING->FAILED), Vector 2 (RUNNING->FAILED attempt 1), Vector 3 (VERIFYING->FAILED), Vector 4 (Stolen lease).
   - Verify what condition triggers `ALL_VECTORS_PROTECTED_GREEN`.
2. Existing Test Suite Audit:
   - Inspect `tests/T04_kernel/test_adversarial_kernel_flaws.py` and other files in `tests/T04_kernel/`.
   - Find tests that currently call `transition(..., "FAILED")`.
   - Determine which tests will fail once direct transition to `"FAILED"` is blocked.
   - For each such test, specify how it must be updated (e.g. either expecting `InvalidTransition` or using `commit_failed()` with proper lease and indictment).
3. FA-13 Causal Graph & Coverage Matrix Design:
   - Design the complete Causal Graph for `commit_failed()` and failure handling.
   - Design test cases covering every causal branch:
     * Branch 1: Direct `transition(task_id, "FAILED")` -> `InvalidTransition` (from all permitted states).
     * Branch 2: `commit_failed()` with invalid lease or non-existent task -> `InvalidTransition` / `TaskNotFound`.
     * Branch 3: `commit_failed()` with actor != leaseholder -> `InvalidTransition` (stolen lease prevented).
     * Branch 4: `commit_failed()` with empty or missing `indictment_ref` -> rejected fail-closed.
     * Branch 5: `commit_failed()` with retryable error and `attempts < max_attempts` -> moves to `UNKNOWN` / `RETRY_SCHEDULED`, increments attempt counter, logs event.
     * Branch 6: `commit_failed()` with retry budget exhausted (`attempts >= max_attempts`) -> moves to terminal `FAILED`.
     * Branch 7: `commit_failed()` with fatal error classification (regardless of attempts) -> moves to terminal `FAILED`.
     * Branch 8: `AskKernelAdapter.fail()` integration.
     * Branch 9: `TaskKernelBridge` error handling integration.
4. Deliver a comprehensive test & causal coverage plan in `c:\Users\check\Downloads\scp\.agents\explorer_3\handoff.md` and notify orchestrator via send_message.
