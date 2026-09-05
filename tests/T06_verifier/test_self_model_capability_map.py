from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scp.epistemic.evidence_store import EvidenceStore
from scp.self_model import CapabilityMap


ROOT = Path(__file__).resolve().parents[2]


def _head_sha() -> str:
    """Ground-truth HEAD sha of the repo owning the Complete-SCP reference."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip().lower()


def _make(tmp_path):
    evidence = EvidenceStore(tmp_path / "epistemic.sqlite", tmp_path / "objects")
    model = CapabilityMap(
        governance_db_path=tmp_path / "governance.sqlite",
        evidence_store=evidence,
        reference_path=ROOT / "spec" / "complete_scp_reference.yaml",
        bindings_path=ROOT / "spec" / "implementation_bindings.yaml",
    )
    return evidence, model


def _proof(evidence, *, sha: str, level: str, capability_id: str = "epistemic.evidence"):
    return evidence.observe(
        kind="TEST_RESULT",
        content=f"proof-{sha}-{level}".encode(),
        collector_id="pytest",
        collector_version="1",
        metadata={"tested_sha": sha, "evidence_level": level, "capability_id": capability_id},
    )


def test_self_model_has_no_direct_mark_verified_api(tmp_path):
    evidence, model = _make(tmp_path)
    assert not hasattr(model, "mark_verified")
    state = model.recompute_capability("epistemic.evidence", "sha-A")
    assert state["maturity"] == "M2"  # importable != runtime proof
    assert state["status"] == "STATIC_PRESENT"
    model.close()
    evidence.db.close()


def test_same_sha_c_evidence_is_required_for_runtime_verified(tmp_path):
    evidence, model = _make(tmp_path)
    head = _head_sha()

    old = _proof(evidence, sha="sha-old", level="C")
    model.record_proof(
        capability_id="epistemic.evidence",
        evidence_id=old["evidence_id"],
        evidence_level="C",
        tested_sha="sha-old",
        archived=True,  # explicit override: HISTORICAL proof archival only
    )
    state = model.recompute_capability("epistemic.evidence", head)
    assert state["maturity"] == "M2"
    assert "historical proof" in " ".join(state["limitations"])

    current = _proof(evidence, sha=head, level="C")
    model.record_proof(
        capability_id="epistemic.evidence",
        evidence_id=current["evidence_id"],
        evidence_level="C",
        tested_sha=head,
    )
    state = model.recompute_capability("epistemic.evidence", head)
    assert state["maturity"] == "M4"
    assert state["status"] == "RUNTIME_VERIFIED"
    assert current["evidence_id"] in state["evidence_refs"]
    model.close()
    evidence.db.close()


def test_proof_metadata_must_match_requested_sha_and_level(tmp_path):
    evidence, model = _make(tmp_path)
    ev = _proof(evidence, sha="sha-A", level="B")
    with pytest.raises(ValueError):
        model.record_proof(
            capability_id="epistemic.evidence",
            evidence_id=ev["evidence_id"],
            evidence_level="C",
            tested_sha="sha-A",
        )
    with pytest.raises(ValueError):
        model.record_proof(
            capability_id="epistemic.evidence",
            evidence_id=ev["evidence_id"],
            evidence_level="B",
            tested_sha="sha-B",
        )
    model.close()
    evidence.db.close()


# ------------------------------------------------------------------------------
# M5: record_proof is bound to the tested commit - caller-supplied tested_sha is
# verified against `git rev-parse HEAD` unless archived=True is passed.
# ------------------------------------------------------------------------------


def test_proof_with_non_head_sha_is_rejected(tmp_path):
    evidence, model = _make(tmp_path)
    head = _head_sha()
    ev = _proof(evidence, sha="sha-old-not-head", level="C")
    with pytest.raises(ValueError, match="does not match current HEAD"):
        model.record_proof(
            capability_id="epistemic.evidence",
            evidence_id=ev["evidence_id"],
            evidence_level="C",
            tested_sha="sha-old-not-head",
        )
    # Even a DIFFERENT valid-looking sha that is simply not HEAD is rejected.
    forged = head[:-1] + ("0" if head[-1] != "0" else "1")
    ev2 = _proof(evidence, sha=forged, level="C")
    with pytest.raises(ValueError, match="does not match current HEAD"):
        model.record_proof(
            capability_id="epistemic.evidence",
            evidence_id=ev2["evidence_id"],
            evidence_level="C",
            tested_sha=forged,
        )
    model.close()
    evidence.db.close()


def test_archived_override_accepts_historical_sha_but_stays_sha_bound(tmp_path):
    evidence, model = _make(tmp_path)
    ev = _proof(evidence, sha="sha-archived-2025", level="C")
    proof_id = model.record_proof(
        capability_id="epistemic.evidence",
        evidence_id=ev["evidence_id"],
        evidence_level="C",
        tested_sha="sha-archived-2025",
        archived=True,
    )
    assert proof_id.startswith("proof_")
    rows = model.db.query("SELECT tested_sha FROM capability_proofs WHERE proof_id=?", (proof_id,))
    assert rows and rows[0]["tested_sha"] == "sha-archived-2025"
    # The archived proof must NOT support verification for the current sha.
    head = _head_sha()
    state = model.recompute_capability("epistemic.evidence", head)
    assert state["maturity"] == "M2", "archived proof must never verify the current sha"
    model.close()
    evidence.db.close()


def test_proof_evidence_must_declare_matching_capability_id(tmp_path):
    evidence, model = _make(tmp_path)
    head = _head_sha()
    # Metadata without capability_id -> rejected.
    ev_missing = evidence.observe(
        kind="TEST_RESULT",
        content=b"proof-no-capability",
        collector_id="pytest",
        collector_version="1",
        metadata={"tested_sha": head, "evidence_level": "C"},
    )
    with pytest.raises(ValueError, match="capability_id"):
        model.record_proof(
            capability_id="epistemic.evidence",
            evidence_id=ev_missing["evidence_id"],
            evidence_level="C",
            tested_sha=head,
        )
    # Metadata bound to ANOTHER capability -> rejected.
    ev_other = _proof(evidence, sha=head, level="C", capability_id="gateway.fallback")
    with pytest.raises(ValueError, match="capability_id"):
        model.record_proof(
            capability_id="epistemic.evidence",
            evidence_id=ev_other["evidence_id"],
            evidence_level="C",
            tested_sha=head,
        )
    model.close()
    evidence.db.close()


def test_capability_proofs_and_blindspots_reject_delete(tmp_path):
    evidence, model = _make(tmp_path)
    ev = _proof(evidence, sha="sha-archived", level="B")
    model.record_proof(
        capability_id="epistemic.evidence",
        evidence_id=ev["evidence_id"],
        evidence_level="B",
        tested_sha="sha-archived",
        archived=True,
    )
    with pytest.raises(Exception, match="append-only"):
        with model.db.transaction() as conn:
            conn.execute("DELETE FROM capability_proofs")
    blindspot_id = model.add_blindspot(
        capability_id="epistemic.evidence",
        unobservable="true randomness of providers",
        reason="no instrumentation can observe it directly",
    )
    with pytest.raises(Exception, match="append-only"):
        with model.db.transaction() as conn:
            conn.execute("DELETE FROM self_model_blindspots WHERE blindspot_id=?", (blindspot_id,))
    assert model.db.query("SELECT COUNT(*) AS n FROM capability_proofs")[0]["n"] == 1
    model.close()
    evidence.db.close()
