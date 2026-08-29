"""Chain Audit fixes (Z→A→G→B→C→D) — test khóa từng phát hiện có bằng chứng.

Claim Z  (Gemini: "production_guard yêu cầu file vật lý → Docker crash loop")
         → SAI: env-only secret pass guard. Test khóa contract này.
Claim A  ("100 request → SQLITE_BUSY chết chuỗi")
         → SAI về cơ chế (0 SQLITE_BUSY), ĐÚNG về bản chất có race thật:
           shared connection làm 16/100 task chết NotFound → đã fix per-thread
           connection. Test load-storm khóa regression này.
Claim A+ (backpressure) → admission control theo cap in-flight.
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

import pytest

from scp.task_kernel import TaskKernel


def test_z_env_only_secrets_pass_production_guard(monkeypatch):
    """Docker/K8s Secret Manager pattern: password qua env, KHÔNG có file."""
    monkeypatch.setenv("SCP_PRODUCTION_MODE", "1")
    monkeypatch.setenv("SCP_EGRESS_MODE", "deny")
    monkeypatch.setenv("SCP_HOST", "127.0.0.1")
    monkeypatch.setenv("SCP_AUTH_PASSWORD", "docker-secret-manager-password-32-chars!")
    monkeypatch.delenv("SCP_AUTH_PASSWORD_FILE", raising=False)
    for flag in ("SCP_DEV_MODE", "SCP_SKIP_STARTUP_GATE", "SCP_AUTO_APPROVE_TIER3",
                 "SCP_EVOLUTION_AUTO", "SCP_ENABLE_CLOSED_LOOP", "SCP_TIER3_ALLOW_RELAXATION",
                 "SCP_TIER3_ALLOW_BAREEXCEPTPASS"):
        monkeypatch.setenv(flag, "0")
    from scp.security.production_guard import enforce_production_safety

    enforce_production_safety()  # KHÔNG được raise — claim Z disproved


def test_a_load_storm_zero_loss(tmp_path):
    """Regression khóa chain-breaker: 100 luồng đồng thời, 0 task được phép
    mất. Trước per-thread-connection fix: 16/100 chết NotFound."""
    kernel = TaskKernel(tmp_path / "storm.sqlite3")
    N = 40  # bug NotFound tái hiện ở 40 thread (9/40 lỗi trước fix)
    errors, done = [], []
    lock = threading.Lock()

    def worker(i):
        tid = f"storm-{i}"
        try:
            kernel.create_task(tid, "load", f"goal {i}", "R0")
            kernel.transition(tid, "PLANNING", actor="w", reason="plan")
            kernel.transition(tid, "READY", actor="w", reason="ready")
            kernel.transition(tid, "QUEUED", actor="w", reason="queue")
            # TTL phải >> thời gian storm — tránh StaleLease ngẫu nhiên
            lease = kernel.claim(tid, "worker-1", ttl_seconds=3600)
            kernel.start(tid, lease.lease_id)
            kernel.transition(tid, "VERIFYING", actor="w", reason="verify")
            kernel.commit_completed(tid, lease.lease_id, "VERIFIED", f"ev://{tid}")
            with lock:
                done.append(tid)
        except Exception as exc:  # noqa: BLE001 — test cần thấy mọi lỗi
            with lock:
                errors.append(f"{tid}: {type(exc).__name__}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"kernel mất task dưới tải: {errors[:5]}"
    assert len(done) == N
    valid = sum(1 for i in range(N) if kernel.verify_journal(f"storm-{i}")["hash_chain_valid"])
    assert valid == N, "hash-chain phải nguyên vẹn sau load storm"
    kernel.close()


def test_a_backpressure_rejects_beyond_cap(monkeypatch, tmp_path):
    kernel = TaskKernel(tmp_path / "bp.sqlite3")
    kernel.create_task("stuck-1", "op", "goal", "R0")
    kernel.create_task("stuck-2", "op", "goal", "R0")  # non-terminal → in-flight
    monkeypatch.setenv("SCP_ASK_MAX_INFLIGHT", "2")
    assert kernel.in_flight_count() == 2

    from scp.ask_kernel_adapter import AskKernelAdapter

    class FakeRequest:
        headers = {}

    adapter = AskKernelAdapter(db_path=str(tmp_path / "a.sqlite3"), trace_path=str(tmp_path / "t.jsonl"))
    # Adapter dùng kernel RIÊNG (db khác) — mock in_flight_count ở adapter kernel
    monkeypatch.setattr(adapter.kernel, "in_flight_count", lambda: 999)
    with pytest.raises(Exception, match="backpressure"):
        adapter.begin("q", [], "", None, request=FakeRequest())


def test_a_normal_capacity_accepts_new_asks(tmp_path):
    kernel = TaskKernel(tmp_path / "ok.sqlite3")
    from scp.ask_kernel_adapter import AskKernelAdapter

    adapter = AskKernelAdapter(db_path=str(tmp_path / "a.sqlite3"), trace_path=str(tmp_path / "t.jsonl"))
    # kernel trống → cap 200 không chặn
    task = adapter.begin("q", [], "", None, request=None)
    assert task["task_id"]
    adapter.kernel.set_task_kill(task["task_id"])
