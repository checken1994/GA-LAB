# Adversarial Review & Quality Assurance Handoff: GAP-03 & GAP-04 Remediation (Round 3)

> [!WARNING] **Skepticism Disclaimer**
> High confidence on in-tree OCC invariants, transaction boundaries, and lease lifecycle persistence: all 4 anti-placebo exploit probe subtests pass, all 10 targeted OCC and concurrency regression tests pass (including newly added lease lifecycle and terminal state preservation tests), all 441 pytest regression tests pass with 0 failures, and 0 meta-audit violations exist; SQLite WAL concurrency remains subject to single-writer serialized write-lock contention under prolonged extreme pressure (>25 retries over 5s).

---

## Execution Context & Environment Metadata
- **HEAD_SHA:** `6070050bdba94b90d8d0d22bbeff7d8e488cd000`
- **TREE_HASH:** `d344024e9214f473787e7cd2085523d761e66dd0`
- **WORKTREE:** `C:/Users/check/Downloads/scp`
- **Python Version:** `Python 3.12.10`
- **SQLite Version:** `3.49.1`
- **Reviewer Directory:** `c:\Users\check\Downloads\scp\.agents\teamwork_preview_reviewer_r3`

---

## 1. What the Prior Attempt Got Wrong

While Round 2 successfully fixed the placebo assertion in Probe Subtest 4, synchronized `OptimisticLockError` attributes, and added multi-process concurrency testing, our Round 3 adversarial scrutiny identified **3 test coverage gaps and edge-case behaviors**:

### Issue 1: Missing Verification of Lease & Fencing Token Persistence Across Rebuilds
- **Input**: A task in `LEASED` or `RUNNING` state with an active lease and fencing token undergoes `rebuild_projection(task_id)`.
- **Expected**: Rebuilding the projection restores `active_lease_id` and `active_fencing_token` from unreleased lease rows, preserving worker authority and fencing invariants.
- **Actual**: Completely untested in `test_rebuild_projection_occ.py`. All prior 9 test cases only set up tasks in `PLANNING` (an unleased state). There was no test ensuring that active leases survive projection rebuilding or that released leases are properly cleared in the projection.
- **Root Cause**: Reliance on a single setup fixture (`_setup_task_in_planning`) across all test cases.

### Issue 2: Untested Administrative Terminal State Handling and Negative Version Rejection
- **Input**: A caller provides negative `expected_version` (e.g. `-1`), or attempts `rebuild_projection()` on a task transitioning to terminal states (`CANCELLED`).
- **Expected**: Negative versions fail closed immediately with `OptimisticLockError(table='tasks', entity_id=task_id, expected_version=-1)`. Rebuilding on terminal states cleanly clears active lease tokens and preserves immutable terminal status.
- **Actual**: Neither negative versions nor terminal state rebuilding had dedicated regression assertions in `test_rebuild_projection_occ.py`.
- **Root Cause**: Scope limitation in test suite generation during implementer and reviewer r2 rounds.

### Issue 3: Incomplete Exploit Mutation Validation Across All Buggy Variations
- **Input**: Mutating `rebuild_projection` into various historic buggy permutations: (a) missing `expected_version` parameter, (b) blind version increment ignoring version comparison, (c) running `verify_journal` and `get_events` outside `self._begin()`.
- **Expected**: Independent adversarial verification that each distinct defect reliably trips the probe into RED exit status.
- **Actual**: Round 2 verified Subtest 4 anti-placebo behavior, but did not document execution of the probe against blind-increment and parameter-omission mutations.
- **Root Cause**: Lack of multi-permutation mutation testing in prior review cycles.

---

## 2. What I Changed

### A. `tests/T04_kernel/test_rebuild_projection_occ.py`
Added `test_rebuild_projection_lease_lifecycle_and_terminal_states`:
1. **Active Lease Preservation**: Verifies that when a task is `LEASED` or `RUNNING` with an active lease, `rebuild_projection` preserves `active_lease_id` and `active_fencing_token` while incrementing version.
2. **Released Lease Clearing**: Verifies that when a lease is released via `kernel.release()`, rebuilding projection resets `active_lease_id` to `None` and `active_fencing_token` to `0`.
3. **Terminal State Preservation**: Verifies that terminal tasks (`CANCELLED`) preserve terminal state with cleared lease metadata.
4. **Negative Version Rejection**: Verifies that negative `expected_version` (`-1`) fails closed with `OptimisticLockError(table="tasks", entity_id=task_id, expected_version=-1)`.
5. Expanded test suite from 9 to 10 tests.

### B. Anti-Placebo Mutation Testing
Empirically executed mutation tests against all three buggy permutations:
1. Permutation A (no `expected_version` in signature): Probe Subtest 1 fails RED with `AssertionError: GAP-03 VULNERABILITY CONFIRMED: rebuild_projection does not support or enforce expected_version OCC check!`.
2. Permutation B (accepts `expected_version` but blind `UPDATE` without `AND version=?`): Probe Subtest 1 fails RED (`Blind overwrite occurred: version jumped`), Probe Subtest 2 fails RED (`Both concurrent workers succeeded! Blind overwrite occurred`).
3. Permutation C (`verify_journal` and `get_events` outside `self._begin()`): Probe Subtest 4 fails RED with `AssertionError: GAP-04 VULNERABILITY CONFIRMED: get_events executed outside active transaction boundary! Observations: [False]`.
4. Fixed Code: All 4 probe subtests pass GREEN (Exit 0).

---

## 3. Verification Record

- **Deep Verification (ran actual tests):**
  - `python tools/probes/probe_gap03_04_blind_overwrite.py`: **ALL 4 SUBTESTS PASS (GREEN, Exit 0)**.
    - Subtest 1: Stale version OCC rejection -> `OptimisticLockError` correctly raised.
    - Subtest 2: True parallel threads barrier race -> Exactly 1 `SUCCESS` and 1 `OCC_ERROR`.
    - Subtest 3: Structural SQL `AND version=?` and `_begin()` boundary check.
    - Subtest 4: Anti-placebo runtime transaction boundary tracking (`in_transaction == True`) and clean rollback.
  - `pytest tests/T04_kernel/test_rebuild_projection_occ.py -v`: **10 passed in 1.83s (Exit 0)**.
  - `pytest tests/ -q`: **441 passed in 110.38s (Exit 0)** (Baseline 431, +10 new regression tests).
  - `python tools/t00_meta_audit.py`: **PASS (0 new regressions, Exit 0)**.
- **Shallow Verification (manual only):** None. All verifications performed via raw terminal execution on Windows.
- **Unverified aspects:**
  - High concurrency stress (>50 parallel OS processes) contending on rebuild_projection and WAL checkpoints simultaneously.
  - Network-mounted filesystem SQLite locks (e.g. NFS/SMB) which violate POSIX/Win32 mandatory lock guarantees.

---

## 4. Known Issues

- `Minor Robustness Risk`: Rebuilding projection for a task whose row was manually dropped from SQLite `tasks` table raises `NotFound` instead of reconstructing from `TASK_CREATED` event, because `create_task()` historically does not store `owner`, `goal`, `deadline_ms`, `risk_tier` in the event payload.
- `Minor Robustness Risk`: Under extreme multi-process write contention exceeding 25 retries (>5s sustained write lock hold), SQLite returns `OperationalError: database is locked`.

---

## 5. Remaining Risk & Next Step

GAP-03 and GAP-04 are fully resolved, backed by anti-placebo exploit probes, multi-process concurrency tests, lease lifecycle preservation tests, and clean transaction rollback guarantees. All 441 tests and T00 Meta-Audit pass cleanly.
**Next Step**: Task is complete and ready for final orchestrator/Sentinel delivery.
