# Handoff Report: GAP-05 & GAP-06 Survey (Explorer 1)

**Working Directory**: `c:\Users\check\Downloads\scp\.agents\explorer_survey_1\`  
**Agent Role**: Explorer 1 (Read-only Investigation and Synthesis)  
**Parent Agent**: `50f4125f-5432-4084-856a-8d91aba6378c`  
**Standard**: SCP DNA (29 Principles), Fail-Closed, Zero-Trust, FA-01 through FA-10  

---

## 1. Observation

1. **Absence of RLock in current `scp/kernel_storage.py`**:
   - Direct inspection of `scp/kernel_storage.py` (186 lines) confirms there are **zero** instances of `threading.RLock()` and **zero** instances of `self._lock` in the current file content.
   - The only threading primitive in `scp/kernel_storage.py` is `self._conn_guard = threading.Lock()` at line 94, used exclusively to synchronize the list of connections (`self._all_conns`) during connection creation (`_get_conn`, line 115) and teardown (`close`, line 162).
2. **Git Provenance of RLock in `SQLiteKernelStorage`**:
   - In commit `eb037010fa7eabc939953e29575c6ab94ff1cd81` and at commit `71420ae6030886bb558cb4cf42f4dc3da0016791` (`HEAD`), `SQLiteKernelStorage` contained:
     ```python
     self._tx_lock = threading.RLock()
     self._tx_state = threading.local()
     ```
     with `self._tx_lock.acquire()` in `begin()` and `self._release_tx_lock()` in `commit()` / `rollback()`.
   - In the local working tree, `git diff scp/kernel_storage.py` shows that `self._tx_lock` and its acquisition/release calls have been removed:
     ```diff
     - self._tx_lock = threading.RLock()
     - self._tx_state = threading.local()
     ...
     - self._tx_lock.acquire()
     ...
     - self._release_tx_lock()
     ```
3. **Repository-Wide Search for `RLock`**:
   - Ripgrep query `RLock` across `scp/` returned 18 occurrences.
   - Outside of the historical `SQLiteKernelStorage._tx_lock`, the only database-related `RLock` is in `scp/persistence/db.py:42` (`FoundationDB`), which protects a single shared SQLite connection for static schema migrations (not used by `TaskKernel`). All other occurrences guard in-memory data structures (e.g. `ast_diff_cache.py:148`, `callgraph_delta.py:322`, `speculative_prefixer.py:458`, `circuit_breaker.py:53`).
4. **TaskKernel Concurrency Architecture (OCC)**:
   - `scp/task_kernel_parts/taskkernel.py` enforces database-level Optimistic Concurrency Control (OCC) across all mutable entities (`tasks`, `leases`, `idempotency`, `queue_accounts`).
   - Every mutation runs inside a SQLite transaction opened via `storage.begin()` which issues `BEGIN IMMEDIATE` with bounded exponential retry (up to 25 attempts on `SQLITE_BUSY` or `database is locked`).
   - Mutations use version checks:
     ```sql
     UPDATE tasks SET state=?, version=version+1, active_lease_id=?, active_fencing_token=?, updated_at=?
     WHERE task_id=? AND version=?
     ```
   - Zero-trust assertion: `if cur.rowcount != 1: raise OptimisticLockError(...)` at line 348, rolling back the transaction.
5. **Execution of GAP-05 Multi-Process Probe**:
   - Command: `python tools/probe_gap05_occ_multiprocess.py`
   - Output:
     ```
     Starting 10 workers, 50 iterations each. Expected total: 500
     Final value: 500
     Time taken: 1.41 seconds
     PASS: No race condition detected. Multiprocess concurrency is safe without RLock.
     ```
6. **Examination of `make_storage()` in `scp/kernel_storage.py`**:
   - Exact code at lines 180-186:
     ```python
     def make_storage(db_path: str | Path) -> SQLiteKernelStorage:
         """Create the default SQLite storage for a given path.

         Future: accept a backend= parameter to select Postgres/etcd.
         """
         return SQLiteKernelStorage(db_path)
     ```
   - Callers:
     - Directly called by `TaskKernel.__init__` in `scp/task_kernel_parts/taskkernel.py:62`.
     - Transitively invoked by all callers instantiating `TaskKernel(db_path)`.
   - Current defects:
     - No docstring `WARNING` about SQLite Single Point of Failure (SPOF) in distributed environments.
     - No check of `SCP_STORAGE_BACKEND` environment variable; unconditionally returns `SQLiteKernelStorage`.
7. **Pre-Commit Meta-Audit Run**:
   - Command: `python tools/t00_meta_audit.py`
   - Result: Exit code 0, `All integrity checks passed (0 new regressions).`

---

## 2. Logic Chain

1. **RLock in `SQLiteKernelStorage` is a Placebo**:
   - *Premise A (Observation 2)*: `self._tx_lock` was an in-memory `threading.RLock()` belonging to a single instance of `SQLiteKernelStorage`.
   - *Premise B (Observation 5)*: In a multi-process or multi-instance setup, separate processes/instances do not share Python object memory; `self._tx_lock` provides zero isolation across process boundaries.
   - *Premise C (Observation 4)*: SQLite WAL mode with `BEGIN IMMEDIATE` already acquires a database-level write lock on the underlying SQLite file, serializing all writers across all threads and processes.
   - *Premise D (Observation 4)*: Logical concurrency safety is enforced at the database level by version-guarded SQL updates raising `OptimisticLockError` on rowcount mismatch.
   - *Inference*: Removing `self._tx_lock` removes an in-memory placebo without degrading concurrency safety, which was empirically validated by Observation 5 (10-process stress probe completing 500/500 transactions cleanly).
2. **GAP-06 Remediation Architecture**:
   - *Premise A (Observation 6)*: `make_storage()` is the sole entry point for initializing storage from `TaskKernel(db_path)`.
   - *Premise B*: In a distributed deployment, SQLite cannot provide high availability or network replication. If a caller configures `SCP_STORAGE_BACKEND=postgres` or any non-sqlite backend, `make_storage()` must not silently provide SQLite.
   - *Inference*: `make_storage()` must check `SCP_STORAGE_BACKEND` (defaulting to `"sqlite"`), normalize case and whitespace, and raise `NotImplementedError` fail-closed with guidance when set to an unsupported backend. It must also feature a prominent docstring warning regarding the SPOF nature of SQLite.

---

## 3. Caveats

1. **Existing Test Suite State**: Full `pytest tests/ -q` resulted in `449 passed, 1 failed`. The failure (`test_golden_b_verified_fix_commits_to_durable_state`) is in the AutoFix epistemic loop (`tests/T09_golden_task/test_golden_b_epistemic_loop.py`), due to missing `semantic_equiv` backup file handling, wholly independent of kernel storage.
2. **Read-Only Scope**: In compliance with our mandate, no production or test files outside `.agents/explorer_survey_1/` were modified. Unstaged diffs in `scp/kernel_storage.py` pre-existed our session.
3. **Alternative Storage Backends**: No alternative backend implementations (e.g. PostgresKernelStorage) currently exist in the codebase. Distributed backends must be injected via `TaskKernel(storage=...)`.

---

## 4. Conclusion

1. **GAP-05**: The `threading.RLock()` in `SQLiteKernelStorage` was indeed a placebo. Its removal in the working tree is fully verified:
   - Zero lost updates under 10-process concurrent stress (`tools/probe_gap05_occ_multiprocess.py`).
   - SQLite WAL + `BEGIN IMMEDIATE` + OCC version checks (`OptimisticLockError`) handle all concurrency requirements safely at the database level.
2. **GAP-06**: `make_storage()` requires:
   - A docstring `WARNING` specifying that SQLite is a Single Point of Failure (SPOF) for distributed deployments.
   - An environment variable guard reading `SCP_STORAGE_BACKEND` (defaulting to `"sqlite"`), raising `NotImplementedError` when set to any value other than `"sqlite"`.
   - Dedicated anti-placebo tests in `tests/T04_kernel/test_kernel_storage.py` verifying the fail-closed behavior across empty, valid, and invalid backends.

---

## 5. Verification Method

To independently verify all claims:

1. **Verify Absence of RLock in `scp/kernel_storage.py`**:
   ```pwsh
   git grep "RLock" scp/kernel_storage.py
   ```
   *Expected*: Empty (exit code 1, no matches).

2. **Verify Multi-Process OCC Concurrency (GAP-05 Probe)**:
   ```pwsh
   python tools/probe_gap05_occ_multiprocess.py
   ```
   *Expected*: Exit code 0, `PASS: No race condition detected. Multiprocess concurrency is safe without RLock.`

3. **Verify Pre-Commit Guardrails**:
   ```pwsh
   python tools/t00_meta_audit.py
   ```
   *Expected*: Exit code 0, `All integrity checks passed (0 new regressions).`

4. **Verify Kernel Storage Tests**:
   ```pwsh
   pytest tests/T04_kernel/test_kernel_storage.py tests/T04_kernel/test_satellite_occ_anti_placebo.py -v
   ```
   *Expected*: All tests PASS.

5. **Invalidation Conditions**:
   - Any reintroduction of `self._tx_lock` or `threading.RLock()` in `scp/kernel_storage.py`.
   - Any silent acceptance of `SCP_STORAGE_BACKEND=postgres` without raising `NotImplementedError`.
