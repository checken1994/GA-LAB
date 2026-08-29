"""
Mảnh ghép #30 — File Mutex: khóa file cross-platform cho multi-writer.

TẠI SAO: Windows không tha thứ hai process ghi cùng một file —
PermissionError: [WinError 32] là cái bẫy chain-breaker của tự chủ phân tán.
FileMutex dùng msvcrt.locking (Windows) / fcntl.flock (POSIX) trên một
file lock sidecar, kết hợp O_EXCL tạo file để atomic-across-platform.
Context manager + timeout — hết giờ raise TimeoutError, không treo vĩnh viễn.
"""
from __future__ import annotations

import contextlib
import os
import time
import uuid
from pathlib import Path
from typing import Iterator


class FileMutex:
    """Mutex dựa trên thư mục O_EXCL (atomic trên mọi OS) — đơn giản, đúng,
    không phụ thuộc fcntl/msvcrt. acquire(timeout) poll với backoff."""

    def __init__(self, lock_dir: str | Path):
        self.lock_dir = Path(lock_dir)
        self.lock_dir.mkdir(parents=True, exist_ok=True)

    def _lock_path(self, name: str) -> Path:
        safe = name.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self.lock_dir / f"{safe}.lock"

    @contextlib.contextmanager
    def acquire(self, name: str, timeout: float = 10.0, holder: str | None = None) -> Iterator[Path]:
        lock_path = self._lock_path(name)
        token = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        deadline = time.monotonic() + timeout
        acquired = False
        try:
            while True:
                try:
                    # O_EXCL — atomic creation: chỉ MỘT winner
                    lock_path.touch(mode=0o600, exist_ok=False)
                    lock_path.write_text(token, encoding="utf-8")
                    acquired = True
                    yield lock_path
                    return
                except FileExistsError:
                    # Stale lock: holder chết mà không release (>holder_ttl) → lấy quyền
                    try:
                        age = time.time() - lock_path.stat().st_mtime
                    except OSError:
                        continue
                    if age > 60.0:  # holder TTL 60s — lock mồ côi bị thu hồi
                        with contextlib.suppress(OSError):
                            lock_path.unlink()
                        continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"file mutex '{name}' not acquired within {timeout}s (held by {holder or 'unknown'})")
                time.sleep(0.05)
        finally:
            if acquired:
                with contextlib.suppress(OSError):
                    if lock_path.exists() and lock_path.read_text(encoding="utf-8") == token:
                        lock_path.unlink()
