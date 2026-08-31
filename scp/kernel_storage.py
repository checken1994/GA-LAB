"""Persistence boundary for :class:`scp.task_kernel.TaskKernel`.

``TaskKernel`` owns task semantics and SQL projections.  This module owns the
database lifecycle: connections, transaction serialization, backend exception
translation, and online backup.  Keeping SQL projections in the kernel is an
intentional incremental boundary; a non-SQL backend would also require a
repository/query contract, not merely a connection adapter.

``TaskKernel(db_path)`` remains backward compatible, while
``TaskKernel(storage=...)`` makes the persistence lifecycle injectable and
testable without exposing SQLite locks or connections to the kernel.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class StorageIntegrityError(sqlite3.IntegrityError):
    """Backend-neutral uniqueness/integrity conflict.

    It temporarily retains ``sqlite3.IntegrityError`` compatibility so callers
    written before the storage abstraction continue to fail closed while they
    migrate to the backend-neutral exception.  The storage layer remains the
    only place that translates backend-specific integrity failures.
    """


@runtime_checkable
class KernelStorage(Protocol):
    """Persistence contract for TaskKernel.

    Implementors MUST provide:
    - begin / commit / rollback   -- atomic write slot
    - execute / fetchone / fetchall -- query primitives
    - close                       -- clean shutdown
    """

    def begin(self) -> None:
        """Acquire exclusive write slot and start a transaction."""
        ...

    def commit(self) -> None:
        """Commit the current transaction and release the write slot."""
        ...

    def rollback(self) -> None:
        """Rollback the current transaction and release the write slot."""
        ...

    def execute(self, sql: str, params: Any = ()) -> Any:
        """Execute a single SQL statement."""
        ...

    def executescript(self, script: str) -> None:
        """Execute a DDL script (CREATE TABLE etc.)."""
        ...

    def fetchone(self, sql: str, params: Any = ()) -> Any | None:
        """Execute and fetch a single row."""
        ...

    def fetchall(self, sql: str, params: Any = ()) -> list[Any]:
        """Execute and fetch all rows."""
        ...

    @property
    def in_transaction(self) -> bool:
        """True if a transaction is currently held by this thread."""
        ...

    def close(self) -> None:
        """Release all resources."""
        ...

    def backup_to(self, target: str | Path) -> None:
        """Write a transactionally consistent snapshot to target."""
        ...


class SQLiteKernelStorage:
    """Per-thread-connection SQLite WAL storage.

    Design invariants (chain-audit 2026-08-29):
    - WAL mode: multiple readers never block writers.
    - Per-thread connections: eliminates cross-thread snapshot visibility issues.
    - busy_timeout=10000ms: prevents instant SQLITE_BUSY under light contention.
    - BEGIN IMMEDIATE with retry: prevents write-write deadlocks.
    - All connections tracked in _all_conns for clean shutdown via close().
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn_local = threading.local()
        self._all_conns: list[sqlite3.Connection] = []
        self._conn_guard = threading.Lock()
        self._tx_lock = threading.RLock()
        self._tx_state = threading.local()
        c = self._get_conn()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=10000")

    def _make_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path, timeout=10, isolation_level=None, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._conn_local, "conn", None)
        if conn is None:
            conn = self._make_connection()
            self._conn_local.conn = conn
            with self._conn_guard:
                self._all_conns.append(conn)
        return conn

    def begin(self) -> None:
        """Acquire write lock + BEGIN IMMEDIATE (3 retries on SQLITE_BUSY)."""
        self._tx_lock.acquire()
        try:
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    self._get_conn().execute("BEGIN IMMEDIATE")
                    self._tx_state.held = True
                    return
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower():
                        raise
                    last_error = exc
                    time.sleep(0.05 * (attempt + 1))
            raise last_error if last_error else RuntimeError("begin failed")
        except BaseException:
            self._tx_lock.release()
            raise

    def _release_tx_lock(self) -> None:
        if getattr(self._tx_state, "held", False):
            self._tx_state.held = False
            self._tx_lock.release()

    def commit(self) -> None:
        try:
            self._get_conn().execute("COMMIT")
        finally:
            self._release_tx_lock()

    def rollback(self) -> None:
        try:
            conn = self._get_conn()
            if conn.in_transaction:
                conn.execute("ROLLBACK")
        finally:
            self._release_tx_lock()

    def execute(self, sql: str, params: Any = ()) -> Any:
        try:
            return self._get_conn().execute(sql, params)
        except sqlite3.IntegrityError as exc:
            raise StorageIntegrityError(str(exc)) from exc

    def executescript(self, script: str) -> None:
        self._get_conn().executescript(script)

    def fetchone(self, sql: str, params: Any = ()) -> Any | None:
        return self._get_conn().execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: Any = ()) -> list[Any]:
        return self._get_conn().execute(sql, params).fetchall()

    @property
    def in_transaction(self) -> bool:
        return bool(self._get_conn().in_transaction)

    def close(self) -> None:
        with self._conn_guard:
            for conn in self._all_conns:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            self._all_conns.clear()
            self._conn_local = threading.local()

    def backup_to(self, target: str | Path) -> None:
        """Use SQLite's online backup API so WAL writers may remain active."""
        destination = sqlite3.connect(str(target))
        try:
            self._get_conn().backup(destination)
        finally:
            destination.close()


def make_storage(db_path: str | Path) -> SQLiteKernelStorage:
    """Create the default SQLite storage for a given path.

    Future: accept a backend= parameter to select Postgres/etcd.
    """
    return SQLiteKernelStorage(db_path)
