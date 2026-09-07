# Implementation Briefing — GAP-11 Remediation

## Executive Objective
Remediate GAP-11 (Fake PASS Bypass) in `TaskKernel` and strictly enforce the FA-11 (Peripheral Audit) and FA-12 (Empirical Causal Closure) protocols.

## Assigned Requirements
1. **R1. Eliminate GAP-11:** In `scp/task_kernel_parts/taskkernel.py`, `transition()` must strictly block any transition to `COMPLETED` by raising `InvalidTransition`. Transition to `COMPLETED` is exclusively permitted via `commit_completed()` with valid evidence.
2. **R2. Peripheral Audit (FA-11) & Causal Graph:** Full Mermaid Causal Graph for `taskkernel.py`. Scan peripheral states (`FAILED`, `CANCELLED`, `WAITING_APPROVAL`, etc.) for similar gaps. Generate `EMERGENCY_GAP_REPORT.md` without stealth patches (zero scope creep).
3. **R3. Empirical Evidence (FA-12):** Execute `tools/probes/probe_gap11.py`, inspect raw SQLite data to prove DB boundary enforcement, establish end-to-end empirical proof.
4. **Regression & Meta-Audit:** All 66 tests in `tests/T04_kernel/` must PASS; `tools/t00_meta_audit.py` must pass with 0 new regressions.
5. **Traceability:** Check/update `spec/scp_target_test_coverage.yaml`.
6. **Commit & Push:** `fix(security): GAP-11 block raw COMPLETED transition` pushed to `main`.
