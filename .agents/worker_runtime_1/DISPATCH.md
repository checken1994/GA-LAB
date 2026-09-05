## 2026-09-05T05:25:42Z

You are Worker 1 (worker_runtime_1) on the Ultra Max code review and runtime audit team.
Your working directory is: c:\Users\check\Downloads\scp\.agents\worker_runtime_1
Project Root: c:\Users\check\Downloads\scp

You MUST read the original request file before starting:
Path: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
Also review project guidance:
- c:\Users\check\Downloads\scp\AGENTS.md
- c:\Users\check\Downloads\scp\.agents\AGENTS.md
- c:\Users\check\Downloads\scp\.agents\GEMINI.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

YOUR MISSION (RUNTIME EXECUTION & RAW LOG CAPTURE):
You are responsible for executing the real runtime audits and capturing VERBATIM UNTRUNCATED TERMINAL OUTPUT.
1. Determine exact Git SHA:
   Run `git rev-parse HEAD`, `git status`, `git branch --show-current`.
2. Run Meta Audit:
   Run `python tools/t00_meta_audit.py`
   Capture the full, exact raw terminal output (exit code, stdout, stderr) and save it verbatim to:
   `c:\Users\check\Downloads\scp\.agents\worker_runtime_1\meta_audit_output.txt`
3. Run Test Suite:
   Run `pytest tests/T09_golden_task/ -v` (or relevant T09 test suite)
   Run the full test suite `pytest tests/` (or portable runner if specified by project guidance)
   Capture the full, exact raw terminal output (exit code, stdout, stderr, test counts, durations, failures if any) and save it verbatim to:
   `c:\Users\check\Downloads\scp\.agents\worker_runtime_1\pytest_output.txt`
4. Document the exact commands run, working directory, environment, exit codes, and test results in:
   `c:\Users\check\Downloads\scp\.agents\worker_runtime_1\runtime_report.md`
   and write a structured `handoff.md` in your working directory.
   Include progress updates in your `progress.md`.
5. When finished, send a completion message with summary and file paths back to caller (orchestrator). Do NOT modify source code or tests.
