from __future__ import annotations

from pathlib import Path
from typing import Any

from scp.kernel_storage import SQLiteKernelStorage
from scp.task_kernel import TaskKernel


class TrackingStorage:
    """Small contract spy; SQL behaviour still comes from the real backend."""

    def __init__(self, db_path: Path) -> None:
        self.backend = SQLiteKernelStorage(db_path)
        self.db_path = str(db_path)
        self.begins = 0
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def begin(self) -> None:
        self.begins += 1
        self.backend.begin()

    def commit(self) -> None:
        self.commits += 1
        self.backend.commit()

    def rollback(self) -> None:
        self.rollbacks += 1
        self.backend.rollback()

    def execute(self, sql: str, params: Any = ()) -> Any:
        return self.backend.execute(sql, params)

    def executescript(self, script: str) -> None:
        self.backend.executescript(script)

    def fetchone(self, sql: str, params: Any = ()) -> Any | None:
        return self.backend.fetchone(sql, params)

    def fetchall(self, sql: str, params: Any = ()) -> list[Any]:
        return self.backend.fetchall(sql, params)

    @property
    def in_transaction(self) -> bool:
        return self.backend.in_transaction

    def backup_to(self, target: str | Path) -> None:
        self.backend.backup_to(target)

    def close(self) -> None:
        self.closed = True
        self.backend.close()


def test_task_kernel_uses_injected_storage_for_transaction_lifecycle(tmp_path: Path) -> None:
    storage = TrackingStorage(tmp_path / "kernel.sqlite3")
    kernel = TaskKernel(storage=storage)

    kernel.create_task("storage-contract", "test", "prove injected storage")
    kernel.transition("storage-contract", "PLANNING")

    assert kernel.get_task("storage-contract")["state"] == "PLANNING"
    assert storage.begins == 2
    assert storage.commits == 2
    assert storage.rollbacks == 0

    kernel.close()
    assert storage.closed is True


def test_task_kernel_backup_is_delegated_to_storage(tmp_path: Path) -> None:
    storage = TrackingStorage(tmp_path / "kernel.sqlite3")
    kernel = TaskKernel(storage=storage)
    kernel.create_task("backup-contract", "test", "prove backup delegation")

    result = kernel.backup(tmp_path / "backups", retain=1)

    backup_path = Path(result["backup"])
    assert backup_path.is_file()
    reopened = TaskKernel(backup_path)
    try:
        assert reopened.get_task("backup-contract")["state"] == "CREATED"
    finally:
        reopened.close()
        kernel.close()
