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

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import logging
logger = logging.getLogger(__name__)



class StorageIntegrityError(RuntimeError):
    """Backend-neutral uniqueness/integrity conflict."""


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
        """Acquire write lock + BEGIN IMMEDIATE (bounded retry on SQLITE_BUSY / locked)."""
        last_error: Exception | None = None
        for attempt in range(25):
            try:
                self._get_conn().execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as exc:
                err_msg = str(exc).lower()
                if "locked" not in err_msg and "busy" not in err_msg:
                    raise
                last_error = exc
                time.sleep(0.05 * min(attempt + 1, 4))
        raise last_error if last_error else RuntimeError("begin failed")

    def commit(self) -> None:
        self._get_conn().execute("COMMIT")

    def rollback(self) -> None:
        conn = self._get_conn()
        if conn.in_transaction:
            conn.execute("ROLLBACK")

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
                    logger.debug('SQLiteKernelStorage.close: sqlite3.Error ignored', exc_info=True)
            self._all_conns.clear()
            self._conn_local = threading.local()

    def backup_to(self, target: str | Path) -> None:
        """Use SQLite's online backup API so WAL writers may remain active."""
        destination = sqlite3.connect(str(target))
        try:
            self._get_conn().backup(destination)
        finally:
            destination.close()


def make_storage(db_path: str | Path, backend: str | None = None) -> KernelStorage:
    """Create the storage backend for a given path.

    Backend resolution order:
      1. explicit ``backend`` argument;
      2. ``SCP_KERNEL_BACKEND`` env (canonical switch; ``postgres`` requires
         ``SCP_KERNEL_PG_DSN`` and returns :class:`PgKernelStorage`);
      3. ``SCP_STORAGE_BACKEND`` env (legacy switch; keeps its fail-closed
         sqlite-only contract — ``postgres`` there still raises
         ``NotImplementedError`` so no deployment silently flips engines);
      4. default ``sqlite``.

    WARNING: SQLite is a Single Point of Failure (SPOF) in distributed deployments.
    It does not support cross-node replication or active-active clustering.
    For high availability or multi-node production setups, a distributed storage backend is required.
    """

    def _unsupported(name: str) -> NotImplementedError:
        return NotImplementedError(
            f"Unsupported storage backend '{name}'. Only 'sqlite' is currently supported. "
            "For distributed deployments, inject a custom Storage instance into TaskKernel."
        )

    def _postgres() -> KernelStorage:
        dsn = os.environ.get("SCP_KERNEL_PG_DSN", "").strip()
        if not dsn:
            raise RuntimeError(
                "SCP_KERNEL_BACKEND=postgres requires SCP_KERNEL_PG_DSN to be set "
                "(fail-closed: refusing to fall back to SQLite)."
            )
        from scp.kernel_storage_pg import PgKernelStorage

        return PgKernelStorage(dsn)

    if backend is not None:
        backend = str(backend).strip().lower()
        if backend in ("sqlite", ""):
            return SQLiteKernelStorage(db_path)
        if backend == "postgres":
            return _postgres()
        raise _unsupported(backend)

    kernel_env = os.environ.get("SCP_KERNEL_BACKEND", "").strip().lower()
    if kernel_env:
        if kernel_env == "sqlite":
            return SQLiteKernelStorage(db_path)
        if kernel_env == "postgres":
            return _postgres()
        raise _unsupported(kernel_env)

    legacy_env = os.environ.get("SCP_STORAGE_BACKEND", "sqlite")
    if legacy_env.strip().lower() in ("sqlite", ""):
        return SQLiteKernelStorage(db_path)
    raise _unsupported(legacy_env.strip())
