from __future__ import annotations

from pathlib import Path

import pytest

from scp.history.evidence_ledger import (
    EvidenceContractError,
    EvidenceRecord,
    append_record,
    promotion_evidence,
)


def _record(kind: str, lineage: str, subject: str = "patch-1") -> EvidenceRecord:
    return EvidenceRecord(
        subject_id=subject,
        lineage=lineage,
        kind=kind,
        locator=f"{lineage}:{kind}",
        observed_claim="claim observed and verified",
        independent_of="different-origin",
    )


def test_evidence_ledger_requires_independence_and_verified_status(tmp_path: Path):
    with pytest.raises(EvidenceContractError):
        append_record(tmp_path / "evidence.jsonl", EvidenceRecord(
            subject_id="same-origin", lineage="same-origin", kind="official_document", locator="x",
            observed_claim="x", independent_of="same-origin",
        ))
    with pytest.raises(EvidenceContractError):
        append_record(tmp_path / "evidence.jsonl", EvidenceRecord(
            subject_id="patch-1", lineage="docs", kind="official_document", locator="x",
            observed_claim="x", independent_of="other", status="unverified",
        ))


def test_two_independent_lineages_are_required(tmp_path: Path):
    path = tmp_path / "evidence.jsonl"
    append_record(path, _record("official_document", "python-docs"))
    assert promotion_evidence(path, "patch-1")["eligible"] is False
    append_record(path, _record("independent_runtime", "pc-runtime"))
    decision = promotion_evidence(path, "patch-1")
    assert decision["eligible"] is True
    assert decision["lineages"] == ["pc-runtime", "python-docs"]


def test_hash_chain_is_append_only(tmp_path: Path):
    path = tmp_path / "evidence.jsonl"
    first = append_record(path, _record("official_document", "python-docs"))
    second = append_record(path, _record("independent_runtime", "pc-runtime"))
    assert first["previous_hash"] == "GENESIS"
    assert second["previous_hash"] == first["record_hash"]
