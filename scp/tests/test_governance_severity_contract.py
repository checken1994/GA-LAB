"""Regression tests for the JudgeCore → Governance severity boundary."""

import pytest

from scp.meta.governance_v97 import Governance, GovernanceAction
from scp.meta.severity import Severity, normalize_severity
from scp.runtime.judge_parts.judgecore_mixin import _build_governance_antibody_results


def _decide(antibody_results, confidence=0.9):
    return Governance().decide(
        ctx={"domain": "test", "session_id": "severity-contract"},
        verdict={"confidence": confidence, "antibody_results": antibody_results},
        council_confidence=confidence,
    )


def test_provider_error_is_canonical_and_cannot_be_upheld():
    results = _build_governance_antibody_results([
        {"slm_name": "fixture-slm", "confidence": 0.9, "error": "provider timeout"}
    ])

    assert results == [{
        "passed": False,
        "severity": Severity.MEDIUM.value,
        "antibody": "fixture-slm",
        "details": "provider timeout",
    }]
    decision = _decide(results)
    assert decision.decision is GovernanceAction.ESCALATE
    assert decision.metadata["failed_antibody_count"] == 1


def test_low_confidence_provider_result_is_failed_and_cannot_be_upheld():
    results = _build_governance_antibody_results([
        {"slm_name": "fixture-slm", "confidence": 0.2, "reasoning": "uncertain"}
    ])

    assert results[0]["passed"] is False
    assert results[0]["severity"] == Severity.WARNING.value
    decision = _decide(results)
    assert decision.decision is GovernanceAction.ESCALATE


def test_unknown_failed_severity_is_visible_and_fail_closed():
    decision = _decide([{
        "passed": False,
        "severity": "provider_transport_unknown",
        "antibody": "fixture-slm",
    }])

    assert decision.decision is GovernanceAction.ESCALATE
    assert decision.metadata["unknown_severities"] == ["provider_transport_unknown"]
    assert "fail-closed" in decision.reason


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (Severity.CRITICAL, "critical"),
        ("HIGH", "high"),
        ("error", "medium"),
        ("warn", "warning"),
        ("not-a-severity", None),
        (None, None),
    ],
)
def test_normalize_severity_is_non_permissive(raw, expected):
    assert normalize_severity(raw) == expected


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        (Severity.CRITICAL.value, GovernanceAction.KILL),
        (Severity.HIGH.value, GovernanceAction.ESCALATE),
        (Severity.MEDIUM.value, GovernanceAction.ESCALATE),
        (Severity.LOW.value, GovernanceAction.ESCALATE),
        (Severity.INFO.value, GovernanceAction.ESCALATE),
    ],
)
def test_failed_canonical_severities_never_fall_through_to_uphold(severity, expected):
    decision = _decide([{"passed": False, "severity": severity, "antibody": "fixture"}])
    assert decision.decision is expected


def test_passed_info_result_is_still_upheld():
    decision = _decide([{"passed": True, "severity": Severity.INFO.value, "antibody": "fixture"}])
    assert decision.decision is GovernanceAction.UPHOLD
