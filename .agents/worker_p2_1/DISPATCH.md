# Dispatch Log — Worker P2-1 (OCC Implementation & Verification)

## 2026-09-06T17:03:00Z

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You are Worker P2-1 (`teamwork_preview_worker`).
Working directory: c:\Users\check\Downloads\scp\.agents\worker_p2_1
Parent Orchestrator: orchestrator_3 (Conv ID: 4aab71c9-e6ee-472b-8c41-c64e48735a24)

Mandatory reading:
- c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
- c:\Users\check\Downloads\scp\GA.md
- c:\Users\check\Downloads\scp\.agents\orchestrator_3\SCOPE.md
- c:\Users\check\Downloads\scp\.agents\explorer_p2_1\handoff.md
- c:\Users\check\Downloads\scp\.agents\explorer_p2_2\handoff.md
- c:\Users\check\Downloads\scp\.agents\explorer_p2_3\handoff.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md

FILE EXCLUSIVE OWNERSHIP:
- `scp/task_kernel.py`
- `scp/task_kernel_parts/taskkernel.py`
- `tests/T04_kernel/test_satellite_occ_anti_placebo.py` (new)

MISSION:
Implement atomic OCC (`WHERE version=?`) and Invariant INV-01 across satellite tables (`leases`, `idempotency`, `queue_accounts`) and fix residual blind overwrite in `tasks:293`.
1. Exception Hierarchy: Define `class OptimisticLockError(StaleLease): pass` in `scp/task_kernel.py` and export it in `__all__` in both `scp/task_kernel.py` and `scp/task_kernel_parts/taskkernel.py`.
2. Schema Evolution: Update `TaskKernel._schema()` in `scp/task_kernel_parts/taskkernel.py` to add `version INTEGER NOT NULL DEFAULT 1` to `leases`, `idempotency`, and `queue_accounts`. Add dynamic `PRAGMA table_info` migration check so existing databases are automatically migrated via `ALTER TABLE ... ADD COLUMN version INTEGER NOT NULL DEFAULT 1`.
3. OCC on Satellite UPDATEs:
   - Update `heartbeat`: require version matching (`WHERE lease_id=? AND released=0 AND version=?`), increment `version=version+1`. Raise `OptimisticLockError` if `cur.rowcount != 1`.
   - Update `release`: require version matching (`WHERE lease_id=? AND released=0 AND version=?`), increment `version=version+1`.
   - Update `idempotency_claim`: when claiming from `RETRYABLE` to `CLAIMED`, enforce `WHERE logical_key=? AND status='RETRYABLE' AND version=?`, increment `version=version+1`. If `cur.rowcount != 1`, raise `OptimisticLockError` or handle atomically.
   - Update `idempotency_complete`: enforce `WHERE logical_key=? AND status='CLAIMED' AND version=?`, increment `version=version+1`. Raise `OptimisticLockError` if `cur.rowcount != 1`.
   - Fix `tasks:293`: in `claim_next` deadline check, add `AND version=?` to the UPDATE query.
4. Mutation Anti-Placebo Test Suite:
   - Create `tests/T04_kernel/test_satellite_occ_anti_placebo.py` testing Mutants M1 to M4 per Explorer P2-3 design.
5. Verification:
   - Run `python .agents/explorer_p2_3/probe_satellite_blind_overwrite.py --verify-fix` -> must PASS with exit code 0.
   - Run `pytest tests/T04_kernel/test_satellite_occ_anti_placebo.py -v` -> must PASS.
   - Run `pytest tests/ -q` -> must PASS (100% green, 0 broken tests).
   - Run `python tools/t00_meta_audit.py` -> must PASS (0 violations).
6. Document all changes and verification outputs in `c:\Users\check\Downloads\scp\.agents\worker_p2_1\handoff.md`.
7. Report completion to parent orchestrator.
