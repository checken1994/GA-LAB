"""
scp/api/background_jobs.py
===========================
Background Job Registry cho SCP lifespan.

DNA #23 — Xây quá trình tự sửa: không để job quan trọng bị "quên" khi thêm mới.
DNA #19 — Missing piece: trước đây mỗi background job là ad-hoc try/except block riêng,
          không có registry → expire_leases, auto_reconcile_orphans không bao giờ được gọi.

Cách dùng:
  from scp.api.background_jobs import registry, BackgroundJob
  import time

  # Đăng ký job (thường ở module init của từng subsystem):
  @registry.register(name="kernel_watchdog", interval_seconds=30, required=True)
  def _kernel_watchdog_tick():
      from scp.api._shared import get_kernel
      k = get_kernel()
      if k:
          k.expire_leases()
          k.auto_reconcile_orphans()

  # Trong lifespan():
  registry.start_all()    # khởi động tất cả jobs
  yield
  registry.stop_all()     # dừng sạch khi shutdown
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger("scp.api.background_jobs")


@dataclass
class BackgroundJob:
    """Mô tả một background job định kỳ."""
    name: str
    fn: Callable[[], None]
    interval_seconds: float
    required: bool = False          # nếu True → lỗi khi start = fail boot
    initial_delay_seconds: float = 10.0
    _stop_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _started: bool = field(default=False, repr=False)
    _error_count: int = field(default=0, repr=False)

    def start(self) -> None:
        if self._started:
            return
        self._stop_event.clear()

        def _loop():
            # Initial delay — để server boot xong trước
            if self._stop_event.wait(self.initial_delay_seconds):
                return
            logger.info("[BackgroundJob] %s: started (interval=%.0fs)", self.name, self.interval_seconds)
            while not self._stop_event.is_set():
                try:
                    self.fn()
                    self._error_count = 0
                except Exception as exc:
                    self._error_count += 1
                    logger.warning(
                        "[BackgroundJob] %s: error #%d — %s",
                        self.name, self._error_count, exc
                    )
                    if self._error_count >= 5:
                        logger.error(
                            "[BackgroundJob] %s: %d consecutive errors — suppressing until next cycle",
                            self.name, self._error_count
                        )
                self._stop_event.wait(self.interval_seconds)

        self._thread = threading.Thread(
            target=_loop,
            daemon=True,
            name=f"scp-bg-{self.name}",
        )
        self._thread.start()
        self._started = True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._started = False


class BackgroundJobRegistry:
    """
    Registry trung tâm cho tất cả background jobs của SCP.
    
    Nguyên tắc:
    - Mỗi job đăng ký một lần, start_all() gọi một lần trong lifespan.
    - Job required=True → lỗi start = raise → server không boot.
    - Job required=False → lỗi start = warn + tiếp tục.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, BackgroundJob] = {}
        self._lock = threading.Lock()

    def register(
        self,
        name: str,
        interval_seconds: float,
        required: bool = False,
        initial_delay_seconds: float = 10.0,
    ) -> Callable[[Callable], Callable]:
        """Decorator để đăng ký một background job."""
        def decorator(fn: Callable) -> Callable:
            with self._lock:
                if name in self._jobs:
                    raise ValueError(f"BackgroundJob '{name}' đã được đăng ký.")
                self._jobs[name] = BackgroundJob(
                    name=name,
                    fn=fn,
                    interval_seconds=interval_seconds,
                    required=required,
                    initial_delay_seconds=initial_delay_seconds,
                )
            return fn
        return decorator

    def add(self, job: BackgroundJob) -> None:
        """Thêm job đã tạo sẵn vào registry."""
        with self._lock:
            if job.name in self._jobs:
                raise ValueError(f"BackgroundJob '{job.name}' đã được đăng ký.")
            self._jobs[job.name] = job

    def start_all(self) -> None:
        """Khởi động tất cả jobs. Required jobs fail → raise."""
        failed_required: list[str] = []
        with self._lock:
            jobs = list(self._jobs.values())

        for job in jobs:
            try:
                job.start()
                logger.info("[BackgroundJobRegistry] Started: %s (required=%s)", job.name, job.required)
            except Exception as exc:
                if job.required:
                    failed_required.append(f"{job.name}: {exc}")
                    logger.error("[BackgroundJobRegistry] REQUIRED job failed to start: %s — %s", job.name, exc)
                else:
                    logger.warning("[BackgroundJobRegistry] Optional job failed to start: %s — %s", job.name, exc)

        if failed_required:
            raise RuntimeError(
                f"[BackgroundJobRegistry] {len(failed_required)} required background job(s) failed to start:\n"
                + "\n".join(f"  - {e}" for e in failed_required)
            )

    def stop_all(self, timeout: float = 5.0) -> None:
        """Dừng sạch tất cả jobs khi shutdown."""
        with self._lock:
            jobs = list(self._jobs.values())
        for job in jobs:
            try:
                job.stop(timeout=timeout)
                logger.debug("[BackgroundJobRegistry] Stopped: %s", job.name)
            except Exception as exc:
                logger.warning("[BackgroundJobRegistry] Error stopping %s: %s", job.name, exc)

    def status(self) -> dict[str, dict]:
        """Trả về trạng thái của tất cả jobs — dùng trong /health endpoint."""
        with self._lock:
            return {
                name: {
                    "started": job._started,
                    "required": job.required,
                    "interval_seconds": job.interval_seconds,
                    "error_count": job._error_count,
                }
                for name, job in self._jobs.items()
            }


# =============================================================================
# Global registry — import và dùng ở bất kỳ đâu
# =============================================================================
registry = BackgroundJobRegistry()


# =============================================================================
# Đăng ký các jobs BẮT BUỘC của SCP kernel
# =============================================================================

@registry.register(
    name="kernel_lease_expiry",
    interval_seconds=30,
    required=True,          # thiếu watchdog = owner lockout vĩnh viễn → PHẢI chạy
    initial_delay_seconds=15,
)
def _kernel_lease_expiry_tick() -> None:
    """Hết hạn các lease bị timeout — ngăn owner lockout vĩnh viễn."""
    try:
        from scp.api._shared import get_kernel  # type: ignore[import]
        k = get_kernel()
        if k is not None:
            expired = k.expire_leases()
            if expired:
                logger.info("[Watchdog] expire_leases: %d expired", len(expired))
    except ImportError:
        pass  # _shared chưa khởi tạo — sẽ retry sau 30s


@registry.register(
    name="kernel_orphan_reconcile",
    interval_seconds=60,
    required=True,          # task orphan không được reconcile = task bị kẹt mãi mãi
    initial_delay_seconds=30,
)
def _kernel_orphan_reconcile_tick() -> None:
    """Reconcile các task orphan (crash, mất kết nối) → RECONCILING state."""
    try:
        from scp.api._shared import get_kernel  # type: ignore[import]
        k = get_kernel()
        if k is not None:
            orphans = k.auto_reconcile_orphans()
            if orphans:
                logger.info("[Watchdog] auto_reconcile_orphans: %d reconciled", len(orphans))
    except ImportError:
        pass


@registry.register(
    name="canary_token_cleanup",
    interval_seconds=86400,  # 24h
    required=False,
    initial_delay_seconds=600,
)
def _canary_cleanup_tick() -> None:
    """Dọn dẹp canary token hết hạn — ngăn memory leak."""
    try:
        from scp.api._shared import _get_judge_lazy  # type: ignore[import]
        judge = _get_judge_lazy()
        cm = getattr(judge, "canary_monitor", None)
        if cm is not None and hasattr(cm, "cleanup_expired"):
            removed = cm.cleanup_expired()
            if removed:
                logger.info("[Watchdog] canary_cleanup: removed %d expired tokens", removed)
    except Exception:
        pass
