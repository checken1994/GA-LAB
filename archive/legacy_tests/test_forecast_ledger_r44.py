from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scp.forecast import (
    ForecastContractError,
    ForecastLedger,
    ForecastRegistry,
    score_binary_forecasts,
)


def _case(case_id: str = "C-001") -> dict:
    return {
        "id": case_id,
        "domain": "test",
        "claimant": "fixture",
        "claim": "An atomic event will occur by the deadline.",
        "date": "2026-08-14",
        "url": "https://example.test/claim",
        "verdict": "REFINE",
        "confidence": "MEDIUM",
        "antibodies": ["AB01"],
        "outcome_code": 9,
    }


def _write_registry(path, *, valid_manifest: bool = True):
    payload = {
        "program": "R44 fixture",
        "total_cases": 1,
        "lock_date": "2026-08-14T00:00:00Z",
        "cases": [_case()],
    }
    if valid_manifest:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


_FORECAST_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "forecast" / "scp_reality_program_v4_pure_prospective_1.json"

def test_current_v4_registry_is_loaded_as_unverified_anchor():
    registry = ForecastRegistry.load(_FORECAST_FIXTURE)
    assert registry.snapshot.case_count == 210
    assert registry.snapshot.manifest_status == "MISMATCH"
    assert all(case["outcome_code"] == 9 for case in registry.cases)


def test_resolution_is_rejected_when_registry_anchor_is_unverified(tmp_path):
    path = tmp_path / "registry.json"
    _write_registry(path, valid_manifest=False)
    registry = ForecastRegistry.load(path)
    ledger = ForecastLedger(registry, tmp_path / "outcomes.jsonl")

    result = ledger.resolve_case(
        "C-001",
        outcome_code=3,
        evidence_url="https://example.test/evidence",
        evidence_sha256="a" * 64,
        adjudicator_id="independent-verifier-1",
    )
    assert result["event"] == "resolution_rejected"
    assert result["reason"] == "registry_anchor_unverified"
    assert ledger.status()["resolved_events"] == 0


def test_verified_resolution_requires_evidence_and_is_immutable(tmp_path):
    path = tmp_path / "registry.json"
    _write_registry(path, valid_manifest=True)
    registry = ForecastRegistry.load(path, strict_manifest=True)
    ledger = ForecastLedger(registry, tmp_path / "outcomes.jsonl")

    accepted = ledger.resolve_case(
        "C-001",
        outcome_code=3,
        evidence_url="https://example.test/evidence",
        evidence_sha256="b" * 64,
        adjudicator_id="independent-verifier-1",
    )
    assert accepted["event"] == "outcome_observed"
    assert ledger.status()["resolved_events"] == 1

    conflict = ledger.resolve_case(
        "C-001",
        outcome_code=1,
        evidence_url="https://example.test/other",
        evidence_sha256="c" * 64,
        adjudicator_id="independent-verifier-2",
    )
    assert conflict["event"] == "resolution_rejected"
    assert conflict["reason"] == "conflicting_resolution_is_immutable"
    assert ledger.current_outcomes()["C-001"]["outcome_code"] == 3


def test_unresolved_is_not_scored_as_negative():
    result = score_binary_forecasts(
        [
            {"case_id": "resolved", "probability": 0.9, "actual": 1, "outcome_code": 1},
            {"case_id": "pending", "probability": 0.1, "actual": 0, "outcome_code": 9},
        ]
    )
    assert result["status"] == "SCORED"
    assert result["n"] == 1
    assert result["excluded_unresolved"] == 1
    assert abs(result["brier_score"] - 0.01) < 1e-12


def test_no_resolved_forecasts_is_explicit_not_zero_score():
    result = score_binary_forecasts([{"case_id": "pending", "probability": 0.8, "outcome_code": 9}])
    assert result["status"] == "NO_RESOLVED_FORECASTS"
    assert result["n"] == 0
    assert result["brier_score"] is None


def test_invalid_probability_fails_closed():
    try:
        score_binary_forecasts([{"probability": 1.1, "actual": 1, "outcome_code": 1}])
    except ForecastContractError as exc:
        assert "[0, 1]" in str(exc)
    else:
        raise AssertionError("invalid probability must be rejected")
