# Original User Request

## 2026-09-05T05:24:22Z

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview
> Requested team: Full team

Perform an 'Ultra max' comprehensive code review and runtime audit of the newly pushed branch (`fix/t09-golden-task-debt`) and any local changes in the project root. The goal is to verify code quality, adherence to strict SCP rules, and identify any unintended side effects before merging. Produce a detailed Audit Report.

Working directory: c:\Users\check\Downloads\scp
Integrity mode: benchmark

## Requirements

### R1. Full Runtime Audit (Zero Trust)
Do not just read file diffs. You must verify reality by executing the full test suite (`pytest`) and the meta audit script (`python tools/t00_meta_audit.py`). Treat all previous claims with extreme skepticism.

### R2. Security & Guardrail Verification
Rigorously verify that the changes in `scp/autofix/runner_phases/reality_test.py` and `tests/T09_golden_task` do not violate FA-01 to FA-07. Confirm that exceptions are no longer swallowed and state pollution is fully prevented. 

### R3. Audit Report Generation
Do not attempt to fix or commit code. Your sole deliverable is a comprehensive Markdown Audit Report documenting every finding, flaw, or confirmation of integrity.

## Acceptance Criteria

### Objective Verification
- [ ] A final Markdown Audit Report is produced outlining the exact SHA tested, methodology, and a Pass/Fail verdict.
- [ ] The report explicitly includes the verbatim raw terminal output of `pytest` and `t00_meta_audit.py` as undeniable proof of the runtime audit.
- [ ] The report explicitly cross-checks and evaluates the changes against the FA-01 to FA-07 constraints.
