# Audit Scope: Ultra Max Code Review & Runtime Audit of `fix/t09-golden-task-debt`

## Objective
Verify code quality, adherence to strict SCP rules (including FA-01 to FA-07 and 29 SCP DNA principles), identify any unintended side effects, confirm runtime validity with verbatim test outputs, and produce a definitive Pass/Fail Audit Report for the branch `fix/t09-golden-task-debt`.

## Target Scope & Changed Modules
1. `scp/autofix/runner_phases/reality_test.py`
2. `tests/T09_golden_task` (and any related test files)
3. Any other modified or untracked files in working tree vs main
4. Exact Git SHA, branch status, and commit log

## Invariants & Guardrails Under Review
- **FA-01**: KHÔNG loosen assertion. Không chấp nhận thêm giá trị, không giảm độ chính xác, không thêm fallback/or quanh assert.
- **FA-02**: KHÔNG delete/skip/xfail test. Không xóa test, không mark skip/xfail, không comment out.
- **FA-03**: KHÔNG claim Done/Pass khi chưa có full `pytest` output trên exact SHA.
- **FA-04**: KHÔNG tạo simulated/manufactured VERIFIED. Không trả VERIFIED từ stub/mock.
- **FA-05**: KHÔNG self-grant authority.
- **FA-06**: KHÔNG sửa production code trước baseline reconcile.
- **FA-07**: KHÔNG claim maturity từ code/test presence.
- **Exception handling**: Confirm exceptions are no longer swallowed in `reality_test.py`.
- **State isolation**: Confirm state pollution is fully prevented across test runs / autofix runner phases.

## Execution Plan & Agent Assignments
1. **Explorer 1 (`explorer_diff`)**: Investigate git state, commit history on `fix/t09-golden-task-debt`, diff against `main`, identify all touched files, functions, and lines.
2. **Worker 1 (`worker_runtime`)**: Execute `git rev-parse HEAD`, `git status`, `python tools/t00_meta_audit.py`, `pytest tests/`, and any specific T09 tests. Capture verbatim full terminal outputs without truncation to a file.
3. **Auditor (`auditor_integrity`)**: Execute deep forensic audit on the diff against FA-01 through FA-07, verify AST and assertion semantics, check whether any test was loosened, skipped, or mock-verified.
4. **Reviewer / Critic (`reviewer_code`)**: Detailed review of `reality_test.py` and `tests/T09_golden_task` for side effects, exception handling, state pollution prevention, and conformance with SCP DNA.
5. **Orchestrator**: Aggregate all findings, verify raw terminal logs, check all gate criteria, and synthesize the final `AUDIT_REPORT.md`.
