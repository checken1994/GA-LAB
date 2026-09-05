import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scp.core.phase0 import EvidenceStore as LegacyEvidenceStore
from scp.core.phase0 import Phase0Store
from scp.epistemic import runtime_bridge as rb
from scp.epistemic.lineage import IndependenceStatus

POLICY = ROOT / "spec" / "data_policies.yaml"


def _bridge(tmp_path):
    stack = rb.build_epistemic_stack(tmp_path / "foundation", POLICY)
    return rb.RuntimeEvidenceBridge(stack)


# ==============================================================================
# M4 EPISTEMIC CUTOVER — runtime verdict cycle records IMMUTABLE evidence via
# GovernedEvidenceWriter (PrivacyWriteGate) + LineageStore; corrections only
# via SUPERSEDES; legacy phase0 is a deprecated routed facade.
# ==============================================================================


def test_verdict_cycle_records_immutable_evidence(tmp_path):
    bridge = _bridge(tmp_path)
    q = "Tính 2+3"
    ev1 = bridge.record_model_response(
        slm_name="math_slm", answer="5", confidence=0.9, entity="2+3",
        attribute="math", raw_data={"answer": "5"}, question=q,
        cycle_count=100, trace_id="cycle-100",
    )
    ev2 = bridge.record_model_response(
        slm_name="bio_slm", answer="5", confidence=0.8, question=q,
        cycle_count=100, trace_id="cycle-100",
    )
    reality = bridge.record_reality_check(
        source="v13", real_value=5, raw_data={"real_value": 5},
        question=q, cycle_count=100, trace_id="cycle-100",
    )
    conclusion = bridge.record_conclusion(
        question=q, ai_answer="5", verdict="PASS", confidence=0.95,
        domain="math", reasoning="ok", cycle_count=100,
        trace_id="cycle-100", source_ids=["math_slm", "bio_slm", "v13"],
    )
    assert ev1 and ev2 and reality and conclusion
    # orchestration (as in scpv14_process_mixin Step 8): link + decision
    for eid in (ev1, ev2, reality):
        bridge.link(eid, conclusion, "VERIFIES" if eid == reality else "SUPPORTS")
    bridge.record_decision(conclusion, "verdict_pass", notes="cycle=100")

    # occurrence identity != content identity (identical content, new occurrence)
    same = bridge.record_model_response(
        slm_name="math_slm", answer="5", confidence=0.9, entity="2+3",
        attribute="math", raw_data={"answer": "5"}, question=q,
        cycle_count=101, trace_id="cycle-101",
    )
    r1 = bridge.stack.store.get(ev1)
    r_same = bridge.stack.store.get(same)
    assert r1["content_hash"] == r_same["content_hash"], "same content must dedupe the blob"
    assert r1["evidence_id"] != r_same["evidence_id"], "occurrences must never be deduped"
    assert r1["kind"] == "MODEL_RESPONSE"  # proves "model said 5", never truth
    assert bridge.stack.store.get(reality)["kind"] == "RUNTIME_OBSERVATION"

    # authority relations: SLM responses SUPPORT, reality check VERIFIES
    links = bridge.stack.store.db.query("SELECT * FROM evidence_links")
    rel = {(l["parent_evidence_id"], l["child_evidence_id"], l["relation"]) for l in links}
    assert (ev1, conclusion, "SUPPORTS") in rel
    assert (ev2, conclusion, "SUPPORTS") in rel
    assert (reality, conclusion, "VERIFIES") in rel

    # LineageStore tracked the sources conservatively (all pairs UNKNOWN default)
    meta = json.loads(bridge.stack.store.get(conclusion)["metadata_json"])
    assert meta["lineage"]["source_count"] == 3
    assert meta["lineage"]["unknown_pairs"] == 3
    assert meta["lineage"]["known_independent_lineages"] == 1
    lineage_rows = bridge.stack.lineage.db.query("SELECT * FROM source_independence")
    assert lineage_rows, "lineage relations must be persisted"
    assert all(r["status"] == IndependenceStatus.UNKNOWN_INDEPENDENCE.value for r in lineage_rows)

    # decision recorded as new evidence linked DECIDES
    drel = bridge.stack.store.db.query("SELECT * FROM evidence_links WHERE relation='DECIDES'")
    assert any(l["child_evidence_id"] == conclusion for l in drel)


def test_evidence_table_rejects_inplace_update(tmp_path):
    bridge = _bridge(tmp_path)
    ev = bridge.record_model_response(slm_name="math_slm", answer="5", confidence=0.9)
    with pytest.raises(Exception):
        bridge.stack.store.db.execute(
            "UPDATE evidence SET metadata_json='tampered' WHERE evidence_id=?", (ev,)
        )


def test_supersede_creates_new_evidence_and_relation_never_edit(tmp_path):
    bridge = _bridge(tmp_path)
    old = bridge.record_reality_check(source="v13", real_value=4, question="q", cycle_count=1)
    old_record = dict(bridge.stack.store.get(old))
    new = bridge.supersede(
        old,
        kind="RUNTIME_OBSERVATION",
        content=b'{"real_value": 5}',
        source_id="v13",
        metadata={"observation_type": "reality_check", "correction_of": old},
    )
    assert new["evidence_id"] != old, "correction must be a NEW evidence occurrence"
    after = bridge.stack.store.get(old)
    assert {k: after[k] for k in old_record} == old_record, "old record must never be edited"
    rel = bridge.stack.store.db.query("SELECT * FROM evidence_links WHERE relation='SUPERSEDES'")
    assert any(
        l["parent_evidence_id"] == old and l["child_evidence_id"] == new["evidence_id"]
        for l in rel
    )


def test_verification_outcome_is_new_evidence_never_edit(tmp_path):
    bridge = _bridge(tmp_path)
    target = bridge.record_model_response(slm_name="math_slm", answer="5", confidence=0.9)
    target_record = dict(bridge.stack.store.get(target))
    vid = bridge.record_verification(target, verified=True, by="reality_engine")
    assert vid != target
    assert bridge.has_evidence(vid)
    assert bridge.stack.store.get(vid)["kind"] == "TEST_RESULT"
    vrel = bridge.stack.store.db.query("SELECT * FROM evidence_links WHERE relation='VERIFIES'")
    assert any(l["parent_evidence_id"] == vid and l["child_evidence_id"] == target for l in vrel)
    assert {k: bridge.stack.store.get(target)[k] for k in target_record} == target_record


def test_phase0_facade_routes_through_epistemic_stack(tmp_path, monkeypatch):
    bridge = _bridge(tmp_path)
    monkeypatch.setattr(rb, "get_runtime_bridge", lambda: bridge)

    with pytest.warns(DeprecationWarning):
        legacy_eid = Phase0Store.add_evidence(
            evidence_type="slm_response", source="math_slm", entity="e",
            attribute="math", value="5", confidence=0.9, raw_data={"answer": "5"},
        )
    assert legacy_eid
    mapped = bridge.resolve_evidence_id(legacy_eid)
    assert mapped != legacy_eid, "legacy id must be registered in the authority index"
    assert bridge.has_evidence(mapped), "authority copy must exist"
    authority_meta = json.loads(bridge.stack.store.get(mapped)["metadata_json"])
    assert authority_meta["legacy_evidence_id"] == legacy_eid

    with pytest.warns(DeprecationWarning):
        cid = Phase0Store.add_conclusion(
            question="q", ai_answer="a", verdict="PASS", confidence=0.9,
            domain="math", reasoning="r", cycle_count=1,
        )
    assert bridge.has_evidence(bridge.resolve_evidence_id(cid))

    with pytest.warns(DeprecationWarning):
        lid = Phase0Store.link_evidence(cid, legacy_eid, weight=0.9, role="slm")
    assert lid
    rel = bridge.stack.store.db.query("SELECT * FROM evidence_links WHERE relation='SLM'")
    assert any(
        l["parent_evidence_id"] == bridge.resolve_evidence_id(cid)
        and l["child_evidence_id"] == mapped
        for l in rel
    ), "authority relation must be recorded for the legacy link"

    with pytest.warns(DeprecationWarning):
        Phase0Store.add_decision(cid, "verdict_pass", notes="cycle=1")
    decisions = bridge.stack.store.db.query(
        "SELECT * FROM evidence WHERE metadata_json LIKE ?", ("%phase0_compat_decision%",)
    )
    assert decisions, "decision must be routed to the authority store"

    # verify(): outcome = NEW immutable TEST_RESULT evidence; legacy UPDATE is
    # only a deprecated read-model sync.
    with pytest.warns(DeprecationWarning):
        assert LegacyEvidenceStore.verify(legacy_eid, by="test") is True
    ver = bridge.stack.store.db.query("SELECT * FROM evidence WHERE kind='TEST_RESULT'")
    assert ver, "verification outcome must be recorded as immutable evidence"
    assert f"target_evidence_id\":\"{legacy_eid}" in ver[0]["metadata_json"].replace(" ", "").replace(
        "'", '"'
    ) or legacy_eid in ver[0]["metadata_json"]

    # supersede(): authority relation recorded even for unresolved legacy ids
    with pytest.warns(DeprecationWarning):
        assert LegacyEvidenceStore.supersede(legacy_eid, "unknown-new-id") is True
    sup = bridge.stack.store.db.query(
        "SELECT * FROM evidence WHERE metadata_json LIKE ?", ("%legacy_relation%",)
    )
    assert any("SUPERSEDES" in (r["metadata_json"] or "") for r in sup)


def test_privacy_gate_redacts_secret_before_storage(tmp_path):
    bridge = _bridge(tmp_path)
    secret = "sk-abcdef1234567890abcdef"
    ev = bridge.record_model_response(slm_name="slm", answer=f"key {secret}", confidence=0.5)
    stored = bridge.stack.store.read_content(ev)
    assert secret.encode() not in stored, "raw secret must never be stored"
    meta = json.loads(bridge.stack.store.get(ev)["metadata_json"])
    assert meta.get("privacy_write_decision") == "REDACT"
    assert meta.get("privacy_redactions"), "redaction fingerprints must be recorded"


def test_process_mixin_uses_bridge_not_legacy_phase0():
    from scp.runtime.engine_parts import scpv14_process_mixin as mixin

    src = inspect.getsource(mixin.SCPV14ProcessMixin.process)
    assert "get_runtime_bridge" in src, "runtime must record through the epistemic bridge"
    assert "self.phase0.add_evidence" not in src, "mutable phase0 path must be cut over"
    assert "self.phase0.add_decision" not in src, "mutable phase0 path must be cut over"
