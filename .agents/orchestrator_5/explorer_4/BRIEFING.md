# BRIEFING — 2026-09-07T07:26:00Z

## Mission
Investigate TaskKernel Bridge Lease Lifecycle defect (double-release collision in `task_kernel_bridge.py` line 451), analyze kernel transition behavior, and produce a clear remediation specification.

## 🔒 My Identity
- Archetype: explorer
- Roles: TaskKernel Bridge Lease Lifecycle Specialist
- Working directory: c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_4
- Original parent: 967399d1-d666-4dce-899b-4c2468b6dd91
- Milestone: GAP-07 Iteration 2

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Strictly bound by Zero-Trust and Fail-Closed principles
- Adhere to FA-01 through FA-10
- Enforce boundaries at Database/Hardware level, not via RAM/Variables
- Working language: Tiếng Việt, giữ nguyên technical identifiers

## Current Parent
- Conversation ID: 967399d1-d666-4dce-899b-4c2468b6dd91
- Updated: 2026-09-07T07:26:00Z

## Investigation State
- **Explored paths**: `scp/hands/task_kernel_bridge.py` lines 435–456 & 527–565, `scp/task_kernel_parts/taskkernel.py` lines 328–342, 460–475, 583–625, 667–700, `reviewer_2/handoff.md`, `challenger_2/handoff.md`
- **Key findings**:
  1. `TaskKernel.transition(task_id, 'FAILED')` automatically and atomically executes `UPDATE leases SET released=1...` in the database transaction, clears `tasks.active_lease_id = NULL`, and evicts `_bound_leases`.
  2. Calling `self.kernel.release(task_id, lease.lease_id)` at line 451 invokes `_assert_lease()`, which sees `lease['released'] == 1` and raises `OptimisticLockError`.
  3. This uncaught `OptimisticLockError` triggers `_unknown_result()` at line 533. Inside `record_action_dispatched()`, illegal transition `FAILED->UNKNOWN` and released lease cause secondary crash, returning `error: "Hands bridge could not persist unknown state: OptimisticLockError"`, `requiresRecovery: True`.
  4. Removing line 451 cleanly resolves the defect: task transitions to `FAILED`, lease is released in SQLite, `queue_accounts.active` decremented, `requiresRecovery` is False/None, and PEP denial error is preserved.
- **Unexplored areas**: None. Baseline reproduction, remediation verification, and SQLite invariant checks are complete.

## Key Decisions Made
- Authored isolated verification harness `.agents/orchestrator_5/explorer_4/verify_lease_remediation.py` which proved 100% pass across all database invariants without mutating product code directly.
- Formulated concrete remediation patch and mandatory regression test for `tests/T04_kernel/test_kernel_p1_regressions.py`.

## Artifact Index
- `.agents/orchestrator_5/explorer_4/DISPATCH.md` — Incoming dispatch log
- `.agents/orchestrator_5/explorer_4/BRIEFING.md` — Situational awareness
- `.agents/orchestrator_5/explorer_4/progress.md` — Execution progress
- `.agents/orchestrator_5/explorer_4/verify_lease_remediation.py` — Verification probe script
- `.agents/orchestrator_5/explorer_4/handoff.md` — Final investigation & remediation specification
