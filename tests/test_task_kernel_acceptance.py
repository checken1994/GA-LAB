from __future__ import annotations

import sqlite3
import threading
import time

import pytest

from scp.task_kernel import (
    CheckpointCorrupt,
    InvalidTransition,
    KillSwitchActive,
    StaleLease,
    TaskKernel,
)
from scp.verifier import IndependentVerifier


def queue_task(kernel: TaskKernel, task_id: str = "task") -> None:
    kernel.create_task(task_id, "test:user", "safe read", "R0")
    for state in ("PLANNING", "READY", "QUEUED"):
        kernel.transition(task_id, state, reason="acceptance")


def test_two_workers_only_one_claim(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    queue_task(kernel)
    results: list[str] = []
    lock = threading.Lock()

    def worker(name: str) -> None:
        try:
            kernel.claim("task", name, ttl_seconds=5)
            value = "OK"
        except Exception as exc:  # only one worker is expected to claim
            value = type(exc).__name__
        with lock:
            results.append(value)

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("w1", "w2")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("OK") == 1
    kernel.close()


def test_expiry_and_latest_fencing_reject_old_worker(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    queue_task(kernel)
    old = kernel.claim("task", "old", ttl_seconds=0.01)
    kernel.start("task", old.lease_id)
    time.sleep(0.03)
    assert kernel.expire_leases()
    assert kernel.get_task("task")["state"] == "RECOVERING"
    kernel.transition("task", "QUEUED", reason="bounded_recovery")
    new = kernel.claim("task", "new", ttl_seconds=5)
    assert new.fencing_token > old.fencing_token
    with pytest.raises(StaleLease):
        kernel.start("task", old.lease_id)
    kernel.start("task", new.lease_id)
    kernel.close()


def test_global_kill_and_terminal_task_immutability(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    queue_task(kernel)
    epoch = kernel.set_global_kill(True, actor="test")
    with pytest.raises(KillSwitchActive):
        kernel.claim("task", "blocked", ttl_seconds=5)
    kernel.set_global_kill(False, actor="test")
    assert epoch >= 1
    killed = kernel.set_task_kill("task", actor="test")
    assert killed["state"] == "CANCELLED"
    with pytest.raises(InvalidTransition):
        kernel.set_task_kill("task", actor="test")
    kernel.close()


def test_checkpoint_hash_journal_and_projection_rebuild(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    queue_task(kernel)
    lease = kernel.claim("task", "worker", ttl_seconds=5)
    kernel.start("task", lease.lease_id)
    checkpoint = kernel.checkpoint(
        "task",
        lease.lease_id,
        "read",
        "WAITING_TOOL",
        {"url": "https://safe.example"},
        0,
        "stable-key",
        pre_observation_ref="obs://before",
    )
    assert kernel.validate_checkpoint(checkpoint, {"url": "https://safe.example"})["checkpoint_id"] == checkpoint
    with pytest.raises(CheckpointCorrupt):
        kernel.validate_checkpoint(checkpoint, {"url": "https://evil.example"})
    kernel.conn.execute("UPDATE tasks SET state='FAILED' WHERE task_id='task'")
    rebuilt = kernel.rebuild_projection("task")
    assert rebuilt["state"] == "WAITING_TOOL"
    assert kernel.verify_journal("task")["hash_chain_valid"] is True
    kernel.close()


def test_event_hash_tamper_is_detected_after_restart(tmp_path):
    db = tmp_path / "kernel.sqlite3"
    kernel = TaskKernel(db)
    queue_task(kernel)
    kernel.close()
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE events SET event_hash='tampered' WHERE task_id='task' AND seq=1")
        connection.commit()
    reopened = TaskKernel(db)
    report = reopened.verify_journal("task")
    assert report["hash_chain_valid"] is False
    reopened.close()


def test_idempotency_and_independent_verifier_gate(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    queue_task(kernel)
    lease = kernel.claim("task", "worker", ttl_seconds=5)
    kernel.start("task", lease.lease_id)
    key, first = kernel.idempotency_claim("task", "read", "context.read", "input-hash")
    same_key, second = kernel.idempotency_claim("task", "read", "context.read", "input-hash")
    assert (key, first) == (same_key, True)
    assert second is False
    kernel.transition("task", "VERIFYING", reason="observed")
    verifier = IndependentVerifier()
    result = verifier.to_dict(
        verifier.verify(
            {"all": [{"kind": "url_matches", "value": "https://safe.example"}], "evidence_required": True},
            {"url": "https://safe.example", "evidence_ref": "evidence://task"},
        )
    )
    kernel.commit_verification_result("task", lease.lease_id, result)
    assert kernel.get_task("task")["state"] == "COMPLETED"
    with pytest.raises(InvalidTransition):
        kernel.transition("task", "RUNNING")
    kernel.close()


def test_recovery_decision_does_not_retry_unknown_side_effect():
    decision = TaskKernel.recovery_decision("LOST_RESPONSE", action_dispatched=True, side_effect_risk="R2")
    assert decision.decision == "RECONCILE"
    assert decision.safe_to_retry is False
    assert decision.next_state == "RECONCILING"
