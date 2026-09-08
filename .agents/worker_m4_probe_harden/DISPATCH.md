## 2026-09-07T18:36:54Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Identity: You are worker_m4_probe_harden (teamwork_preview_worker).
Working directory: c:\Users\check\Downloads\scp\.agents\worker_m4_probe_harden
Parent conversation ID: 55c745a6-7ce1-4c1e-9385-e614d0c57946

MANDATORY READING:
You MUST read `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md` before starting work.
Also read `c:\Users\check\Downloads\scp\GA.md`, `c:\Users\check\Downloads\scp\.agents\AGENTS.md`, `c:\Users\check\Downloads\scp\.agents\skills\scp-delta-audit\SKILL.md`, `c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md`, and `c:\Users\check\Downloads\scp\.agents\orchestrator_8\SCOPE.md`.
Also read Challenger 2 handoff: `c:\Users\check\Downloads\scp\.agents\challenger_delta_2\handoff.md`.

CRITICAL CONSTRAINT: DO NOT modify any production code in `scp/`. Only modify the probe script `tools/probes/probe_gap12_delta_audit.py`.

TASK (Harden GAP-12 Probe Script per Challenger 2 Feedback):
1. In `tools/probes/probe_gap12_delta_audit.py`:
   - Import `InvalidTransition` from `scp.task_kernel`.
   - In Vectors 1, 2, 3, and 4: replace blanket `except Exception as e:` with `except InvalidTransition as e:`. If any other unexpected exception occurs, let it fail or catch and flag as UNEXPECTED_CRASH, to prevent placebo crash-masking.
   - Update summary verdict: if all 4 vectors are protected with `InvalidTransition`, explicitly output `ALL_VECTORS_PROTECTED_GREEN` (exit 0). If all 4 vectors reproduce the vulnerability, output `ALL_VECTORS_PROVEN_RED` (exit 0).
2. Execute `python tools/probes/probe_gap12_delta_audit.py` on the terminal via `run_command` and capture verbatim output.
3. Verify test suite regression: `pytest tests/T04_kernel -q`.
4. Ensure `git diff scp/` is completely empty.
5. Write your handoff report to `c:\Users\check\Downloads\scp\.agents\worker_m4_probe_harden\handoff.md`.
6. Send a message to recipient 55c745a6-7ce1-4c1e-9385-e614d0c57946 when finished.
