import asyncio
from pathlib import Path

import pytest

from scp.hands.hands_executor import HandsExecutor
from scp.hands.planner import HandsPlanner
from scp.hands.task_kernel_bridge import TaskKernelHandsBridge
from scp.pc_control.pc_controller import PCController
from scp.security.capability_epoch import CapabilityAuthority


# ==============================================================================
# T03 - HANDS AUTHORITY PEP (FA-05 ERADICATION & INV-AUTH-02 SCOPED VALIDATION)
# ==============================================================================
# Verifies that HandsExecutor never self-issues capability authority, rejects
# unauthorized actions fail-closed, validates exact scoped subjects, respects
# authority revocations, and requires explicit tokens for rollback.
# ==============================================================================


def _setup_executor(tmp_path: Path) -> tuple[HandsExecutor, Path, CapabilityAuthority]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    cap_state = tmp_path / "capability_state.json"
    cap_auth = CapabilityAuthority(cap_state)
    executor = HandsExecutor(
        controller=PCController(working_dir=workspace),
        capability_authority=cap_auth,
        data_dir=tmp_path / "hands_data",
    )
    return executor, workspace, cap_auth


def test_hands_executor_rejects_missing_token_fail_closed(tmp_path):
    """Execution with capability_token=None must fail closed without side-effects."""
    executor, workspace, _cap_auth = _setup_executor(tmp_path)
    target = workspace / "blocked_missing.txt"

    result = asyncio.run(
        executor.execute(
            action="pc.write_file",
            params={"path": str(target), "content": "forbidden_payload"},
            capability_level=3,
            approved=True,
            capability_token=None,
        )
    )

    assert result.get("success") is False
    assert "CapabilityRequiredError" in result.get("error", "")
    assert not target.exists(), "Side effect executed without capability token (FA-05 violation)"


def test_hands_executor_rejects_scope_mismatch_fail_closed(tmp_path):
    """Token authorized for a different action must be rejected fail-closed."""
    executor, workspace, cap_auth = _setup_executor(tmp_path)
    target = workspace / "blocked_scope.txt"
    status_token = cap_auth.issue("hands:pc.status")

    result = asyncio.run(
        executor.execute(
            action="pc.write_file",
            params={"path": str(target), "content": "forbidden_payload"},
            capability_level=3,
            approved=True,
            capability_token=status_token,
        )
    )

    assert result.get("success") is False
    assert "CapabilityScopeMismatchError" in result.get("error", "")
    assert not target.exists(), "Side effect executed with mismatched token scope (INV-AUTH-02 violation)"


def test_hands_executor_rejects_revoked_epoch(tmp_path):
    """Token with an obsolete or revoked epoch must be rejected fail-closed."""
    executor, workspace, cap_auth = _setup_executor(tmp_path)
    target = workspace / "blocked_revoked.txt"
    write_token = cap_auth.issue("hands:pc.write_file")

    # Revoke all tokens across the authority
    cap_auth.revoke(reason="security_alert", actor="sec_op")

    result = asyncio.run(
        executor.execute(
            action="pc.write_file",
            params={"path": str(target), "content": "forbidden_payload"},
            capability_level=3,
            approved=True,
            capability_token=write_token,
        )
    )

    assert result.get("success") is False
    error = result.get("error", "").lower()
    assert "revoked" in error or "stale" in error, f"Unexpected error: {result.get('error')}"
    assert not target.exists(), "Side effect executed with revoked capability token"


def test_hands_executor_rollback_requires_token(tmp_path):
    """Rollback requires an authorized token with scoped subject hands:rollback."""
    executor, workspace, cap_auth = _setup_executor(tmp_path)
    target = workspace / "rollback_target.txt"
    write_token = cap_auth.issue("hands:pc.write_file")

    write_res = asyncio.run(
        executor.execute(
            action="pc.write_file",
            params={"path": str(target), "content": "initial_content"},
            capability_level=3,
            approved=True,
            capability_token=write_token,
        )
    )
    assert write_res.get("success") is True
    checkpoint_id = write_res.get("checkpointId")
    assert checkpoint_id is not None
    assert target.exists()

    # 1. Rollback without token -> rejected fail-closed
    rb_missing = asyncio.run(
        executor.rollback(
            checkpoint_id=checkpoint_id,
            capability_level=3,
            approved=True,
            capability_token=None,
        )
    )
    assert rb_missing.get("success") is False
    assert "CapabilityRequiredError" in rb_missing.get("error", "")
    assert target.exists(), "Rollback occurred without capability token"

    # 2. Rollback with write token (scope mismatch) -> rejected fail-closed
    rb_wrong_scope = asyncio.run(
        executor.rollback(
            checkpoint_id=checkpoint_id,
            capability_level=3,
            approved=True,
            capability_token=write_token,
        )
    )
    assert rb_wrong_scope.get("success") is False
    assert "CapabilityScopeMismatchError" in rb_wrong_scope.get("error", "")
    assert target.exists(), "Rollback occurred with wrong token scope"

    # 3. Rollback with valid hands:rollback token -> succeeds and reverts state
    rollback_token = cap_auth.issue("hands:rollback")
    rb_valid = asyncio.run(
        executor.rollback(
            checkpoint_id=checkpoint_id,
            capability_level=3,
            approved=True,
            capability_token=rollback_token,
        )
    )
    assert rb_valid.get("success") is True, f"Rollback failed: {rb_valid}"
    assert not target.exists(), "Rollback did not remove newly created file"


# ==============================================================================
# TaskKernelHandsBridge PEP & Policy Denial Regression Tests
# ==============================================================================


def _setup_bridge(tmp_path: Path) -> tuple[TaskKernelHandsBridge, Path, CapabilityAuthority]:
    executor, workspace, cap_auth = _setup_executor(tmp_path)
    bridge = TaskKernelHandsBridge(executor, db_path=tmp_path / "kernel.sqlite3")
    return bridge, workspace, cap_auth


def test_bridge_execute_missing_token_clean_policy_denial_no_recovery(tmp_path: Path):
    """Direct bridge execution with capability_token=None must fail closed.

    Verifies:
    1. result['success'] is False
    2. 'CapabilityRequiredError' in error
    3. No 'OptimisticLockError' (no double-release crash)
    4. result['requiresRecovery'] is False
    5. result['kernel']['requiresRecovery'] is False
    6. result['kernel']['taskState'] == 'FAILED' (and 'state' == 'FAILED')
    7. target.exists() is False (zero side effects on disk)
    8. Durable database state is FAILED, active_lease_id is None, active_fencing_token is 0
    """
    bridge, workspace, _cap_auth = _setup_bridge(tmp_path)
    target = workspace / "blocked_bridge_missing.txt"

    try:
        result = asyncio.run(
            bridge.execute(
                action="pc.write_file",
                params={"path": str(target), "content": "test"},
                capability_level=3,
                approved=True,
                capability_token=None,
            )
        )

        # 1. Execution denial assertions
        assert result.get("success") is False
        assert "CapabilityRequiredError" in result.get("error", "")
        assert "OptimisticLockError" not in result.get("error", "")

        # 2. Kernel state assertions (strictly fail-closed, no recovery required)
        kernel_info = result.get("kernel", {})
        assert kernel_info.get("requiresRecovery") is False
        assert kernel_info.get("taskState") == "FAILED"
        assert kernel_info.get("state") == "FAILED"
        assert result.get("requiresRecovery") is False

        # 3. Disk side-effect assertion (zero side effects on policy denial)
        assert target.exists() is False, "Side effect executed without capability token (FA-05 violation)"

        # 4. Durable database state verification
        task_id = kernel_info.get("taskId")
        assert task_id is not None
        db_task = bridge.kernel.get_task(task_id)
        assert db_task["state"] == "FAILED"
        assert db_task["active_lease_id"] is None
        assert db_task["active_fencing_token"] == 0

        lease_row = bridge.kernel.conn.execute(
            "SELECT * FROM leases WHERE lease_id=?", (kernel_info.get("leaseId"),)
        ).fetchone()
        assert lease_row["released"] == 1, "Lease must be marked released in DB"
    finally:
        bridge.close()


def test_bridge_rejects_scope_mismatch_fail_closed(tmp_path: Path):
    """Bridge execution with token authorized for a different action must fail closed."""
    bridge, workspace, cap_auth = _setup_bridge(tmp_path)
    target = workspace / "blocked_bridge_scope.txt"
    status_token = cap_auth.issue("hands:pc.status")

    try:
        result = asyncio.run(
            bridge.execute(
                action="pc.write_file",
                params={"path": str(target), "content": "test"},
                capability_level=3,
                approved=True,
                capability_token=status_token,
            )
        )

        assert result.get("success") is False
        assert "CapabilityScopeMismatchError" in result.get("error", "")
        assert "OptimisticLockError" not in result.get("error", "")
        assert result.get("requiresRecovery") is False
        assert result.get("kernel", {}).get("requiresRecovery") is False
        assert result.get("kernel", {}).get("taskState") == "FAILED"
        assert result.get("kernel", {}).get("state") == "FAILED"
        assert target.exists() is False
    finally:
        bridge.close()


def test_bridge_rejects_revoked_token_fail_closed(tmp_path: Path):
    """Bridge execution with revoked token must fail closed without recovery."""
    bridge, workspace, cap_auth = _setup_bridge(tmp_path)
    target = workspace / "blocked_bridge_revoked.txt"
    write_token = cap_auth.issue("hands:pc.write_file")
    cap_auth.revoke(reason="security_alert", actor="sec_op")

    try:
        result = asyncio.run(
            bridge.execute(
                action="pc.write_file",
                params={"path": str(target), "content": "test"},
                capability_level=3,
                approved=True,
                capability_token=write_token,
            )
        )

        assert result.get("success") is False
        error = result.get("error", "").lower()
        assert "revoked" in error or "stale" in error
        assert "OptimisticLockError" not in result.get("error", "")
        assert result.get("requiresRecovery") is False
        assert result.get("kernel", {}).get("requiresRecovery") is False
        assert result.get("kernel", {}).get("taskState") == "FAILED"
        assert result.get("kernel", {}).get("state") == "FAILED"
        assert target.exists() is False
    finally:
        bridge.close()


# ==============================================================================
# HandsPlanner Step-Level Capability Token Regression Tests
# ==============================================================================


def test_planner_step_capability_token_preservation_and_execution(tmp_path: Path):
    """Step-level capabilityToken must be preserved during plan creation and applied during execution."""
    executor, workspace, cap_auth = _setup_executor(tmp_path)
    planner = HandsPlanner(executor=executor)

    # 1. Step with dict capabilityToken
    tok1 = cap_auth.issue("hands:pc.write_file")
    target1 = workspace / "plan_step1.txt"
    plan1 = planner.create_plan(
        "write step 1",
        [
            {
                "action": "pc.write_file",
                "params": {"path": str(target1), "content": "hello_step_1"},
                "capabilityToken": tok1.to_dict(),
            }
        ],
    )
    assert plan1["steps"][0]["capabilityToken"] is not None
    assert plan1["steps"][0]["capabilityToken"]["subject"] == "hands:pc.write_file"

    res1 = asyncio.run(planner.run_plan(plan1["planId"], capability_level=3, approved=True))
    assert res1.get("success") is True, f"Plan 1 run failed: {res1}"
    assert target1.exists()
    assert target1.read_text(encoding="utf-8") == "hello_step_1"

    # 2. Step with CapabilityToken dataclass object directly
    tok2 = cap_auth.issue("hands:pc.write_file")
    target2 = workspace / "plan_step2.txt"
    plan2 = planner.create_plan(
        "write step 2",
        [
            {
                "action": "pc.write_file",
                "params": {"path": str(target2), "content": "hello_step_2"},
                "capabilityToken": tok2,
            }
        ],
    )
    assert isinstance(plan2["steps"][0]["capabilityToken"], dict)
    assert plan2["steps"][0]["capabilityToken"]["subject"] == "hands:pc.write_file"

    res2 = asyncio.run(planner.run_plan(plan2["planId"], capability_level=3, approved=True))
    assert res2.get("success") is True, f"Plan 2 run failed: {res2}"
    assert target2.exists()
    assert target2.read_text(encoding="utf-8") == "hello_step_2"


def test_planner_step_capability_token_scope_mismatch_fails_closed(tmp_path: Path):
    """Step-level capability token with mismatched scope must fail closed."""
    executor, workspace, cap_auth = _setup_executor(tmp_path)
    planner = HandsPlanner(executor=executor)

    tok_mismatched = cap_auth.issue("hands:pc.status")
    target = workspace / "plan_mismatched.txt"
    plan = planner.create_plan(
        "mismatched step",
        [
            {
                "action": "pc.write_file",
                "params": {"path": str(target), "content": "should_fail"},
                "capabilityToken": tok_mismatched,
            }
        ],
    )
    res = asyncio.run(planner.run_plan(plan["planId"], capability_level=3, approved=True))
    assert res.get("success") is False
    assert "CapabilityScopeMismatchError" in str(res.get("result", {}).get("error", ""))
    assert not target.exists()
