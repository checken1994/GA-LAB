from __future__ import annotations

import pytest

from scp.task_kernel import (
    InvalidTransition,
    KernelError,
    StaleLease,
    TaskKernel,
)


def _setup_running_task(kernel: TaskKernel, task_id: str = "adv-1", owner: str = "adv-owner"):
    kernel.create_task(task_id, owner, "adversarial test goal", "R1")
    for s in ("PLANNING", "READY", "QUEUED"):
        kernel.transition(task_id, s, actor="setup")
    lease = kernel.claim(task_id, "worker-1", ttl_seconds=300)
    kernel.start(task_id, lease.lease_id)
    return lease


def test_boot_recovery_decrements_queue_active_and_permits_subsequent_claims(tmp_path):
    db_path = tmp_path / "kernel.sqlite3"
    k1 = TaskKernel(db_path)
    try:
        _setup_running_task(k1, "adv-boot-1", "owner-alpha")
        status = k1.queue_status()
        owner_entry = next(o for o in status["owners"] if o["owner"] == "owner-alpha")
        assert owner_entry["active"] == 1
    finally:
        k1.close()

    # Reboot
    k_boot = TaskKernel(db_path)
    try:
        report = k_boot.recover_on_boot()
        assert len(report["recovered"]) == 1

        # Queue active count MUST be decremented to 0
        status_after = k_boot.queue_status()
        owner_after = next(o for o in status_after["owners"] if o["owner"] == "owner-alpha")
        assert owner_after["active"] == 0, "queue_accounts.active leaked across boot recovery"

        # Subsequent claim_next for owner-alpha must not be blocked
        k_boot.create_task("adv-boot-2", "owner-alpha", "second task", "R1")
        for s in ("PLANNING", "READY", "QUEUED"):
            k_boot.transition("adv-boot-2", s, actor="setup")
        claimed = k_boot.claim_next("worker-2", max_active_per_owner=1)
        assert claimed is not None, "owner was permanently blocked by leaked queue_accounts quota"
        assert claimed.task_id == "adv-boot-2"
    finally:
        k_boot.close()


def test_transition_to_human_review_or_recovering_releases_lease_and_queue_quota(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    try:
        lease = _setup_running_task(kernel, "adv-hr-1", "owner-beta")
        assert kernel.queue_status()["owners"][0]["active"] == 1

        # Worker moves task to HUMAN_REVIEW (non-terminal, non-leased)
        kernel.transition("adv-hr-1", "HUMAN_REVIEW", actor="worker-1", reason="need_human")

        # In DB, lease must be released
        lease_row = kernel.conn.execute("SELECT * FROM leases WHERE lease_id=?", (lease.lease_id,)).fetchone()
        assert lease_row["released"] == 1, "lease remained unreleased after transition out of leased state"

        # Queue slot must be released
        assert kernel.queue_status()["owners"][0]["active"] == 0, "queue slot leaked on transition to HUMAN_REVIEW"

        # Instance bound lease must be cleared
        assert "adv-hr-1" not in getattr(kernel, "_bound_leases", {})

        # Owner can claim another task immediately
        kernel.create_task("adv-hr-2", "owner-beta", "second task", "R1")
        for s in ("PLANNING", "READY", "QUEUED"):
            kernel.transition("adv-hr-2", s, actor="setup")
        claimed = kernel.claim_next("worker-2", max_active_per_owner=1)
        assert claimed is not None
    finally:
        kernel.close()


def test_checkpoint_rejected_on_non_running_or_mismatched_task(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    try:
        lease = _setup_running_task(kernel, "adv-cp-1", "owner-gamma")
        # Transition out of running to HUMAN_REVIEW
        kernel.transition("adv-cp-1", "HUMAN_REVIEW", actor="worker-1", reason="need_human")

        # Checkpoint on task in HUMAN_REVIEW must fail
        with pytest.raises((InvalidTransition, StaleLease)):
            kernel.checkpoint(
                "adv-cp-1",
                lease.lease_id,
                "step-1",
                "RUNNING",
                {"action": "test"},
                0,
                "idem-cp-1",
            )
    finally:
        kernel.close()


def test_rogue_worker_cannot_hijack_transition_by_quoting_active_lease_id(tmp_path):
    db_path = tmp_path / "kernel.sqlite3"
    worker_legit = TaskKernel(db_path)
    worker_rogue = TaskKernel(db_path)
    try:
        lease = _setup_running_task(worker_legit, "adv-hijack-1", "owner-delta")

        # Rogue worker reads active_lease_id from DB
        active_lease = worker_rogue.get_task("adv-hijack-1")["active_lease_id"]
        assert active_lease == lease.lease_id

        # Rogue worker attempts to transition task using stolen lease_id
        with pytest.raises(StaleLease):
            worker_rogue.transition("adv-hijack-1", "HUMAN_REVIEW", lease_id=active_lease)

        # Task remains in RUNNING for legitimate worker
        assert worker_legit.get_task("adv-hijack-1")["state"] == "RUNNING"
        # Legitimate worker can transition
        worker_legit.transition("adv-hijack-1", "VERIFYING", actor="worker-1")
        assert worker_legit.get_task("adv-hijack-1")["state"] == "VERIFYING"
    finally:
        worker_legit.close()
        worker_rogue.close()


def test_release_increments_version_with_occ(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    try:
        lease = _setup_running_task(kernel, "adv-rel-1", "owner-epsilon")
        v_before = kernel.get_task("adv-rel-1")["version"]

        kernel.release("adv-rel-1", lease.lease_id)
        task_after = kernel.get_task("adv-rel-1")
        assert task_after["version"] == v_before + 1, "release() must increment version"
        assert task_after["active_lease_id"] is None
        assert task_after["active_fencing_token"] == 0
    finally:
        kernel.close()


def test_rebuild_projection_reconstructs_active_lease_and_fencing_token(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    try:
        lease = _setup_running_task(kernel, "adv-proj-1", "owner-zeta")
        task_before = kernel.get_task("adv-proj-1")
        assert task_before["active_lease_id"] == lease.lease_id
        assert task_before["active_fencing_token"] == lease.fencing_token

        # Rebuild projection
        rebuilt = kernel.rebuild_projection("adv-proj-1")
        assert rebuilt["active_lease_id"] == lease.lease_id
        assert rebuilt["active_fencing_token"] == lease.fencing_token

        # Now transition to CANCELLED
        kernel.set_task_kill("adv-proj-1", actor="test")
        rebuilt_cancelled = kernel.rebuild_projection("adv-proj-1")
        assert rebuilt_cancelled["state"] == "CANCELLED"
        assert rebuilt_cancelled["active_lease_id"] is None
        assert rebuilt_cancelled["active_fencing_token"] == 0
    finally:
        kernel.close()


def test_rogue_worker_cannot_start_heartbeat_release_or_checkpoint(tmp_path):
    db_path = tmp_path / "kernel.sqlite3"
    worker_legit = TaskKernel(db_path)
    worker_rogue = TaskKernel(db_path)
    try:
        worker_legit.create_task("adv-auth-1", "owner-eta", "adversarial auth goal", "R1")
        for s in ("PLANNING", "READY", "QUEUED"):
            worker_legit.transition("adv-auth-1", s, actor="setup")
        lease = worker_legit.claim("adv-auth-1", "worker-legit", ttl_seconds=300)

        # Rogue worker cannot call start()
        with pytest.raises(StaleLease):
            worker_rogue.start("adv-auth-1", lease.lease_id)

        # Legitimate worker starts task
        worker_legit.start("adv-auth-1", lease.lease_id)

        # Rogue worker cannot call heartbeat()
        with pytest.raises(StaleLease):
            worker_rogue.heartbeat("adv-auth-1", lease.lease_id)

        # Rogue worker cannot call checkpoint()
        with pytest.raises(StaleLease):
            worker_rogue.checkpoint(
                "adv-auth-1",
                lease.lease_id,
                "step-1",
                "RUNNING",
                {"action": "test"},
                0,
                "idem-auth-1",
            )

        # Rogue worker cannot call release()
        with pytest.raises(StaleLease):
            worker_rogue.release("adv-auth-1", lease.lease_id)

        # Legitimate worker can heartbeat, checkpoint, and release
        worker_legit.heartbeat("adv-auth-1", lease.lease_id)
        cp_id = worker_legit.checkpoint(
            "adv-auth-1",
            lease.lease_id,
            "step-1",
            "RUNNING",
            {"action": "test"},
            0,
            "idem-auth-1",
        )
        assert cp_id.startswith("cp_")
        worker_legit.release("adv-auth-1", lease.lease_id)
        assert worker_legit.get_task("adv-auth-1")["active_lease_id"] is None
    finally:
        worker_legit.close()
        worker_rogue.close()


def test_enter_reconciling_releases_leases_and_decrements_queue_active(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    try:
        lease = _setup_running_task(kernel, "adv-rec-1", "owner-theta")
        idem_key, claimed = kernel.idempotency_claim("adv-rec-1", "step-1", "http.post", "https://api.test/charge")
        assert claimed is True
        disp = kernel.record_action_dispatched(
            "adv-rec-1",
            lease.lease_id,
            "step-1",
            {"action": "charge"},
            1,
            idem_key,
            "provider-req-1",
        )
        cp_id = disp["checkpoint_id"]
        assert kernel.get_task("adv-rec-1")["state"] == "UNKNOWN"

        # Enter reconciling
        kernel.enter_reconciling("adv-rec-1", cp_id)
        task_rec = kernel.get_task("adv-rec-1")
        assert task_rec["state"] == "RECONCILING"
        assert task_rec["active_lease_id"] is None

        # Lease must be released in SQLite
        lease_row = kernel.conn.execute("SELECT released FROM leases WHERE lease_id=?", (lease.lease_id,)).fetchone()
        assert lease_row["released"] == 1, "lease remained unreleased in enter_reconciling"

        # Queue active count must be decremented
        owner_status = next(o for o in kernel.queue_status()["owners"] if o["owner"] == "owner-theta")
        assert owner_status["active"] == 0, "queue active count leaked in enter_reconciling"

        # Zombie heartbeat must fail
        with pytest.raises(StaleLease):
            kernel.heartbeat("adv-rec-1", lease.lease_id)

        # Reconcile outcome NOT_APPLIED moves task to QUEUED
        kernel.reconcile_unknown("adv-rec-1", cp_id, "NOT_APPLIED", "ev_not_applied", "verifier-1")
        assert kernel.get_task("adv-rec-1")["state"] == "QUEUED"

        # Owner can claim the queued task without queue starvation
        claimed_next = kernel.claim_next("worker-2", max_active_per_owner=1)
        assert claimed_next is not None, "owner was starved after reconcile NOT_APPLIED"
        assert claimed_next.task_id == "adv-rec-1"
    finally:
        kernel.close()


def test_expire_leases_recovers_verifying_and_checkpointed_tasks(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    try:
        # 1. VERIFYING task with expired lease
        l_ver = _setup_running_task(kernel, "adv-exp-ver", "owner-iota")
        kernel.transition("adv-exp-ver", "VERIFYING")
        # Force expiration in DB
        kernel.conn.execute("UPDATE leases SET expires_at=0 WHERE lease_id=?", (l_ver.lease_id,))

        # 2. CHECKPOINTED task with expired lease
        l_cp = _setup_running_task(kernel, "adv-exp-cp", "owner-kappa")
        kernel.checkpoint("adv-exp-cp", l_cp.lease_id, "s1", "RUNNING", {"a": 1}, 1, "idem-exp-cp")
        kernel.transition("adv-exp-cp", "CHECKPOINTED")
        kernel.conn.execute("UPDATE leases SET expires_at=0 WHERE lease_id=?", (l_cp.lease_id,))

        expired = kernel.expire_leases()
        assert l_ver.lease_id in expired
        assert l_cp.lease_id in expired

        # VERIFYING task must transition to HUMAN_REVIEW (fail-closed)
        t_ver = kernel.get_task("adv-exp-ver")
        assert t_ver["state"] == "HUMAN_REVIEW", f"Expected HUMAN_REVIEW, got {t_ver['state']}"
        assert t_ver["active_lease_id"] is None

        # CHECKPOINTED task must transition to QUEUED (resumable)
        t_cp = kernel.get_task("adv-exp-cp")
        assert t_cp["state"] == "QUEUED", f"Expected QUEUED, got {t_cp['state']}"
        assert t_cp["active_lease_id"] is None
    finally:
        kernel.close()


def test_rogue_worker_cannot_commit_completed_or_verification_result(tmp_path):
    db_path = tmp_path / "kernel.sqlite3"
    worker_legit = TaskKernel(db_path)
    worker_rogue = TaskKernel(db_path)
    try:
        lease = _setup_running_task(worker_legit, "adv-complete-1", "owner-lambda")
        worker_legit.transition("adv-complete-1", "VERIFYING")

        # Rogue worker reads active_lease_id and tries to call commit_completed
        active_lease = worker_rogue.get_task("adv-complete-1")["active_lease_id"]
        assert active_lease == lease.lease_id

        with pytest.raises(StaleLease):
            worker_rogue.commit_completed("adv-complete-1", active_lease, "VERIFIED", "test://fake-evidence")

        # Rogue worker also cannot call commit_verification_result
        with pytest.raises(StaleLease):
            worker_rogue.commit_verification_result(
                "adv-complete-1",
                active_lease,
                {"verdict": "VERIFIED", "verifier_id": "rogue", "evidence_ref": "test://fake"},
            )

        # Legitimate worker can complete task
        completed_task = worker_legit.commit_completed("adv-complete-1", lease.lease_id, "VERIFIED", "test://legit")
        assert completed_task["state"] == "COMPLETED"
        assert completed_task["active_lease_id"] is None
    finally:
        worker_legit.close()
        worker_rogue.close()


def test_rebuild_projection_preserves_active_lease_for_unknown_state(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    try:
        lease = _setup_running_task(kernel, "adv-proj-unk-1", "owner-mu")
        idem, _ = kernel.idempotency_claim("adv-proj-unk-1", "s1", "http.post", "https://api.test/charge")
        kernel.record_action_dispatched("adv-proj-unk-1", lease.lease_id, "s1", {"a": 1}, 1, idem, "req-1")

        task_before = kernel.get_task("adv-proj-unk-1")
        assert task_before["state"] == "UNKNOWN"
        assert task_before["active_lease_id"] == lease.lease_id

        # Rebuild projection must retain the active lease for UNKNOWN tasks
        rebuilt = kernel.rebuild_projection("adv-proj-unk-1")
        assert rebuilt["state"] == "UNKNOWN"
        assert rebuilt["active_lease_id"] == lease.lease_id
        assert rebuilt["active_fencing_token"] == lease.fencing_token
    finally:
        kernel.close()


def test_occ_conflict_precedes_state_transition_validation(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    try:
        kernel.create_task("adv-occ-1", "owner-nu", "occ test goal")
        # Task version is 1 in CREATED
        kernel.transition("adv-occ-1", "PLANNING")
        # Task version is now 2 in PLANNING

        # Attempt transition specifying stale expected_version=1
        with pytest.raises(StaleLease) as excinfo:
            kernel.transition("adv-occ-1", "PLANNING", expected_version=1)
        assert "concurrency conflict" in str(excinfo.value)
    finally:
        kernel.close()


def test_kernel_cancel_method_alias_and_quota_cleanup(tmp_path):
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    try:
        lease = _setup_running_task(kernel, "adv-cancel-1", "owner-xi")
        cancelled = kernel.cancel("adv-cancel-1")
        assert cancelled["state"] == "CANCELLED"
        assert cancelled["active_lease_id"] is None
        assert cancelled["active_fencing_token"] == 0

        # Lease is marked released and quota is cleaned up
        lease_row = kernel.conn.execute("SELECT * FROM leases WHERE lease_id=?", (lease.lease_id,)).fetchone()
        assert lease_row["released"] == 1

        queue_status = kernel.queue_status()
        owner_status = next(o for o in queue_status["owners"] if o["owner"] == "owner-xi")
        assert owner_status["active"] == 0
    finally:
        kernel.close()


def test_gap11_raw_transition_to_completed_is_strictly_forbidden(tmp_path):
    """GAP-11: Raw transition() to COMPLETED must raise InvalidTransition.

    Tasks can only be completed via commit_completed() with valid evidence and lease.
    """
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    try:
        lease = _setup_running_task(kernel, "adv-gap11-1", "owner-gap11")
        kernel.transition("adv-gap11-1", "VERIFYING")

        # Rogue attempt: bypass evidence verification via transition()
        with pytest.raises(InvalidTransition) as excinfo:
            kernel.transition(
                "adv-gap11-1",
                "COMPLETED",
                lease_id=lease.lease_id,
                actor="rogue_worker",
                reason="fake pass attempt",
            )
        assert "direct transition to COMPLETED is forbidden" in str(excinfo.value)

        # Verify DB state is unmodified
        task = kernel.get_task("adv-gap11-1")
        assert task["state"] == "VERIFYING"
        events = kernel.get_events("adv-gap11-1")
        assert not any(e["to_state"] == "COMPLETED" for e in events)

        # Legitimate path: commit_completed with valid evidence
        completed = kernel.commit_completed(
            "adv-gap11-1",
            lease.lease_id,
            "VERIFIED",
            "evidence://audit/proof-hash-1234",
        )
        assert completed["state"] == "COMPLETED"
    finally:
        kernel.close()


def test_gap11_adversarial_replay_attack_blocked(tmp_path):
    """GAP-11 Adversarial: Replaying an existing TASK_COMPLETED event_id must fail closed."""
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    try:
        lease = _setup_running_task(kernel, "adv-gap11-replay-1", "owner-replay")
        kernel.transition("adv-gap11-replay-1", "VERIFYING")
        completed = kernel.commit_completed(
            "adv-gap11-replay-1",
            lease.lease_id,
            "VERIFIED",
            "evidence://valid/proof-1",
        )
        assert completed["state"] == "COMPLETED"
        events = kernel.get_events("adv-gap11-replay-1")
        completed_evt = [e for e in events if e["to_state"] == "COMPLETED"][0]
        completed_event_id = completed_evt["event_id"]

        # Setup victim task in VERIFYING
        lease_victim = _setup_running_task(kernel, "adv-gap11-victim", "owner-replay")
        kernel.transition("adv-gap11-victim", "VERIFYING")

        # Attack: replay the valid COMPLETED event_id on the victim task
        with pytest.raises(InvalidTransition) as excinfo:
            kernel.transition(
                "adv-gap11-victim",
                "COMPLETED",
                event_id=completed_event_id,
                lease_id=lease_victim.lease_id,
                actor="verifier",
                reason="postcondition_verified",
            )
        assert "direct transition to COMPLETED is forbidden" in str(excinfo.value)
        task_victim = kernel.get_task("adv-gap11-victim")
        assert task_victim["state"] == "VERIFYING"
    finally:
        kernel.close()


def test_gap11_adversarial_all_states_direct_transition_blocked(tmp_path):
    """GAP-11 Adversarial: transition() to COMPLETED is blocked from non-existent and unstarted tasks."""
    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
    try:
        # 1. Non-existent task
        with pytest.raises(InvalidTransition) as excinfo:
            kernel.transition("non-existent-task-id", "COMPLETED")
        assert "direct transition to COMPLETED is forbidden" in str(excinfo.value)

        # 2. Freshly created task (CREATED state)
        kernel.create_task("adv-created-task", "owner-created", "goal")
        with pytest.raises(InvalidTransition) as excinfo:
            kernel.transition("adv-created-task", "COMPLETED")
        assert "direct transition to COMPLETED is forbidden" in str(excinfo.value)
        assert kernel.get_task("adv-created-task")["state"] == "CREATED"

        # 3. Task in PLANNING state
        kernel.transition("adv-created-task", "PLANNING")
        with pytest.raises(InvalidTransition) as excinfo:
            kernel.transition("adv-created-task", "COMPLETED")
        assert "direct transition to COMPLETED is forbidden" in str(excinfo.value)
        assert kernel.get_task("adv-created-task")["state"] == "PLANNING"
    finally:
        kernel.close()


def test_gap11_rebuild_projection_with_tampered_journal_fails_closed(tmp_path):
    """GAP-11 Adversarial: Raw SQLite tampering with events table fails journal integrity and rebuild refuses."""
    import sqlite3
    db_file = tmp_path / "kernel.sqlite3"
    kernel = TaskKernel(db_file)
    try:
        lease = _setup_running_task(kernel, "adv-tamper-1", "owner-tamper")
        kernel.transition("adv-tamper-1", "VERIFYING")

        # Directly inject forged COMPLETED event with broken hash into SQLite
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO events(event_id, task_id, seq, type, from_state, to_state, actor, reason, payload_json, event_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "evt_forged_raw",
                "adv-tamper-1",
                99,
                "STATE_TRANSITION",
                "VERIFYING",
                "COMPLETED",
                "forger",
                "fake",
                "{}",
                "fake_hash_value",
                "2026-09-08T00:00:00Z",
            ),
        )
        conn.commit()
        conn.close()

        # Rebuild projection MUST fail-closed due to invalid journal integrity
        with pytest.raises(KernelError) as excinfo:
            kernel.rebuild_projection("adv-tamper-1")
        assert "journal integrity invalid" in str(excinfo.value)

        # Verify DB tasks table was NOT modified
        assert kernel.get_task("adv-tamper-1")["state"] == "VERIFYING"
    finally:
        kernel.close()


def test_watchdog_lease_expiry_racing_commit_completed_blocks_stale_worker(tmp_path):
    """Adversarial R2: Expired lease watchdog racing against commit_completed().

    Verifies that passive TTL expiry or active watchdog expiry strictly blocks
    commit_completed() with StaleLease and cannot force a COMPLETED state.
    """
    import time
    db_file = tmp_path / "kernel.sqlite3"
    kernel = TaskKernel(db_file)
    try:
        # 1. Passive TTL expiry
        lease1 = _setup_running_task(kernel, "adv-watchdog-1", "owner-watchdog")
        kernel.transition("adv-watchdog-1", "VERIFYING")
        # Manually expire the lease in DB
        kernel.conn.execute("UPDATE leases SET expires_at=? WHERE lease_id=?", (time.time() - 1.0, lease1.lease_id))

        with pytest.raises(StaleLease):
            kernel.commit_completed(
                "adv-watchdog-1",
                lease1.lease_id,
                "VERIFIED",
                "evidence://passive-expired",
            )
        assert kernel.get_task("adv-watchdog-1")["state"] == "VERIFYING"

        # 2. Active watchdog expiry via expire_leases()
        lease2 = _setup_running_task(kernel, "adv-watchdog-2", "owner-watchdog")
        kernel.transition("adv-watchdog-2", "VERIFYING")
        expired = kernel.expire_leases(now=time.time() + 1000.0)
        assert lease2.lease_id in expired
        # Task must now be in HUMAN_REVIEW
        assert kernel.get_task("adv-watchdog-2")["state"] == "HUMAN_REVIEW"
        assert kernel.get_task("adv-watchdog-2")["active_lease_id"] is None

        # Stale worker attempts commit_completed()
        with pytest.raises(StaleLease):
            kernel.commit_completed(
                "adv-watchdog-2",
                lease2.lease_id,
                "VERIFIED",
                "evidence://stale-worker-after-watchdog",
            )
        assert kernel.get_task("adv-watchdog-2")["state"] == "HUMAN_REVIEW"
        events2 = kernel.get_events("adv-watchdog-2")
        assert not any(e["to_state"] == "COMPLETED" for e in events2)
    finally:
        kernel.close()


def test_fencing_token_staleness_blocks_commit_completed_after_reclaim(tmp_path):
    """Adversarial R2: Fencing token staleness strictly rejects commit_completed()."""
    import time
    db_file = tmp_path / "kernel.sqlite3"
    kernel = TaskKernel(db_file)
    try:
        lease1 = _setup_running_task(kernel, "adv-fence-1", "owner-fence")
        # Expire lease1
        kernel.expire_leases(now=time.time() + 1000.0)
        assert kernel.get_task("adv-fence-1")["state"] == "RECOVERING"

        # Re-queue task and claim by worker 2
        kernel.transition("adv-fence-1", "QUEUED")
        lease2 = kernel.claim("adv-fence-1", "worker-2", ttl_seconds=60.0)
        assert lease2.fencing_token > lease1.fencing_token
        kernel.start("adv-fence-1", lease2.lease_id)
        kernel.transition("adv-fence-1", "VERIFYING")

        # Worker 1 (stale fencing token) attempts commit_completed()
        with pytest.raises(StaleLease):
            kernel.commit_completed(
                "adv-fence-1",
                lease1.lease_id,
                "VERIFIED",
                "evidence://stale-token-commit",
            )

        task = kernel.get_task("adv-fence-1")
        assert task["state"] == "VERIFYING"
        assert task["active_lease_id"] == lease2.lease_id
        assert task["active_fencing_token"] == lease2.fencing_token
    finally:
        kernel.close()


def test_multithreaded_lease_watchdog_race_with_commit_completed(tmp_path):
    """Adversarial R2: True concurrent race between expire_leases() and commit_completed()."""
    import concurrent.futures
    import time
    db_file = tmp_path / "kernel.sqlite3"
    kernel = TaskKernel(db_file)
    thread_kernels = []
    try:
        num_tasks = 8
        tasks = []
        for i in range(num_tasks):
            tid = f"adv-race-{i}"
            kernel.create_task(tid, "owner-race", f"goal {i}")
            for s in ("PLANNING", "READY", "QUEUED"):
                kernel.transition(tid, s, actor="setup")
            lease = kernel.claim(tid, f"worker-{i}", ttl_seconds=0.1)
            kernel.start(tid, lease.lease_id)
            kernel.transition(tid, "VERIFYING", lease_id=lease.lease_id)
            tasks.append((tid, lease.lease_id))

        def watchdog_action(tid, lid):
            try:
                time.sleep(0.02)
                k = TaskKernel(db_file)
                thread_kernels.append(k)
                k.expire_leases(now=time.time() + 0.1)
            except Exception:
                pass

        def commit_action(tid, lid):
            try:
                time.sleep(0.02)
                k = TaskKernel(db_file)
                thread_kernels.append(k)
                k._bound_leases[tid] = lid
                k.commit_completed(tid, lid, "VERIFIED", f"evidence://{tid}")
            except Exception:
                pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            futures = []
            for tid, lid in tasks:
                futures.append(executor.submit(watchdog_action, tid, lid))
                futures.append(executor.submit(commit_action, tid, lid))
            concurrent.futures.wait(futures)

        for tid, lid in tasks:
            task = kernel.get_task(tid)
            assert task["state"] in {"COMPLETED", "HUMAN_REVIEW"}, f"Task {tid} in unexpected state: {task['state']}"
            events = kernel.get_events(tid)
            event_types = [e["type"] for e in events]
            if task["state"] == "COMPLETED":
                assert "TASK_COMPLETED" in event_types
                assert event_types[-1] == "TASK_COMPLETED"
            elif task["state"] == "HUMAN_REVIEW":
                assert "LEASE_EXPIRED" in event_types
                assert "TASK_COMPLETED" not in event_types
    finally:
        for tk in thread_kernels:
            try:
                tk.close()
            except Exception:
                pass
        kernel.close()




