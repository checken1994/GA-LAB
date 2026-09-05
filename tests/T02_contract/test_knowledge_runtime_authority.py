"""Issue #37: caller assertions and raw SQL must not mint epistemic maturity."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from scp.epistemic.evidence_store import EvidenceStore
from scp.epistemic.lineage import IndependenceStatus, LineageStore
from scp.knowledge.knowledge_runtime import (
    GoldLifecycle,
    KnowledgeStore,
    KnowledgeTransitionRejected,
    TemporalRevalidation,
)
from scp.knowledge.ontology import KnowledgeObject, KnowledgeStatus
from scp.knowledge.promotion_authority import PromotionAuthority


def build(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    evidence = EvidenceStore(tmp_path / "epistemic.db", tmp_path / "objects")
    lineage = LineageStore(tmp_path / "epistemic.db")
    lifecycle = GoldLifecycle(store, promotion_authority=PromotionAuthority(evidence, lineage))
    obj = KnowledgeObject(
        type="FACT",
        title="authority-bound fact",
        content={"subject": "svc", "predicate": "state", "object": "ok"},
        scope={"domain": "issue37"},
    )
    store.upsert(obj)
    return store, evidence, lineage, lifecycle, obj


def support(evidence, obj, source):
    return evidence.observe(
        kind="RUNTIME_OBSERVATION",
        content=f"support:{source}".encode(),
        collector_id="issue37-support",
        collector_version="1",
        source_id=source,
    )["evidence_id"]


def reality(evidence, obj, support_refs, episode, *, trusted=True, gold=False):
    payload = {
        "schema": "scp.reality_verification.v1",
        "knowledge_id": obj.knowledge_id,
        "knowledge_scope": obj.scope,
        "verdict": "VERIFIED",
        "input_evidence_refs": support_refs,
        "postconditions": [{"name": "postcondition", "passed": True}],
        "episode_id": episode,
        "temporal_validity": True,
        "adversarial_check": bool(gold),
        "counterexample_check": bool(gold),
        "temporal_stability": bool(gold),
    }
    return evidence.observe(
        kind="TEST_RESULT",
        content=json.dumps(payload, sort_keys=True).encode(),
        collector_id="scp-reality-verifier" if trusted else "caller-self-report",
        collector_version="1",
        source_id=f"verifier:{episode}",
        attempt_id=episode,
    )["evidence_id"]


def mark_independent(lineage, sources, refs):
    for i, a in enumerate(sources):
        for b in sources[i + 1:]:
            lineage.record_relation(
                a,
                b,
                status=IndependenceStatus.INDEPENDENT,
                basis=[{"type": "independent_runtime_observation"}],
                evidence_refs=refs,
            )


def to_corroborated(store, evidence, lineage, lifecycle, obj):
    a = support(evidence, obj, "source-a")
    b = support(evidence, obj, "source-b")
    lifecycle.promote(obj.knowledge_id, evidence_refs=[a])
    mark_independent(lineage, ["source-a", "source-b"], [a, b])
    lifecycle.promote(obj.knowledge_id, evidence_refs=[b])
    return [a, b]


def to_verified(store, evidence, lineage, lifecycle, obj):
    refs = to_corroborated(store, evidence, lineage, lifecycle, obj)
    c = support(evidence, obj, "source-c")
    refs.append(c)
    mark_independent(lineage, ["source-a", "source-b", "source-c"], refs)
    verification = reality(evidence, obj, refs, "verify-1")
    lifecycle.promote(
        obj.knowledge_id,
        evidence_refs=[c],
        verification_evidence_refs=[verification],
    )
    return refs


def test_fake_or_nonexistent_evidence_id_cannot_curate(tmp_path):
    store, evidence, lineage, lifecycle, obj = build(tmp_path)
    with pytest.raises(KnowledgeTransitionRejected) as excinfo:
        lifecycle.promote(obj.knowledge_id, evidence_refs=["ev_nonexistent_issue37"])
    assert any("missing or failed EvidenceStore integrity" in item for item in excinfo.value.missing_pieces)
    assert store.get(obj.knowledge_id).status is KnowledgeStatus.RAW


def test_forged_independent_lineage_scalar_cannot_corroborate(tmp_path):
    store, evidence, lineage, lifecycle, obj = build(tmp_path)
    a = support(evidence, obj, "source-a")
    b = support(evidence, obj, "source-b")
    lifecycle.promote(obj.knowledge_id, evidence_refs=[a])
    with pytest.raises(KnowledgeTransitionRejected):
        lifecycle.promote(obj.knowledge_id, evidence_refs=[b], independent_lineages=999)
    assert store.get(obj.knowledge_id).status is KnowledgeStatus.CURATED


def test_arbitrary_verification_id_cannot_grant_verified(tmp_path):
    store, evidence, lineage, lifecycle, obj = build(tmp_path)
    refs = to_corroborated(store, evidence, lineage, lifecycle, obj)
    untrusted = reality(evidence, obj, refs, "fake-verifier", trusted=False)
    with pytest.raises(KnowledgeTransitionRejected) as excinfo:
        lifecycle.promote(obj.knowledge_id, verification_evidence_refs=[untrusted])
    assert any("canonical RealityVerifier" in item for item in excinfo.value.missing_pieces)
    assert store.get(obj.knowledge_id).status is KnowledgeStatus.CORROBORATED


def test_scalar_success_observations_cannot_grant_gold(tmp_path):
    store, evidence, lineage, lifecycle, obj = build(tmp_path)
    to_verified(store, evidence, lineage, lifecycle, obj)
    with pytest.raises(KnowledgeTransitionRejected):
        lifecycle.promote(obj.knowledge_id, success_observations=999999)
    assert store.get(obj.knowledge_id).status is KnowledgeStatus.VERIFIED


def test_historical_transition_event_cannot_authorize_later_raw_update(tmp_path):
    store, evidence, lineage, lifecycle, obj = build(tmp_path)
    ev = support(evidence, obj, "source-a")
    lifecycle.promote(obj.knowledge_id, evidence_refs=[ev])

    scheduler = TemporalRevalidation(store, review_after_seconds={"STABLE": 1})
    scheduler.assign(
        obj.knowledge_id,
        "STABLE",
        now=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    assert scheduler.sweep(now=datetime.now(timezone.utc))[0].to_status == "UNDER_REVIEW"
    lifecycle.promote(
        obj.knowledge_id,
        target=KnowledgeStatus.CURATED,
        evidence_refs=[ev],
    )
    assert any(
        event["from_status"] == "CURATED" and event["to_status"] == "UNDER_REVIEW"
        for event in store.history(obj.knowledge_id)
    )

    foreign = sqlite3.connect(store.db_path)
    with pytest.raises(sqlite3.Error):
        foreign.execute(
            "UPDATE knowledge_objects SET status='UNDER_REVIEW' WHERE knowledge_id=?",
            (obj.knowledge_id,),
        )
    foreign.close()
    assert store.get(obj.knowledge_id).status is KnowledgeStatus.CURATED


def test_insert_or_replace_cannot_bypass_lifecycle_authority(tmp_path):
    store, evidence, lineage, lifecycle, obj = build(tmp_path)
    foreign = sqlite3.connect(store.db_path)
    with pytest.raises(sqlite3.IntegrityError, match="non-RAW knowledge insert forbidden"):
        foreign.execute(
            """
            INSERT OR REPLACE INTO knowledge_objects (
                knowledge_id, type, status, title, data_class, payload_json,
                independent_lineages, evidence_count, volatility,
                last_validated_at, review_after, created_at, updated_at
            )
            SELECT knowledge_id, type, 'GOLD', title, data_class, payload_json,
                   999, 999, volatility, last_validated_at, review_after, created_at, updated_at
            FROM knowledge_objects WHERE knowledge_id=?
            """,
            (obj.knowledge_id,),
        )
    foreign.close()
    assert store.get(obj.knowledge_id).status is KnowledgeStatus.RAW
