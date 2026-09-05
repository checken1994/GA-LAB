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

## 2026-09-05T10:20:22Z

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview
> Requested team: Full team

Perform an ultra-rigorous, dynamic runtime execution audit and causal chain analysis across the entire SCP Agent OS system (`c:\Users\check\Downloads\scp`). Do NOT rely solely on dynamic AST scans. Verify actual runtime reality, trace complete cause-and-effect execution paths, and produce an independent Audit Report to benchmark against the DeepInvestigator audit.

Working directory: c:\Users\check\Downloads\scp
Integrity mode: benchmark

## Requirements

### R1. Dynamic Runtime Execution (Reality > Model)
Do not just inspect code or run static parsers ("tĩnh sống -> thực tế chết"). You must execute live runtime test suites, adversarial probes, and component lifecycles (including `pytest tests/`, `python tools/t00_meta_audit.py`, and direct subsystem executions). Capture verbatim terminal logs and verify how the runtime behaves under live execution.

### R2. End-to-End Causal Chain Analysis
Map out and document the full causal chain (Trigger/Input -> Routing/Dispatch -> TaskKernel State Transitions -> Subsystem Side Effects -> Final Verdict/Failure) for:
1. The TaskKernel state machine (analyzing the 18 active runtime states vs the 15-state mandate).
2. The FA-02 skip paths and baseline technical debt identified in the codebase.
3. The Epistemic EvidenceStore crash-ordering and atomic staging lifecycle.

### R3. Comprehensive Reality Audit Report
Synthesize all dynamic findings into a comprehensive Markdown Audit Report (`teamwork_runtime_audit_report.md`). Document raw terminal execution outputs, failure vectors, and a definitive Pass/Fail verdict on whether the system is truly sound in dynamic reality.

## Acceptance Criteria

### Objective Verification
- [ ] Verbatim raw terminal output from live dynamic execution runs (`pytest`, `t00_meta_audit.py`, or direct subsystem invocation) included in the report.
- [ ] Explicit step-by-step causal chain flow (Input -> Transition -> Output) documented for TaskKernel and identified technical debts.
- [ ] Definitive evaluation of whether static passes translate into runtime stability or mask latent failures.
- [ ] A final Markdown Audit Report produced in the artifact directory.

## 2026-09-05T11:14:30Z

Bác check đã đổi sang model hệ thống mới (Gemini 3.1 Pro) để vượt qua giới hạn Quota. Yêu cầu team tiếp tục phần Victory Audit còn dang dở. Hãy hoàn thành nốt việc đánh giá từ 2 reviewer cuối cùng và cập nhật kết quả vào `teamwork_runtime_audit_report.md`. Lên!

