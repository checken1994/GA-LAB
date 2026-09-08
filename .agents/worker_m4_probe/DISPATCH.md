## 2026-09-08T01:29:14Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Identity: You are worker_m4_probe (teamwork_preview_worker).
Working directory: c:\Users\check\Downloads\scp\.agents\worker_m4_probe
Parent conversation ID: 55c745a6-7ce1-4c1e-9385-e614d0c57946

MANDATORY READING:
You MUST read `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md` before starting work.
Also read `c:\Users\check\Downloads\scp\GA.md`, `c:\Users\check\Downloads\scp\.agents\AGENTS.md`, `c:\Users\check\Downloads\scp\.agents\skills\scp-delta-audit\SKILL.md`, `c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md`, and `c:\Users\check\Downloads\scp\.agents\orchestrator_8\SCOPE.md`.
Also read Explorer findings in `c:\Users\check\Downloads\scp\.agents\explorer_survey_8_1\analysis.md` and `c:\Users\check\Downloads\scp\.agents\explorer_survey_8_1\handoff.md`.

CRITICAL CONSTRAINT: DO NOT modify any production code in `scp/` during this audit.

TASK (Milestone M4 — Probe Execution & Anti-Placebo Evidence):
1. Review the existing probe script `tools/probes/probe_gap12_gap13_unproven_vulnerabilities.py` and create a dedicated, clean, standalone probe script:
   `tools/probes/probe_gap12_delta_audit.py`
   This script must test all 4 GAP-12 exploit vectors deterministically (NO sleep races):
   - Vector 1: Unauthenticated caller invokes `transition(task_id, "FAILED")` from `PLANNING` with no lease, no authority, and no evidence -> succeeds on current code (VULNERABILITY PROVEN).
   - Vector 2: Worker in `RUNNING` invokes `transition(task_id, "FAILED")` with zero crash evidence / indictment -> succeeds on current code (VULNERABILITY PROVEN).
   - Vector 3: Caller in `VERIFYING` invokes `transition(task_id, "FAILED")` bypassing independent verifier check -> succeeds on current code (VULNERABILITY PROVEN).
   - Vector 4: Stolen or expired lease holder forces task into terminal `FAILED`, permanently killing task and bypassing recovery state machine -> succeeds on current code (VULNERABILITY PROVEN).
2. Execute `python tools/probes/probe_gap12_delta_audit.py` on the terminal via `run_command` and capture the verbatim stdout, stderr, and exit code.
3. Also verify raw SQLite persistence by inspecting the `tasks` and `task_events` table in the test database to prove that the database state was actually mutated to terminal `FAILED`.
4. Demonstrate Anti-Placebo compliance:
   - Prove that on current code, the probe triggers the vulnerability and exposes the broken invariants (RED state / Vulnerability active).
   - Specify the exact falsification condition (i.e. once the evolution path is implemented, `transition(..., "FAILED")` will raise `InvalidTransition` or require `commit_failed()`, turning the exploit into a caught error).
5. Write your comprehensive report and raw terminal outputs to `c:\Users\check\Downloads\scp\.agents\worker_m4_probe\handoff.md`.
6. Use `send_message` to report back to recipient 55c745a6-7ce1-4c1e-9385-e614d0c57946 when finished.
