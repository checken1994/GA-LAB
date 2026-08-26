import multiprocessing
import os
import sqlite3
import time
import threading

import pytest

from scp.task_kernel import CheckpointCorrupt, KernelError, StaleLease, TaskKernel


def queue_task(kernel: TaskKernel, task_id: str = "task") -> None:
    kernel.create_task(task_id, "test:user", "safe read", "R0")
    for state in ("PLANNING", "READY", "QUEUED"):
        kernel.transition(task_id, state, reason="recovery-contract")


def make_checkpoint(kernel: TaskKernel):
    queue_task(kernel)
    lease = kernel.claim("task", "worker", ttl_seconds=5)
    kernel.start("task", lease.lease_id)
    checkpoint_id = kernel.checkpoint(
        "task",
        lease.lease_id,
        "read",
        "WAITING_TOOL",
        {"operation": "read", "url": "https://safe.example"},
        0,
        "stable-key",
        pre_observation_ref="obs://before",
    )
    return lease, checkpoint_id


def _crash_after_checkpoint(db_path: str, pipe, ready) -> None:
    kernel = TaskKernel(db_path)
    lease = kernel.claim("task", "crasher", ttl_seconds=0.2)
    kernel.start("task", lease.lease_id)
    checkpoint_id = kernel.checkpoint(
        "task",
        lease.lease_id,
        "read",
        "WAITING_TOOL",
        {"operation": "read", "url": "https://safe.example"},
        0,
        "crash-stable-key",
        pre_observation_ref="obs://before",
    )
    pipe.send((lease.lease_id, checkpoint_id))
    pipe.close()
    ready.set()
    os._exit(42)


def test_worker_process_crash_after_checkpoint_recovers_safely(tmp_path):
    db = tmp_path / "kernel.sqlite3"
    kernel = TaskKernel(db)
    queue_task(kernel)
    kernel.close()
    parent_pipe, child_pipe = multiprocessing.Pipe(duplex=False)
    ready = multiprocessing.Event()
    context = multiprocessing.get_context("spawn")
    worker = context.Process(target=_crash_after_checkpoint, args=(str(db), child_pipe, ready))
    worker.start()
    assert ready.wait(20)
    old_lease_id, checkpoint_id = parent_pipe.recv()
    worker.join(20)
    assert worker.exitcode == 42
    parent_pipe.close()
    reopened = TaskKernel(db)
    try:
        assert reopened.validate_checkpoint(
            checkpoint_id,
            {"operation": "read", "url": "https://safe.example"},
        )["checkpoint_id"] == checkpoint_id
        assert reopened.expire_leases(now=time.time() + 1)
        assert reopened.get_task("task")["state"] == "RECOVERING"
        assert reopened.verify_journal("task")["hash_chain_valid"] is True
        reopened.transition("task", "QUEUED", reason="worker_crash_recovery")
        new_lease = reopened.claim("task", "recovery-worker", ttl_seconds=5)
        assert new_lease.lease_id != old_lease_id
        assert new_lease.fencing_token > 0
        reopened.start("task", new_lease.lease_id)
        with pytest.raises(StaleLease):
            reopened.heartbeat("task", old_lease_id)
    finally:
        reopened.close()


def test_global_kill_fences_existing_lease_and_completion(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    queue_task(kernel)
    lease = kernel.claim("task", "worker", ttl_seconds=5)
    kernel.start("task", lease.lease_id)
    kernel.transition("task", "VERIFYING", reason="kill-fence-test")
    epoch = kernel.set_global_kill(True, actor="chaos-test")
    assert epoch >= 1
    with pytest.raises(StaleLease):
        kernel.heartbeat("task", lease.lease_id)
    with pytest.raises(StaleLease):
        kernel.commit_verification_result(
            "task",
            lease.lease_id,
            {"verdict": "VERIFIED", "verifier_id": "test", "evidence_ref": "evidence://task"},
        )
    kernel.set_global_kill(False, actor="chaos-test")
    assert kernel.get_task("task")["state"] == "VERIFYING"
    kernel.close()


def test_concurrent_idempotency_claim_has_single_winner(tmp_path):
    db = tmp_path / "kernel.sqlite3"
    kernels = [TaskKernel(db), TaskKernel(db)]
    barrier = threading.Barrier(2)
    results = []

    def claim(kernel):
        barrier.wait()
        try:
            results.append(kernel.idempotency_claim("task", "read", "context.read", "same-input"))
        except Exception as exc:
            results.append(type(exc).__name__)

    threads = [threading.Thread(target=claim, args=(kernel,)) for kernel in kernels]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(isinstance(result, tuple) and result[1] is True for result in results) == 1
    assert sum(isinstance(result, tuple) and result[1] is False for result in results) == 1
    assert all(isinstance(result, tuple) for result in results)
    for kernel in kernels:
        kernel.close()


def test_idempotency_completion_requires_existing_claim_and_is_idempotent(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    with pytest.raises(KernelError, match="idempotency key not found"):
        kernel.idempotency_complete("missing-key", "result://missing")
    key, claimed = kernel.idempotency_claim("task", "read", "context.read", "input")
    assert claimed is True
    kernel.idempotency_complete(key, "result://one")
    kernel.idempotency_complete(key, "result://one")
    with pytest.raises(KernelError, match="idempotency result mismatch"):
        kernel.idempotency_complete(key, "result://other")
    kernel.close()


def test_checkpoint_payload_hash_tamper_is_rejected(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    _, checkpoint_id = make_checkpoint(kernel)
    kernel.conn.execute(
        "UPDATE checkpoints SET payload_hash=? WHERE checkpoint_id=?",
        ("sha256:tampered", checkpoint_id),
    )
    with pytest.raises(CheckpointCorrupt):
        kernel.validate_checkpoint(
            checkpoint_id,
            {"operation": "read", "url": "https://safe.example"},
        )
    kernel.close()


def test_checkpoint_rejects_secret_material(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    queue_task(kernel)
    lease = kernel.claim("task", "worker", ttl_seconds=5)
    kernel.start("task", lease.lease_id)
    with pytest.raises(KernelError, match="checkpoint contains secret material"):
        kernel.checkpoint(
            "task",
            lease.lease_id,
            "read",
            "RUNNING",
            {
                "operation": "read",
                "headers": {"Authorization": "Bearer abcdefgh12345678"},
            },
            0,
            "secret-key",
        )
    kernel.close()


def test_journal_invalid_json_is_reported_without_crash(tmp_path):
    db = tmp_path / "kernel.sqlite3"
    kernel = TaskKernel(db)
    queue_task(kernel)
    kernel.close()
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE events SET payload_json=? WHERE task_id=? AND seq=1",
            ("{broken-json", "task"),
        )
        connection.commit()
    reopened = TaskKernel(db)
    report = reopened.verify_journal("task")
    assert report["hash_chain_valid"] is False
    assert "payload_json:1" in report["errors"]
    reopened.close()


def test_projection_rebuild_rejects_tampered_journal(tmp_path):
    db = tmp_path / "kernel.sqlite3"
    kernel = TaskKernel(db)
    queue_task(kernel)
    kernel.close()
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE events SET payload_json=? WHERE task_id=? AND seq=1",
            ('{"input_hash":"sha256:tampered"}', "task"),
        )
        connection.commit()
    reopened = TaskKernel(db)
    with pytest.raises(KernelError, match="journal integrity"):
        reopened.rebuild_projection("task")
    reopened.close()
