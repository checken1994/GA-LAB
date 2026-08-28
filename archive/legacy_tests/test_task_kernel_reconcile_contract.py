import multiprocessing
import os

import pytest

from scp.task_kernel import InvalidTransition, KernelError, TaskKernel


def queue_task(kernel: TaskKernel, task_id: str = "task") -> None:
    kernel.create_task(task_id, "test:user", "safe side effect", "R0")
    for state in ("PLANNING", "READY", "QUEUED"):
        kernel.transition(task_id, state, reason="reconcile-contract")


def start_action(kernel: TaskKernel):
    queue_task(kernel)
    lease = kernel.claim("task", "worker", ttl_seconds=5)
    kernel.start("task", lease.lease_id)
    logical_key, claimed = kernel.idempotency_claim(
        "task", "submit", "safe.side_effect", "resource-1"
    )
    assert claimed is True
    return lease, logical_key


def dispatch(kernel: TaskKernel):
    lease, logical_key = start_action(kernel)
    recorded = kernel.record_action_dispatched(
        "task",
        lease.lease_id,
        "submit",
        {"operation": "safe-side-effect", "resource": "resource-1"},
        0,
        logical_key,
        "provider-request-123",
        pre_observation_ref="obs://before-submit",
    )
    return lease, logical_key, recorded


def test_action_dispatch_persists_unknown_boundary_and_provider_identity(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    _, _, recorded = dispatch(kernel)
    assert recorded["state"] == "UNKNOWN"
    assert recorded["provider_request_id"] == "provider-request-123"
    assert kernel.get_task("task")["state"] == "UNKNOWN"
    checkpoint = kernel.get_checkpoint(recorded["checkpoint_id"])
    assert checkpoint["state"] == "UNKNOWN"
    assert "provider-request-123" in checkpoint["tool_result_json"]
    event_types = [event["type"] for event in kernel.get_events("task")]
    assert "ACTION_DISPATCHED" in event_types
    assert kernel.verify_journal("task")["hash_chain_valid"] is True
    kernel.close()


def test_unknown_cannot_retry_until_reconciled(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    _, _, recorded = dispatch(kernel)
    with pytest.raises(InvalidTransition):
        kernel.transition("task", "QUEUED", reason="unsafe_retry")
    kernel.enter_reconciling("task", recorded["checkpoint_id"], reason="lost_response")
    result = kernel.reconcile_unknown(
        "task",
        recorded["checkpoint_id"],
        "UNKNOWN",
        evidence_ref="provider://status/unknown",
        verifier_id="provider-state-reader",
    )
    assert result["state"] == "HUMAN_REVIEW"
    assert kernel.get_task("task")["state"] == "HUMAN_REVIEW"
    kernel.close()


def test_not_applied_reconcile_reopens_only_same_logical_action_for_retry(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    _, logical_key, recorded = dispatch(kernel)
    kernel.enter_reconciling("task", recorded["checkpoint_id"], reason="provider_checked")
    result = kernel.reconcile_unknown(
        "task",
        recorded["checkpoint_id"],
        "NOT_APPLIED",
        evidence_ref="provider://status/not-applied",
    )
    assert result["state"] == "QUEUED"
    assert kernel.get_task("task")["state"] == "QUEUED"
    same_key, reclaimed = kernel.idempotency_claim(
        "task", "submit", "safe.side_effect", "resource-1"
    )
    assert same_key == logical_key
    assert reclaimed is True
    kernel.close()


def test_applied_reconcile_never_auto_completes_and_requires_evidence(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    _, _, recorded = dispatch(kernel)
    kernel.enter_reconciling("task", recorded["checkpoint_id"], reason="provider_checked")
    with pytest.raises(KernelError, match="reconcile evidence"):
        kernel.reconcile_unknown(
            "task", recorded["checkpoint_id"], "APPLIED", evidence_ref=""
        )
    result = kernel.reconcile_unknown(
        "task",
        recorded["checkpoint_id"],
        "APPLIED",
        evidence_ref="provider://status/applied",
        verifier_id="provider-state-reader",
    )
    assert result["state"] == "HUMAN_REVIEW"
    assert result["state"] != "COMPLETED"
    kernel.close()


def test_reconcile_refuses_tampered_checkpoint(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    _, _, recorded = dispatch(kernel)
    kernel.conn.execute(
        "UPDATE checkpoints SET payload_hash=? WHERE checkpoint_id=?",
        ("sha256:tampered", recorded["checkpoint_id"]),
    )
    with pytest.raises(KernelError, match="checkpoint integrity"):
        kernel.enter_reconciling("task", recorded["checkpoint_id"], reason="lost_response")
    assert kernel.get_task("task")["state"] == "UNKNOWN"
    kernel.close()


def test_reconcile_checkpoint_mismatch_is_rejected(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    _, _, recorded = dispatch(kernel)
    with pytest.raises(KernelError, match="checkpoint task mismatch"):
        kernel.enter_reconciling("task", "cp_missing", reason="lost_response")
    kernel.close()


def _crash_after_dispatch(db_path: str, pipe) -> None:
    kernel = TaskKernel(db_path)
    lease = kernel.claim("task", "worker-process", ttl_seconds=5)
    kernel.start("task", lease.lease_id)
    logical_key, claimed = kernel.idempotency_claim(
        "task", "submit", "safe.side_effect", "resource-1"
    )
    assert claimed is True
    recorded = kernel.record_action_dispatched(
        "task",
        lease.lease_id,
        "submit",
        {"operation": "safe-side-effect", "resource": "resource-1"},
        0,
        logical_key,
        "provider-request-process-123",
        pre_observation_ref="obs://before-submit",
    )
    pipe.send(recorded["checkpoint_id"])
    pipe.close()
    os._exit(42)


def test_process_crash_after_submit_reopens_as_unknown_and_requires_reconcile(tmp_path):
    db = tmp_path / "kernel.sqlite3"
    kernel = TaskKernel(db)
    queue_task(kernel)
    kernel.close()
    context = multiprocessing.get_context("spawn")
    parent_pipe, child_pipe = context.Pipe(duplex=False)
    worker = context.Process(target=_crash_after_dispatch, args=(str(db), child_pipe))
    worker.start()
    try:
        assert parent_pipe.poll(30), "worker did not publish dispatch checkpoint"
        checkpoint_id = parent_pipe.recv()
        worker.join(20)
        if worker.is_alive():
            worker.terminate()
            worker.join(10)
        assert worker.exitcode == 42
    finally:
        parent_pipe.close()
    reopened = TaskKernel(db)
    try:
        assert reopened.get_task("task")["state"] == "UNKNOWN"
        reopened.enter_reconciling("task", checkpoint_id, reason="worker_crash_after_submit")
        result = reopened.reconcile_unknown(
            "task", checkpoint_id, "NOT_APPLIED", "provider://status/not-applied"
        )
        assert result["state"] == "QUEUED"
        assert reopened.verify_journal("task")["hash_chain_valid"] is True
    finally:
        reopened.close()
