# Progress: Adversarial Review & QA Round 3 (GAP-03 & GAP-04 Remediation)

## Current Status: ALL REQUIREMENTS SATISFIED, EXPLOIT PROBES GREEN, 441 TESTS PASSING

### 1. Step 1 - Independent Understanding
- Read `GA.md`, `scp-dna`, `scp-task-kernel-review`, and `scp-reality-verifier`.
- Formed independent threat model for GAP-03 and GAP-04 in `rebuild_projection()`:
  1. GAP-03: Blind Version Increment (`UPDATE tasks SET ... WHERE task_id=?` missing `AND version=?`). Must query current version, validate against `expected_version` (raise `OptimisticLockError`), and enforce atomic OCC match with `cur.rowcount == 1`.
  2. GAP-04: Transaction Boundary (`rebuild_projection()` missing full transaction wrapping). Must wrap `verify_journal()` and `get_events()` inside `self._begin()` / `self._commit()`, with clean rollback on error.

### 2. Step 2 - Break It (Adversarial Probing & Anti-Placebo Validation)
- Validated probe behavior across 3 distinct buggy permutations:
  - Permutation A (no `expected_version` parameter): Subtest 1 FAILS RED (`TypeError`).
  - Permutation B (blind increment without `AND version=?`): Subtest 1 FAILS RED (version jump without `OptimisticLockError`), Subtest 2 FAILS RED (both parallel threads succeed).
  - Permutation C (`verify_journal` and `get_events` run outside `self._begin()`): Subtest 4 FAILS RED (`get_events executed outside active transaction boundary! Observations: [False]`).
- Identified missing test coverage for lease lifecycle persistence during rebuilds and negative version inputs.

### 3. Step 3 - Fix & Fortify
- Added `test_rebuild_projection_lease_lifecycle_and_terminal_states` in `tests/T04_kernel/test_rebuild_projection_occ.py`:
  - Active lease and fencing token preservation when rebuilding `LEASED` / `RUNNING` tasks.
  - Clearing of active lease tokens when lease is released.
  - Terminal state (`CANCELLED`) persistence with cleared lease tokens.
  - Negative version (`expected_version=-1`) rejection with `OptimisticLockError`.

### 4. Step 4 - Re-verify
- `tools/probes/probe_gap03_04_blind_overwrite.py`: 4/4 subtests PASS GREEN.
- `tests/T04_kernel/test_rebuild_projection_occ.py`: 10/10 tests PASS in 1.83s.
- `tools/t00_meta_audit.py`: PASS (0 new regressions, trusted base `origin/main`).
- `pytest tests/ -q`: 441 passed in 110.38s (100% full repository test suite green).
