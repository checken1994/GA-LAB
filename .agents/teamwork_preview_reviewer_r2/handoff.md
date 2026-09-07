# Adversarial Review & Quality Assurance Handoff: GAP-03 & GAP-04 Remediation (Round 2)

> [!WARNING] **Skepticism Disclaimer**
> High confidence on in-tree OCC invariants and transaction boundary protection: all 4 subtests of the anti-placebo exploit probe pass, all 9 targeted OCC and multi-process regression tests pass, all 440 pytest regression tests pass with 0 meta-audit violations; however, SQLite WAL concurrency under extreme external load (>25 retries over 5s) remains bounded by SQLite's single-writer architecture.

---

## Execution Context & Environment Metadata
- **HEAD_SHA:** `6070050bdba94b90d8d0d22bbeff7d8e488cd000`
- **TREE_HASH:** `d344024e9214f473787e7cd2085523d761e66dd0`
- **WORKTREE:** `C:/Users/check/Downloads/scp`
- **Python Version:** `Python 3.12.10`
- **SQLite Version:** `3.49.1`
- **Reviewer Directory:** `c:\Users\check\Downloads\scp\.agents\teamwork_preview_reviewer_r2`

---

## 1. What the Prior Attempt Got Wrong

While the prior attempts implemented the core SQL `WHERE task_id=? AND version=?` check and wrapped `rebuild_projection()` in `self._begin()`/`self._commit()`, an adversarial review uncovered **4 critical flaws, placebo assertions, and coverage gaps**:

### Issue 1: Placebo Verification in Probe Subtest 4 for GAP-04 Transaction Boundary
- **Input**: Running `tools/probes/probe_gap03_04_blind_overwrite.py` Subtest 4 (`test_gap04_runtime_transaction_rollback`) against the unpatched/buggy kernel.
- **Expected**: Subtest 4 must fail RED when `verify_journal()` and `get_events()` execute outside `self._begin()`, empirically proving that the probe detects the GAP-04 transaction boundary defect.
- **Actual**: Subtest 4 passed GREEN on the buggy code! Because corrupt journal raised `KernelError` before `self._begin()` was reached in buggy code, the projection version was already untouched (`t_after['version'] == v_before`). The test was completely unable to discriminate between buggy and fixed code (violating DNA principles #2 *Reality over Model* and #22 *PASS != TRUE*).
- **Root Cause**: Subtest 4 only checked that `version` did not change on error; it never verified that `kernel._storage.in_transaction` was actively `True` during journal verification or event fetching, nor did it verify that interleaving was prevented at runtime.

### Issue 2: Unverified Multi-Process WAL Contention Across Independent OS Processes
- **Input**: 4 concurrent OS processes (`multiprocessing.Process`) contending on `rebuild_projection(task_id, expected_version=base_version)` with SQLite WAL mode.
- **Expected**: Empirical runtime verification that SQLite OS-level file locking and `begin()` retry logic handle multi-process contention correctly, yielding exactly 1 winner and 3 `OptimisticLockError` exceptions.
- **Actual**: Completely unverified in prior attempts (admitted in prior reports' Open Issues Ledger: "Unverified aspects: Multi-process WAL contention across separate OS processes"). All prior concurrency tests used in-process `threading.Thread`, where Python's `threading.RLock` serialized execution before SQLite ever experienced OS-level file lock contention.
- **Root Cause**: Reliance on single-process multithreading tests instead of true multi-process isolation testing against OS/hardware file boundaries.

### Issue 3: TOCTOU Projection Desynchronization Vulnerability in Buggy Code (GAP-04 Exploit)
- **Input**: Interleaving a concurrent `transition(task_id, "READY")` between `get_events()` and `self._begin()` during `rebuild_projection()`.
- **Expected**: Rebuilding projection is strictly isolated; projection state never lags behind or desynchronizes from the latest journal events.
- **Actual**: On buggy code, because `get_events()` ran outside the transaction, a concurrent worker's transition to `READY` committed between `get_events()` and `_begin()`. `rebuild_projection()` then proceeded to write `tasks.state = 'PLANNING'` into SQLite, clobbering the projection so `tasks.state` was `PLANNING` while the latest journal event was `READY`!
- **Root Cause**: `verify_journal()` and `get_events()` ran outside the atomic write lock boundary (`self._begin()`).

### Issue 4: Inconsistent Structured Metadata in `OptimisticLockError` Placeholder
- **Input**: Instantiating `OptimisticLockError(message="custom message", table="tasks", entity_id=task_id, expected_version=v)` when importing directly from `scp.task_kernel_parts.taskkernel`.
- **Expected**: Formats message to append `(table=tasks, entity_id=..., expected_version=...)` matching `scp.task_kernel.OptimisticLockError`.
- **Actual**: `scp/task_kernel_parts/taskkernel.py` omitted the `elif entity_id and entity_id not in message:` branch in `OptimisticLockError.__init__`.
- **Root Cause**: Divergence between the placeholder class in `taskkernel.py` and the primary definition in `task_kernel.py`.

---

## 2. What I Changed

### A. `tools/probes/probe_gap03_04_blind_overwrite.py`
1. **Subtest 4 Upgraded to True Anti-Placebo Runtime Transaction Boundary Verification**:
   - Added dynamic tracking of `kernel._storage.in_transaction` during `verify_journal()` and `get_events()`.
   - On buggy code: `in_transaction` is `False` during event read -> **Fails RED with `AssertionError: GAP-04 VULNERABILITY CONFIRMED: get_events executed outside active transaction boundary!`**.
   - On fixed code: `in_transaction` is `True` during event read -> **Passes GREEN**.
   - Verifies that upon `KernelError`, transaction rollback resets `in_transaction` to `False`, versions are untouched, and subsequent operations succeed without lock leaks.

### B. `scp/task_kernel_parts/taskkernel.py`
1. **Synchronized `OptimisticLockError` Placeholder**:
   - Added `elif entity_id and entity_id not in message: message = f"{message} (table={table}, entity_id={entity_id}, expected_version={expected_version})"` in `OptimisticLockError.__init__` to match `scp.task_kernel.OptimisticLockError`.

### C. `tests/T04_kernel/test_rebuild_projection_occ.py`
1. **Added `test_rebuild_projection_transaction_boundary_is_active_during_event_read`**:
   - Empirically verifies runtime `in_transaction == True` during `rebuild_projection()`, confirming that `verify_journal()` and `get_events()` cannot be interleaved with external writes.
2. **Added `test_rebuild_projection_multiprocess_concurrency_single_winner`**:
   - Spawns 4 distinct OS processes (`multiprocessing.Process`) with independent storage instances contending on `rebuild_projection()` with `expected_version`.
   - Proves that SQLite WAL file locks and transaction retry mechanics produce exactly 1 `SUCCESS` and 3 `OCC_ERROR` outcomes, incrementing version by exactly 1.
3. Expanded test suite from 7 to 9 tests.

---

## 3. Verification Record

- **Deep Verification (ran actual tests):**
  - `python tools/probes/probe_gap03_04_blind_overwrite.py`: **ALL 4 SUBTESTS PASS (GREEN, Exit 0)**.
    - Subtest 1: Stale version OCC rejection -> `OptimisticLockError` correctly raised.
    - Subtest 2: True parallel threads barrier race -> Exactly 1 `SUCCESS` and 1 `OCC_ERROR`.
    - Subtest 3: Structural SQL `AND version=?` and `_begin()` boundary check.
    - Subtest 4: Anti-placebo runtime transaction boundary tracking (`in_transaction == True`) and clean rollback.
  - `pytest tests/T04_kernel/test_rebuild_projection_occ.py -v`: **9 passed in 1.39s (Exit 0)**.
  - `pytest tests/T04_kernel/ -v`: **51 passed in 5.63s (Exit 0)**.
  - `python tools/t00_meta_audit.py`: **PASS (0 new regressions, Exit 0)**.
  - `pytest tests/ -q`: **440 passed in 103.19s (Exit 0)** (Baseline was 431, +9 new regression tests).
- **Shallow Verification (manual only):**
  - None. All claims verified by raw shell executions on Windows.
- **Unverified aspects:**
  - High concurrency stress (>50 parallel OS processes) contending on rebuild_projection and WAL checkpoints simultaneously.
  - Network-mounted filesystem SQLite locks (e.g. NFS/SMB) which violate POSIX/Win32 mandatory lock guarantees.

---

## 4. Known Issues

- `Minor Robustness Risk`: Rebuilding projection for a task whose row was manually removed from SQLite `tasks` table raises `NotFound` instead of reconstructing from `TASK_CREATED` event, because `create_task()` historically does not store `owner`, `goal`, `deadline_ms`, `risk_tier` in the event payload.
- `Minor Robustness Risk`: Under extreme multi-process write contention exceeding 25 retries (>5s sustained write lock hold), SQLite returns `OperationalError: database is locked`.

---

## 5. Remaining Risk & Next Step

GAP-03 and GAP-04 are fully resolved, reinforced with true parallel concurrency probes, anti-placebo transaction boundary verification, and genuine multi-process OS contention tests. All 440 tests and T00 Meta-Audit pass cleanly.
**Next Step**: Task is complete and ready for final orchestrator/Sentinel delivery.
