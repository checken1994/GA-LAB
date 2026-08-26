from __future__ import annotations

from scripts.ops.scp_hourly_monitor import evaluate_policy, policy_payload


def result(allowed: bool) -> dict[str, object]:
    return {"allowed": allowed, "status": 200, "ok": True}


def test_policy_payload_is_dry_run_and_has_no_content_side_effect() -> None:
    payload = policy_payload("pc.write_file", 3, True)
    assert payload == {
        "action": "pc.write_file",
        "params": {},
        "capabilityLevel": 3,
        "approved": True,
        "dryRun": True,
    }


def test_policy_matrix_requires_deny_by_default_and_explicit_approval() -> None:
    results = {
        "status_l0": result(True),
        "write_l0_no_approval": result(False),
        "write_l3_no_approval": result(False),
        "write_l3_approved": result(True),
        "unknown_action": result(False),
    }
    assert evaluate_policy(results) == []


def test_policy_matrix_reports_each_missing_guard() -> None:
    results = {
        "status_l0": result(False),
        "write_l0_no_approval": result(True),
        "write_l3_no_approval": result(True),
        "write_l3_approved": result(False),
        "unknown_action": result(True),
    }
    failures = evaluate_policy(results)
    assert len(failures) == 5
    assert any("write_l0_no_approval" in failure for failure in failures)
    assert any("write_l3_no_approval" in failure for failure in failures)
    assert any("unknown_action" in failure for failure in failures)
    assert any("status_l0" in failure for failure in failures)
    assert any("write_l3_approved" in failure for failure in failures)
