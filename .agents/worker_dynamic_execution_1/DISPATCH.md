# Task Assignment: Worker Dynamic Execution 1

## Identity
- Role: Worker (Dynamic Runtime Execution Specialist)
- Archetype: teamwork_preview_worker
- Working directory: c:\Users\check\Downloads\scp\.agents\worker_dynamic_execution_1
- Parent: Orchestrator 2 (c:\Users\check\Downloads\scp\.agents\orchestrator_2)

## Mandatory Input
- Read ORIGINAL_REQUEST.md at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (specifically the entry dated 2026-09-05T10:20:22Z).
- Apply skills:
  - c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
  - c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md
  - c:\Users\check\Downloads\scp\.agents\skills\scp-runtime-audit\SKILL.md

## Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Objective & Scope
You are tasked with executing the live dynamic runtime execution probes across the SCP repository (`c:\Users\check\Downloads\scp`):
1. Execute `python tools/t00_meta_audit.py` and capture verbatim terminal output.
2. Execute `python tools/verify_scp_test_skill_contract.py` and capture verbatim output.
3. Execute live pytest test suites:
   - Full test run or comprehensive suites: `pytest tests/` (capture exact total passed, skipped, failed, xfailed, and execution duration).
   - Core subsystem test runs:
     - `pytest tests/T04_kernel/ -v`
     - `pytest tests/T06_verifier/ -v`
     - `pytest tests/T09_golden_task/ -v`
     - `pytest tests/T10_recovery/ -v`
     - `pytest scp/tests/ -v` (or representative modules)
4. Probe direct subsystem runtime behaviors:
   - Check TaskKernel 18 active states vs 15-state mandate in live Python REPL / command.
   - Check `EvidenceStore` staging cleanup race condition in live Python probe.
   - Check `reality_test.py` behavior on synthetic callables.
5. Capture full verbatim terminal outputs, exact timestamps, exit codes, and memory/process health.
6. Do NOT modify any production code or existing tests.

## Output Requirements
Write your findings and verbatim terminal output logs to `c:\Users\check\Downloads\scp\.agents\worker_dynamic_execution_1\handoff.md` and `progress.md`.
Notify orchestrator when done via send_message.

## 2026-09-05T10:27:38Z
You are Worker Dynamic Execution 1. Your working directory is c:\Users\check\Downloads\scp\.agents\worker_dynamic_execution_1.
Read your DISPATCH.md at c:\Users\check\Downloads\scp\.agents\worker_dynamic_execution_1\DISPATCH.md.
MANDATORY: Read ORIGINAL_REQUEST.md at c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md before starting work.
Apply skills:
- c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-runtime-audit\SKILL.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Execute live runtime test suites and adversarial probes:
1. python tools/t00_meta_audit.py (capture verbatim log)
2. python tools/verify_scp_test_skill_contract.py (capture verbatim log)
3. pytest tests/ (capture exact counts: passed, skipped, failed, duration, verbatim log)
4. pytest tests/T04_kernel/ -v, pytest tests/T06_verifier/ -v, pytest tests/T09_golden_task/ -v, pytest tests/T10_recovery/ -v
5. Probe live Python runtime for TaskKernel state machine (18 active states vs 15 mandate) and EvidenceStore staging cleanup.

Maintain progress.md in your directory. Write your full report with all verbatim logs to c:\Users\check\Downloads\scp\.agents\worker_dynamic_execution_1\handoff.md.
When finished, send a message to orchestrator parent with a summary of findings and the path to your handoff.md.
