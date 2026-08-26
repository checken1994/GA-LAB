from __future__ import annotations

import time

import pytest

from scp.task_kernel import KernelError, TaskKernel


def queue_task(kernel: TaskKernel, task_id: str, owner: str, priority: int = 5, deadline_ms: int = 60_000) -> None:
    kernel.create_task(task_id, owner, f"goal-{task_id}", "R0", deadline_ms=deadline_ms, priority=priority)
    for state in ("PLANNING", "READY", "QUEUED"):
        kernel.transition(task_id, state, reason="queue-policy-test")


def test_claim_next_fair_share_alternates_owners_and_releases_quota(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    for task_id, owner in (("a1", "tenant-a"), ("a2", "tenant-a"), ("b1", "tenant-b"), ("b2", "tenant-b")):
        queue_task(kernel, task_id, owner)

    owners = []
    for _ in range(4):
        lease = kernel.claim_next("worker", max_active_per_owner=1, ttl_seconds=5)
        assert lease is not None
        owners.append(kernel.get_task(lease.task_id)["owner"])
        kernel.release(lease.task_id, lease.lease_id)

    assert owners == ["tenant-a", "tenant-b", "tenant-a", "tenant-b"]
    assert all(row["active"] == 0 for row in kernel.queue_status()["owners"])
    kernel.close()


def test_claim_next_bounded_fairness_stress_has_no_owner_starvation(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    for index in range(24):
        queue_task(kernel, f"a-{index:02d}", "tenant-a")
        queue_task(kernel, f"b-{index:02d}", "tenant-b")

    owners = []
    for _ in range(48):
        lease = kernel.claim_next("stress-worker", max_active_per_owner=1, ttl_seconds=5)
        assert lease is not None
        owners.append(kernel.get_task(lease.task_id)["owner"])
        kernel.release(lease.task_id, lease.lease_id)

    assert owners.count("tenant-a") == owners.count("tenant-b") == 24
    assert all(left != right for left, right in zip(owners, owners[1:]))
    kernel.close()


def test_claim_next_enforces_active_owner_quota(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    queue_task(kernel, "a1", "tenant-a")
    queue_task(kernel, "a2", "tenant-a")
    queue_task(kernel, "b1", "tenant-b")

    first = kernel.claim_next("worker", max_active_per_owner=1, ttl_seconds=5)
    second = kernel.claim_next("worker", max_active_per_owner=1, ttl_seconds=5)
    assert first is not None and second is not None
    assert kernel.get_task(first.task_id)["owner"] != kernel.get_task(second.task_id)["owner"]
    assert kernel.queue_status()["queued"] == 1

    kernel.release(first.task_id, first.lease_id)
    kernel.release(second.task_id, second.lease_id)
    assert kernel.queue_status()["owners"] == [
        {"owner": "tenant-a", "active": 0, "dispatch_count": 1, "last_dispatch_at": pytest.approx(kernel.queue_status()["owners"][0]["last_dispatch_at"])},
        {"owner": "tenant-b", "active": 0, "dispatch_count": 1, "last_dispatch_at": pytest.approx(kernel.queue_status()["owners"][1]["last_dispatch_at"])},
    ]
    kernel.close()


def test_claim_next_expires_overdue_task_and_claims_live_task(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    queue_task(kernel, "expired", "tenant-a", priority=0, deadline_ms=1)
    time.sleep(0.01)
    queue_task(kernel, "live", "tenant-b", priority=5, deadline_ms=60_000)

    lease = kernel.claim_next("worker", ttl_seconds=5)
    assert lease is not None
    assert lease.task_id == "live"
    assert kernel.get_task("expired")["state"] == "FAILED"
    assert any(event["type"] == "DEADLINE_EXPIRED" for event in kernel.get_events("expired"))
    kernel.release("live", lease.lease_id)
    kernel.close()


def test_create_task_rejects_invalid_priority(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    with pytest.raises(KernelError, match="priority"):
        kernel.create_task("bad", "tenant", "goal", priority=101)
    kernel.close()
