# Comprehensive Analysis: GAP-05 (RLock Placebo Verification) & GAP-06 (SQLite SPOF Guard)

**Date**: 2026-09-07  
**Agent**: Explorer 1 (`.agents/explorer_survey_1/`)  
**Mission**: Read-only exploration and anti-placebo design for GAP-05 and GAP-06  
**Standards Applied**: SCP DNA (29 Principles), Zero-Trust, Fail-Closed, FA-01 through FA-10  

---

## 1. Executive Summary

- **GAP-05 (RLock Placebo)**:
  - In commit `eb03701` and present at `HEAD` (`71420ae`), `SQLiteKernelStorage` in `scp/kernel_storage.py` contained `self._tx_lock = threading.RLock()`, acquired in `begin()` and released in `commit()`/`rollback()`.
  - An exhaustive survey confirms that `self._tx_lock` was an in-memory **placebo**:
    1. It only protected threads within a single Python process and within the same object instance. Multiple processes or multiple `TaskKernel` instances connecting to the same SQLite database received zero protection from `self._tx_lock`.
    2. SQLite WAL mode with `BEGIN IMMEDIATE` already serializes write transactions across all connections and all processes at the file/engine level.
    3. `TaskKernel` enforces database-level Optimistic Concurrency Control (OCC) (`UPDATE ... SET version=version+1 WHERE ... AND version=?` checking `rowcount == 1`), which detects and aborts conflicting concurrent state mutations with `OptimisticLockError`.
  - In the current working tree, `self._tx_lock` has been removed from `scp/kernel_storage.py`. An adversarial multi-process test probe (`tools/probe_gap05_occ_multiprocess.py`, 10 workers x 50 iterations = 500 atomic transactions) verifies 100% data integrity without any in-memory lock.
  - No other storage locks exist in `scp/kernel_storage.py`. All other `RLock` instances across `scp/` are either in `FoundationDB` (protecting a single shared SQLite connection for static schema migrations) or in memory caches/state trackers.

- **GAP-06 (SQLite SPOF Documentation + Guard)**:
  - `make_storage()` in `scp/kernel_storage.py` is the factory function creating the storage backend for `TaskKernel`.
  - It currently instantiates `SQLiteKernelStorage(db_path)` directly with no docstring WARNING regarding SQLite being a Single Point of Failure (SPOF) in distributed environments, and no validation of the target backend.
  - All calls to `TaskKernel(db_path)` (across tests, acceptance scripts, soak tests, and audit runners) route directly through `make_storage()`.
  - Remediation requires:
    1. Adding an explicit, prominent docstring `WARNING` detailing that SQLite lacks distributed consensus, multi-host replication, and high availability.
    2. Introducing an environment variable guard `SCP_STORAGE_BACKEND` (defaulting to `"sqlite"`), raising `NotImplementedError` fail-closed when set to anything other than `"sqlite"` (e.g. `"postgres"`, `"etcd"`, `"redis"`).
    3. Adding an anti-placebo test suite validating the guard across valid, default, and invalid backend configurations.

---

## 2. GAP-05: In-Depth Investigation

### 2.1 Codebase Survey for `threading.RLock()` and `self._lock`

An exhaustive AST and pattern search across `scp/` revealed 18 occurrences of `RLock`:

| File Path | Line Number | Identifier / Usage | Purpose / Classification |
|---|---|---|---|
| `scp/kernel_storage.py` (HEAD `71420ae`) | 95, 123, 142 | `self._tx_lock = threading.RLock()` | **The GAP-05 Placebo Lock** (removed in working tree diff). |
| `scp/persistence/db.py` | 42, 53, 84, 94, 98, 107 | `self._lock = threading.RLock()` | `FoundationDB`: serializes access to a single shared `_conn` for static DDL migrations. Not used by `TaskKernel`. |
| `scp/core/db_manager.py` | 27, 141, 151 | `_db_lock = threading.RLock()` | Global lock for legacy `v13.db` database operations. |
| `scp/autofix/speculative_prefixer.py` | 458 | `self._lock = threading.RLock()` | RAM cache guard for speculative AST edits. |
| `scp/autofix/callgraph_delta.py` | 322 | `self._lock = threading.RLock()` | RAM cache guard for callgraph diffs. |
| `scp/knowledge/source_reputation.py` | 125 | `self._lock = threading.RLock()` | RAM dict guard for source reputation metrics. |
| `scp/autofix/ast_diff_cache.py` | 148 | `self._lock = threading.RLock()` | RAM dict guard for AST diff cache. |
| `scp/autofix/policy_gate.py` | 328, 499 | `self._lock = threading.RLock()` | Guard for dynamic policy rules and verdicts. |
| `scp/core/partition/rotate.py` | 47 | `self._lock = threading.RLock()` | Partition rotation lock for legacy db partitions. |
| `scp/core/smart_cache.py` | 105 | `cls._instance._entry_lock = threading.RLock()` | RAM cache entry lock. |
| `scp/core/request_run_ledger.py` | 102 | `self._lock = threading.RLock()` | Thread-safe run ledger history in memory. |
| `scp/core/subsystem_telemetry.py` | 75 | `self._lock = threading.RLock()` | Subsystem metrics and telemetry aggregation. |
| `scp/security/response_monitor.py` | 159 | `self._lock = threading.RLock()` | Security response monitoring state. |
| `scp/autofix/runner_phases/auto_rollback.py` | 151 | `self._lock = threading.RLock()` | Auto-rollback phase watcher list guard. |
| `scp/security/circuit_breaker.py` | 53 | `self.lock = threading.RLock()` | Circuit breaker failure count state. |
| `scp/security/capability_epoch.py` | 89 | `self._lock = threading.RLock()` | Capability epoch state transition lock. |
| `scp/security/attack_memory.py` | 105 | `self._lock = threading.RLock()` | Attack memory bypass rules cache. |

**Key Finding**: No other locks exist in `scp/kernel_storage.py` except `self._conn_guard = threading.Lock()`, which is strictly used for thread-safe appending to `self._all_conns` during connection creation and iteration during `close()`.

### 2.2 Call Graph & Execution Trace: Storage Concurrency Control

The concurrency control architecture in `TaskKernel` and `SQLiteKernelStorage` follows a multi-tier database-enforced design:

```
[Caller / Worker]
       │
       ▼ (1) transition(), claim(), heartbeat(), idempotency_claim(), etc.
┌─────────────────────────────────────────────────────────────┐
│ TaskKernel (scp/task_kernel_parts/taskkernel.py)           │
│                                                             │
│  - _begin()                                                 │
│       │                                                     │
│       ▼                                                     │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ KernelStorage.begin()                                 │  │
│  │ (SQLiteKernelStorage in scp/kernel_storage.py)        │  │
│  │                                                       │  │
│  │  1. Get thread-local conn (_conn_local.conn)          │  │
│  │  2. Loop (up to 25 attempts):                         │  │
│  │       execute("BEGIN IMMEDIATE")                      │  │
│  │       - SQLite acquires RESERVED lock on DB file.     │  │
│  │       - On SQLITE_BUSY / locked: backoff & retry.     │  │
│  │       - Readers continue via WAL snapshots without     │  │
│  │         blocking writer.                              │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  - Query current version:                                   │
│       row = conn.execute("SELECT version FROM ...")         │
│       cur_version = int(row["version"])                     │
│                                                             │
│  - Atomic OCC Update:                                       │
│       cur = conn.execute(                                   │
│           "UPDATE <table> SET ..., version=version+1        │
│            WHERE <id>=? AND version=?",                     │
│           (..., entity_id, cur_version)                     │
│       )                                                     │
│                                                             │
│  - Rowcount verification (Zero-Trust):                      │
│       if cur.rowcount != 1:                                 │
│           raise OptimisticLockError(...)                    │
│           (triggers rollback: conn.execute("ROLLBACK"))     │
│                                                             │
│  - Audit log append:                                        │
│       _append_event(task_id, event_type, ...)               │
│                                                             │
│  - _commit():                                               │
│       conn.execute("COMMIT")                                │
│       (releases SQLite RESERVED lock at database level)     │
└─────────────────────────────────────────────────────────────┘
```

#### Detailed Execution Trace: State Transition (`transition_state`)
1. **Entry**: Caller invokes `TaskKernel.transition(task_id, to_state, actor="worker-1", reason="step-done")`.
2. **State Machine Validation**: `self._validate_transition(old_state, to_state)` asserts transition is valid in `ALLOWED_TRANSITIONS`.
3. **Transaction Acquisition**:
   - `self._begin()` -> `self._storage.begin()`.
   - `_get_conn()` retrieves the calling thread's isolated connection from `self._conn_local`.
   - Executes `BEGIN IMMEDIATE`. This requests an immediate write lock in SQLite WAL mode. Other readers are not blocked, but concurrent write transactions from other threads or processes are queued/blocked until this transaction completes or timeout expires.
4. **Current State Read**:
   - `task = self._task(task_id)`.
   - Extracts `cur_version = int(task["version"])`.
5. **Conditional OCC Update**:
   - Executes:
     ```sql
     UPDATE tasks
     SET state=?, version=version+1, active_lease_id=?, active_fencing_token=?, updated_at=?
     WHERE task_id=? AND version=?
     ```
     passing `cur_version` as the guard condition.
6. **Conflict Detection**:
   - Inspects `cur.rowcount`.
   - If another transaction committed a version increment between step 4 and step 5, `cur.rowcount == 0`.
   - Instantly raises `OptimisticLockError(table="tasks", entity_id=task_id, expected_version=cur_version)`.
   - In the `except Exception:` block, calls `self._rollback()` -> `_get_conn().execute("ROLLBACK")` -> re-raises.
7. **Hash-Chained Event Append**:
   - If `cur.rowcount == 1`, generates sha256 hash of previous event and inserts new event into `events` table.
8. **Commit**:
   - Calls `self._commit()` -> `_get_conn().execute("COMMIT")`. The write lock is released.

### 2.3 Why `RLock` Was an Anti-Pattern / Placebo Lock

1. **Process Boundary Blindness**: `threading.RLock()` is an in-memory lock local to a single Python process. A real Agent OS or distributed agent cluster runs multiple worker processes, subagent processes, or background daemons. `RLock` cannot synchronize or protect across processes.
2. **Instance Boundary Blindness**: If two components instantiate `TaskKernel(db_path)` or `SQLiteKernelStorage(db_path)` on the same SQLite file within the same process, each has its own independent `self._tx_lock`. The locks do not coordinate.
3. **Redundant with Engine-Level Locking**: SQLite WAL mode natively handles multi-connection write serialization via `BEGIN IMMEDIATE` and `PRAGMA busy_timeout=10000`. The retry loop in `begin()` already provides bounded retries on `SQLITE_BUSY`.
4. **Redundant with Application-Level OCC**: In an asynchronous or multi-step workflow, locking `begin()` only serializes the physical SQLite write transaction. It does NOT prevent logical races where two workers read version $N$ at different times. Logical consistency is guaranteed exclusively by the atomic OCC query (`WHERE version=?`) and fencing tokens (`active_fencing_token`).
5. **False Sense of Security (Placebo)**: The presence of `_tx_lock` created an illusion of concurrency safety in RAM, obscuring the fact that true concurrency guarantees come from SQLite WAL `BEGIN IMMEDIATE` + OCC version checks at the database layer.

### 2.4 Concrete Verification & Anti-Placebo Evidence (FA-09)

To satisfy FA-09 (Exploit Mandate):
- **Evidence of Absence**: `git diff scp/kernel_storage.py` confirms that `self._tx_lock` and `self._tx_state` have been removed from `SQLiteKernelStorage`.
- **Evidence of Multi-Process OCC Safety**: `tools/probe_gap05_occ_multiprocess.py` was executed:
  - 10 independent OS worker processes spawned via `multiprocessing.Process`.
  - Each process opened its own `SQLiteKernelStorage(probe_occ.db)`.
  - 50 iterations per worker with artificial sleep delay (`time.sleep(0.001)`) to maximize write contention.
  - Final value: Exactly 500 / 500 increments committed without loss or corruption.
  - Result: `PASS: No race condition detected. Multiprocess concurrency is safe without RLock.`

---

## 3. GAP-06: In-Depth Investigation

### 3.1 Examination of `make_storage()` in `scp/kernel_storage.py`

Current implementation (`scp/kernel_storage.py:180-186`):
```python
def make_storage(db_path: str | Path) -> SQLiteKernelStorage:
    """Create the default SQLite storage for a given path.

    Future: accept a backend= parameter to select Postgres/etcd.
    """
    return SQLiteKernelStorage(db_path)
```

### 3.2 Complete Call Graph of `make_storage()`

```
make_storage(db_path) [scp/kernel_storage.py:180]
  ▲
  │ (imported in scp/task_kernel.py:14)
  │ (imported in scp/task_kernel_parts/taskkernel.py:12)
  │
  └── called by TaskKernel.__init__(db_path, *, storage=None) [scp/task_kernel_parts/taskkernel.py:62]
        ▲
        ├── scripts/run_scp_acceptance.py (lines 442, 458, 678, 734)
        ├── scripts/run_scp_acceptance_ci.py (line 53)
        ├── scripts/run_system_audit_strict.py (lines 163, 185, 207, 220, 237)
        ├── scripts/scp_soak_test.py (lines 122, 368, 500)
        ├── tools/audit_mutants.py (lines 86, 148, 158, 222, 285, 324, 372)
        ├── tests/T04_kernel/test_task_kernel_mutation_contract.py
        ├── tests/T04_kernel/test_transition_lease_fencing.py
        ├── tests/T04_kernel/test_satellite_occ_anti_placebo.py
        ├── tests/T04_kernel/test_rebuild_projection_occ.py
        ├── tests/T09_golden_task/test_golden_a_agent_os.py
        ├── tests/T09_golden_task/test_golden_risk_containment_e2e.py
        ├── tests/T09_golden_task/test_e2e_scp_complete.py
        ├── tests/T10_recovery/test_adversarial_chaos_matrix.py
        ├── tests/T10_recovery/test_kernel_chaos_recovery.py
        └── tests/T10_recovery/test_reconciliation_outcome_contract.py
```

### 3.3 Architectural Vulnerability: SQLite SPOF in Distributed Deployments

SQLite is fundamentally an embedded, file-based database. In a multi-node distributed system:
1. **No Network Protocol**: SQLite has no native network server; sharing an SQLite database across network filesystems (NFS, SMB) is notorious for file locking bugs, stale caches, and database corruption.
2. **Single Host Failure**: If the host containing the SQLite file crashes or loses disk access, the entire Agent OS kernel becomes unavailable.
3. **No Distributed Consensus**: SQLite does not implement Raft, Paxos, or multi-primary replication.
4. **Current Status**: `make_storage()` blindly creates a local SQLite connection without warning callers or checking environment configuration.

### 3.4 Proposed Remediation Design for GAP-06

#### A. Enhanced Function Signature & Docstring WARNING
```python
def make_storage(
    db_path: str | Path,
    backend: str | None = None,
) -> SQLiteKernelStorage:
    """Create a persistence storage backend for TaskKernel.

    WARNING:
        SINGLE POINT OF FAILURE (SPOF) IN DISTRIBUTED ENVIRONMENTS
        SQLite is a single-node, single-host file-based storage engine.
        It does NOT provide high availability, multi-host replication,
        failover, or distributed consensus.

        In distributed multi-node deployments, running on a single SQLite
        database introduces a critical Single Point of Failure (SPOF).
        For distributed production deployments, a distributed KernelStorage
        backend (such as PostgreSQL, CockroachDB, or etcd) MUST be used
        and injected via `TaskKernel(storage=my_storage)`.

    Args:
        db_path: Local filesystem path for the SQLite database.
        backend: Optional storage backend name. If None, the value of the
            `SCP_STORAGE_BACKEND` environment variable is used (defaulting
            to "sqlite").

    Returns:
        SQLiteKernelStorage: The initialized SQLite storage adapter.

    Raises:
        NotImplementedError: If `backend` or `SCP_STORAGE_BACKEND` is set
            to any value other than 'sqlite'.
    """
```

#### B. Fail-Closed Backend Guard Implementation
```python
    import os

    if backend is None:
        backend = os.environ.get("SCP_STORAGE_BACKEND", "sqlite")

    backend_normalized = backend.strip().lower()

    if backend_normalized != "sqlite":
        raise NotImplementedError(
            f"Storage backend '{backend}' is not supported. "
            f"Currently, 'sqlite' is the only built-in backend supported by make_storage(). "
            f"To use an external or distributed backend (e.g., PostgreSQL, etcd), "
            f"implement the KernelStorage protocol and pass it directly to "
            f"TaskKernel(storage=your_storage_instance)."
        )

    return SQLiteKernelStorage(db_path)
```

#### C. Handling of Unset / Blank Environment Variable
- If `SCP_STORAGE_BACKEND` is not set in `os.environ`, it defaults to `"sqlite"`.
- If `SCP_STORAGE_BACKEND` is set to `"sqlite"`, `"SQLite"`, or `"  sqlite  "`, whitespace is stripped and it is lowercased to `"sqlite"`, returning `SQLiteKernelStorage`.
- If `SCP_STORAGE_BACKEND` is empty (`""`) or set to `"postgres"`, `"mysql"`, `"etcd"`, `"distributed"`, it fails closed by raising `NotImplementedError`.

---

## 4. Anti-Placebo Test Suite Design (GAP-05 & GAP-06)

To be added to `tests/T04_kernel/test_kernel_storage.py`:

```python
import os
import pytest
from pathlib import Path
from scp.kernel_storage import SQLiteKernelStorage, make_storage
from scp.task_kernel import TaskKernel

# --- GAP-05 Anti-Placebo Tests ---

def test_gap05_multi_instance_concurrent_writes_without_rlock(tmp_path: Path):
    """Verify that concurrent writes across independent SQLiteKernelStorage instances
    (having no shared in-memory RLock) maintain atomic OCC integrity."""
    db_path = tmp_path / "gap05_concurrency.sqlite3"
    storage1 = SQLiteKernelStorage(db_path)
    storage1.executescript("CREATE TABLE counters (id TEXT PRIMARY KEY, val INTEGER, version INTEGER DEFAULT 1);")
    storage1.execute("INSERT INTO counters (id, val, version) VALUES ('c1', 0, 1)")
    storage1.close()

    # Two separate storages pointing to the same file
    s_a = SQLiteKernelStorage(db_path)
    s_b = SQLiteKernelStorage(db_path)
    try:
        s_a.begin()
        s_a.execute("UPDATE counters SET val=val+10, version=version+1 WHERE id='c1' AND version=1")
        s_a.commit()

        # s_b attempts OCC update with stale version=1
        s_b.begin()
        cur = s_b.execute("UPDATE counters SET val=val+20, version=version+1 WHERE id='c1' AND version=1")
        # Rowcount must be 0 because version is now 2
        assert cur.rowcount == 0
        s_b.rollback()

        res = s_a.fetchone("SELECT val, version FROM counters WHERE id='c1'")
        assert res["val"] == 10
        assert res["version"] == 2
    finally:
        s_a.close()
        s_b.close()


# --- GAP-06 Anti-Placebo Tests ---

def test_gap06_make_storage_default_sqlite(tmp_path: Path, monkeypatch):
    """Default backend with no env var set returns SQLiteKernelStorage."""
    monkeypatch.delenv("SCP_STORAGE_BACKEND", raising=False)
    db_path = tmp_path / "default.sqlite3"
    storage = make_storage(db_path)
    try:
        assert isinstance(storage, SQLiteKernelStorage)
        assert storage.db_path == str(db_path)
    finally:
        storage.close()


def test_gap06_make_storage_explicit_sqlite_env(tmp_path: Path, monkeypatch):
    """Explicit sqlite env var (case-insensitive with whitespace) succeeds."""
    monkeypatch.setenv("SCP_STORAGE_BACKEND", "  SQLite  ")
    db_path = tmp_path / "explicit.sqlite3"
    storage = make_storage(db_path)
    try:
        assert isinstance(storage, SQLiteKernelStorage)
    finally:
        storage.close()


@pytest.mark.parametrize("invalid_backend", ["postgres", "postgresql", "etcd", "redis", "mysql", "distributed", ""])
def test_gap06_make_storage_unsupported_backend_raises_fail_closed(tmp_path: Path, monkeypatch, invalid_backend):
    """Setting SCP_STORAGE_BACKEND to any non-sqlite value raises NotImplementedError fail-closed."""
    monkeypatch.setenv("SCP_STORAGE_BACKEND", invalid_backend)
    db_path = tmp_path / "unsupported.sqlite3"
    with pytest.raises(NotImplementedError) as exc_info:
        make_storage(db_path)
    assert f"Storage backend '{invalid_backend}' is not supported" in str(exc_info.value)
    assert "TaskKernel(storage=your_storage_instance)" in str(exc_info.value)


def test_gap06_task_kernel_integration_with_invalid_storage_backend(tmp_path: Path, monkeypatch):
    """TaskKernel(db_path) transitively invokes make_storage and fails closed on invalid backend."""
    monkeypatch.setenv("SCP_STORAGE_BACKEND", "postgres")
    with pytest.raises(NotImplementedError):
        TaskKernel(tmp_path / "kernel.sqlite3")
```

---

## 5. Verification Command Checklist

1. **Meta-Audit Verification**:
   ```bash
   python tools/t00_meta_audit.py
   ```
2. **GAP-05 Multi-Process Concurrency Probe**:
   ```bash
   python tools/probe_gap05_occ_multiprocess.py
   ```
3. **GAP-06 & Kernel Storage Unit Tests**:
   ```bash
   pytest tests/T04_kernel/test_kernel_storage.py -v
   ```
4. **Full Test Suite Regression Run**:
   ```bash
   pytest tests/ -q
   ```
