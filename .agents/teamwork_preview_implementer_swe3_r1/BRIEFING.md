# Briefing — teamwork_preview_implementer_swe3_r1

## Mission
Refinement & Adversarial Reviewer Round 1 for GAP-11 remediation in `TaskKernel` (`scp/task_kernel_parts/taskkernel.py`).

## Role & Objectives
1. Actively attempt to BREAK the current implementation and test edge cases (e.g., edge cases in `transition()`, OCC versions, `rebuild_projection()`, state machine boundaries).
2. Verify that FA-11 (Peripheral Audit & Anti-Scope Creep) and FA-12 (Empirical Causal Closure) evidence standards are strictly satisfied.
3. Check if any fixes or additional adversarial tests are needed to ensure regression-proof robustness.
4. Report detailed verification records and handoff report to `handoff.md` and send report back to parent orchestrator (`teamwork_preview_swe_3`).

## Key Invariants
- Zero-Trust & Fail-Closed
- FA-01 through FA-13 strict adherence
- Database/Hardware level enforcement (not just RAM/Variables)
- Zero Scope Creep (GAP-12/GAP-13 remain documented in EMERGENCY_GAP_REPORT.md, not secretly patched)
