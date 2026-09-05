"""T02 contract tests — S06 Knowledge System runtime (M8).

Covers: GoldLifecycle promotion ladder + demotion on contradiction,
TemporalRevalidation (volatility classes, stale knowledge excluded from
decisions), and the FTS5 RetrievalIndex as a rebuildable ACCELERATOR whose
authority stays in the SQLite knowledge store (CE-S06-01/02/03).
"""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scp.knowledge.knowledge_runtime import (
    DEFAULT_REVIEW_AFTER_SECONDS,
    GoldLifecycle,
    KnowledgeNotFound,
    KnowledgeStore,
    KnowledgeTransitionRejected,
    RetrievalIndex,
    RetrievalIndexMissing,
    TemporalRevalidation,
    VolatilityClass,
)
from scp.knowledge.ontology import KnowledgeObject, KnowledgeStatus
from scp.epistemic.evidence_store import EvidenceStore
from scp.epistemic.lineage import IndependenceStatus, LineageStore
from scp.knowledge.promotion_authority import PromotionAuthority


# ==============================================================================
# helpers
# ==============================================================================

def make_store(tmp_path) -> tuple[KnowledgeStore, RetrievalIndex, GoldLifecycle, TemporalRevalidation]:
    store = KnowledgeStore(tmp_path / "knowledge_runtime.db")
    index = store.attach_index(RetrievalIndex(store))
    evidence = EvidenceStore(tmp_path / "epistemic.db", tmp_path / "evidence_objects")
    lineage = LineageStore(tmp_path / "epistemic.db")
    lifecycle = GoldLifecycle(store, promotion_authority=PromotionAuthority(evidence, lineage))
    revalidation = TemporalRevalidation(store)
    return store, index, lifecycle, revalidation


def make_fact(tmp_scope: dict | None = None, title: str = "provider/model-x prompt price") -> KnowledgeObject:
    return KnowledgeObject(
        type="FACT",
        title=title,
        content={
            "subject": "provider/model-x",
            "predicate": "prompt_price",
            "object": 0,
            "unit": "USD/token",
        },
        scope=tmp_scope or {"domain": "provider-pricing"},
    )


def _support(lifecycle: GoldLifecycle, knowledge_id: str, source_id: str) -> str:
    authority = lifecycle.promotion_authority
    assert authority is not None
    record = authority.evidence_store.observe(
        kind="RUNTIME_OBSERVATION",
        content=f"support:{knowledge_id}:{source_id}".encode(),
        collector_id="t02-support",
        collector_version="1",
        source_id=source_id,
    )
    return record["evidence_id"]


def _mark_independent(lifecycle: GoldLifecycle, sources: list[str], refs: list[str]) -> None:
    authority = lifecycle.promotion_authority
    assert authority is not None
    for i, source_a in enumerate(sources):
        for source_b in sources[i + 1:]:
            authority.lineage_store.record_relation(
                source_a,
                source_b,
                status=IndependenceStatus.INDEPENDENT,
                basis=[{"type": "independent_runtime_observation"}],
                evidence_refs=refs,
            )


def _reality(
    lifecycle: GoldLifecycle,
    knowledge_id: str,
    *,
    episode_id: str,
    gold_checks: bool = False,
) -> str:
    authority = lifecycle.promotion_authority
    assert authority is not None
    obj = lifecycle.store.get(knowledge_id)
    support_refs = list((obj.validity or {}).get("support_evidence_refs", []))
    payload = {
        "schema": "scp.reality_verification.v1",
        "knowledge_id": knowledge_id,
        "knowledge_scope": obj.scope,
        "verdict": "VERIFIED",
        "input_evidence_refs": support_refs,
        "postconditions": [{"name": "claim_postcondition", "passed": True}],
        "episode_id": episode_id,
        "temporal_validity": True,
        "adversarial_check": bool(gold_checks),
        "counterexample_check": bool(gold_checks),
        "temporal_stability": bool(gold_checks),
    }
    import json
    record = authority.evidence_store.observe(
        kind="TEST_RESULT",
        content=json.dumps(payload, sort_keys=True).encode(),
        collector_id="scp-reality-verifier",
        collector_version="1",
        source_id=f"reality:{episode_id}",
        attempt_id=episode_id,
    )
    return record["evidence_id"]


def walk_to_gold(lifecycle: GoldLifecycle, knowledge_id: str) -> None:
    a = _support(lifecycle, knowledge_id, "source-a")
    lifecycle.promote(knowledge_id, evidence_refs=[a])

    b = _support(lifecycle, knowledge_id, "source-b")
    _mark_independent(lifecycle, ["source-a", "source-b"], [a, b])
    lifecycle.promote(knowledge_id, evidence_refs=[b])

    c = _support(lifecycle, knowledge_id, "source-c")
    _mark_independent(lifecycle, ["source-a", "source-b", "source-c"], [a, b, c])
    verification = _reality(lifecycle, knowledge_id, episode_id="verify-1")
    lifecycle.promote(
        knowledge_id,
        evidence_refs=[c],
        verification_evidence_refs=[verification],
    )

    success_1 = _reality(lifecycle, knowledge_id, episode_id="gold-1", gold_checks=True)
    success_2 = _reality(lifecycle, knowledge_id, episode_id="gold-2", gold_checks=True)
    lifecycle.promote(knowledge_id, success_evidence_refs=[success_1, success_2])


# ==============================================================================
# GoldLifecycle: promotion ladder
# ==============================================================================

def test_promote_walk_raw_to_gold_all_valid_transitions_pass(tmp_path):
    store, _, lifecycle, _ = make_store(tmp_path)
    obj = make_fact()
    store.upsert(obj)
    walk_to_gold(lifecycle, obj.knowledge_id)

    gold = store.get(obj.knowledge_id)
    assert gold.status is KnowledgeStatus.GOLD
    assert gold.independent_lineages >= 3
    assert gold.validity["last_validated_at"]
    assert gold.validity["review_after"]
    assert gold.validity["repeated_success_observations"] == 2
    assert len(gold.validity["verified_success_episode_ids"]) == 2
    assert [event["to_status"] for event in store.history(obj.knowledge_id)] == [
        "CURATED", "CORROBORATED", "VERIFIED", "GOLD",
    ]


def test_raw_to_gold_direct_jump_rejected_and_state_untouched(tmp_path):
    store, _, lifecycle, _ = make_store(tmp_path)
    obj = make_fact()
    store.upsert(obj)

    with pytest.raises(KnowledgeTransitionRejected) as excinfo:
        lifecycle.promote(obj.knowledge_id, target=KnowledgeStatus.GOLD)
    assert "INVALID_TRANSITION" in excinfo.value.reason_codes
    assert "must be walked rung by rung" in str(excinfo.value)

    # fail-closed: nothing changed, nothing recorded
    assert store.get(obj.knowledge_id).status is KnowledgeStatus.RAW
    assert store.history(obj.knowledge_id) == []

    # skipping a middle rung (RAW -> CORROBORATED) is equally impossible
    with pytest.raises(KnowledgeTransitionRejected):
        lifecycle.promote(obj.knowledge_id, target=KnowledgeStatus.CORROBORATED)


def test_gold_without_evidence_refs_rejected(tmp_path):
    with pytest.raises(ValueError):
        KnowledgeObject(type="FACT", title="gold", content={"k": "v"}, status="GOLD")

    store, _, _, _ = make_store(tmp_path)
    forged = KnowledgeObject(
        type="FACT",
        title="verified but evidence-less",
        content={"k": "v"},
        status="VERIFIED",
        scope={"domain": "d"},
    )
    with pytest.raises(sqlite3.IntegrityError, match="non-RAW knowledge insert forbidden"):
        store.upsert(forged)
    assert store.find(forged.knowledge_id) is None


def test_corroboration_requires_independent_lineage_threshold(tmp_path):
    store, _, lifecycle, _ = make_store(tmp_path)
    obj = make_fact()
    store.upsert(obj)
    a = _support(lifecycle, obj.knowledge_id, "source-a")
    lifecycle.promote(obj.knowledge_id, evidence_refs=[a])
    b = _support(lifecycle, obj.knowledge_id, "source-b")

    with pytest.raises(KnowledgeTransitionRejected) as excinfo:
        lifecycle.promote(
            obj.knowledge_id,
            evidence_refs=[b],
            independent_lineages=999,
        )
    assert any("independent_lineage" in piece for piece in excinfo.value.missing_pieces)
    assert store.get(obj.knowledge_id).status is KnowledgeStatus.CURATED

    _mark_independent(lifecycle, ["source-a", "source-b"], [a, b])
    result = lifecycle.promote(obj.knowledge_id, evidence_refs=[b])
    assert result.to_status == "CORROBORATED"
    assert store.get(obj.knowledge_id).independent_lineages == 2


def test_curated_with_open_contradiction_cannot_corroborate(tmp_path):
    store, _, lifecycle, _ = make_store(tmp_path)
    obj = make_fact()
    store.upsert(obj)
    a = _support(lifecycle, obj.knowledge_id, "source-a")
    lifecycle.promote(obj.knowledge_id, evidence_refs=[a])
    b = _support(lifecycle, obj.knowledge_id, "source-b")
    _mark_independent(lifecycle, ["source-a", "source-b"], [a, b])
    lifecycle.report_contradiction(
        obj.knowledge_id,
        evidence_ref=b,
        description="unit price contradicts other sources",
    )
    with pytest.raises(KnowledgeTransitionRejected) as excinfo:
        lifecycle.promote(obj.knowledge_id, evidence_refs=[b])
    assert any("contradiction" in piece for piece in excinfo.value.missing_pieces)


# ==============================================================================
# GoldLifecycle: contradiction demotion + retirement
# ==============================================================================

def test_contradiction_demotes_gold_to_under_review_then_demoted(tmp_path):
    store, _, lifecycle, _ = make_store(tmp_path)
    obj = make_fact()
    store.upsert(obj)
    walk_to_gold(lifecycle, obj.knowledge_id)

    contradiction_id, transition = lifecycle.report_contradiction(
        obj.knowledge_id,
        evidence_ref="ev_contra_d0000000000000004",
        description="provider changed price, evidence contradicts gold claim",
    )
    assert transition.from_status == "GOLD" and transition.to_status == "UNDER_REVIEW"
    assert store.get(obj.knowledge_id).status is KnowledgeStatus.UNDER_REVIEW
    open_rows = [
        row for row in store.contradictions(obj.knowledge_id) if row["resolution"] == "OPEN"
    ]
    assert [row["contradiction_id"] for row in open_rows] == [contradiction_id]

    result = lifecycle.demote(obj.knowledge_id, reason="contradiction confirmed by re-check")
    assert (result.from_status, result.to_status) == ("UNDER_REVIEW", "DEMOTED")
    assert store.get(obj.knowledge_id).status is KnowledgeStatus.DEMOTED

    # history preserved, never overwritten: every rung + the demotion path
    assert [event["to_status"] for event in store.history(obj.knowledge_id)] == [
        "CURATED", "CORROBORATED", "VERIFIED", "GOLD", "UNDER_REVIEW", "DEMOTED",
    ]
    # demoted knowledge is not decision-grade anymore
    assert store.usable_for_decisions(store.get(obj.knowledge_id)) is False


def test_retire_old_gold_past_review_after(tmp_path):
    store, _, lifecycle, _ = make_store(tmp_path)
    now = datetime.now(timezone.utc)
    # tightened schedule: review_after = assigned_at + 1h
    scheduler = TemporalRevalidation(store, review_after_seconds={"STABLE": 3600})

    old_gold = make_fact()
    store.upsert(old_gold)
    walk_to_gold(lifecycle, old_gold.knowledge_id)
    scheduler.assign(old_gold.knowledge_id, "STABLE", now=now - timedelta(hours=2))

    young_gold = make_fact(title="fresh gold claim")
    store.upsert(young_gold)
    walk_to_gold(lifecycle, young_gold.knowledge_id)
    scheduler.assign(young_gold.knowledge_id, "STABLE")  # reviewed right now

    assert scheduler.is_stale(old_gold.knowledge_id, now=now) is True
    assert scheduler.is_stale(young_gold.knowledge_id, now=now) is False

    retired = lifecycle.retire_expired_gold(now=now)
    assert [r.knowledge_id for r in retired] == [old_gold.knowledge_id]
    assert store.get(old_gold.knowledge_id).status is KnowledgeStatus.RETIRED
    assert store.get(young_gold.knowledge_id).status is KnowledgeStatus.GOLD

    with pytest.raises(KnowledgeTransitionRejected):
        lifecycle.retire(old_gold.knowledge_id, reason="")  # retire requires a reason


# ==============================================================================
# TemporalRevalidation: volatility classes
# ==============================================================================

def test_volatility_classes_complete_with_monotonic_defaults():
    assert {cls.value for cls in VolatilityClass} == {
        "STABLE", "SLOW", "MEDIUM", "FAST", "VERY_FAST",
    }
    ordered = [VolatilityClass.STABLE, VolatilityClass.SLOW, VolatilityClass.MEDIUM,
               VolatilityClass.FAST, VolatilityClass.VERY_FAST]
    seconds = [DEFAULT_REVIEW_AFTER_SECONDS[cls] for cls in ordered]
    assert seconds == sorted(seconds, reverse=True), "STABLE reviews least often, VERY_FAST most often"
    assert all(value > 0 for value in seconds)


def test_revalidation_flags_stable_knowledge_past_review_after(tmp_path):
    store, index, lifecycle, revalidation = make_store(tmp_path)

    stable = make_fact()
    store.upsert(stable)
    walk_to_gold(lifecycle, stable.knowledge_id)  # gets default GOLD schedule
    # tighten the STABLE policy so the review window is reachable in-test
    fast_revalidation = TemporalRevalidation(store, review_after_seconds={"STABLE": 3600})
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    fast_revalidation.assign(stable.knowledge_id, "STABLE", now=past)
    assert fast_revalidation.is_stale(stable.knowledge_id) is True

    fresh = make_fact(title="fresh knowledge")
    store.upsert(fresh)
    walk_to_gold(lifecycle, fresh.knowledge_id)
    fast_revalidation.assign(fresh.knowledge_id, "STABLE")  # reviewed just now

    outcomes = fast_revalidation.sweep()
    assert [o.knowledge_id for o in outcomes] == [stable.knowledge_id]
    assert outcomes[0].from_status == "GOLD" and outcomes[0].to_status == "UNDER_REVIEW"
    assert outcomes[0].reason_code == "REVIEW_AFTER_EXPIRED"
    assert store.get(stable.knowledge_id).status is KnowledgeStatus.UNDER_REVIEW
    assert store.get(fresh.knowledge_id).status is KnowledgeStatus.GOLD

    # stale knowledge is flagged for re-check, not silently kept
    event = store.history(stable.knowledge_id)[-1]
    assert event["reason_codes"][0] == "REVIEW_AFTER_EXPIRED"


def test_stale_and_reviewed_knowledge_not_used_for_decisions(tmp_path):
    store, index, lifecycle, revalidation = make_store(tmp_path)
    obj = make_fact()
    store.upsert(obj)
    walk_to_gold(lifecycle, obj.knowledge_id)

    stale_at = datetime.now(timezone.utc) + timedelta(days=200)  # long past review_after
    assert revalidation.usable_for_decisions(store.get(obj.knowledge_id), now=stale_at) is False
    assert store.usable_for_decisions(store.get(obj.knowledge_id), now=stale_at) is False

    ok_at = datetime.now(timezone.utc)  # review window still open
    assert store.usable_for_decisions(store.get(obj.knowledge_id), now=ok_at) is True

    # the same rule holds inside decision-grade retrieval
    assert index.search(title="prompt price", decision_only=True, now=ok_at)
    assert index.search(title="prompt price", decision_only=True, now=stale_at) == []


# ==============================================================================
# RetrievalIndex: FTS5 accelerator
# ==============================================================================

def test_fts_search_returns_ranked_results_by_relevance(tmp_path):
    store, index, _, _ = make_store(tmp_path)
    strong = KnowledgeObject(
        type="PLAYBOOK",
        title="kubernetes pod scheduling playbook",
        content={
            "subject": "kubernetes",
            "predicate": "scheduling",
            "object": "pod placement",
            "steps": "kubernetes scheduling uses bin packing; kubernetes scheduling honors affinity",
        },
        scope={"domain": "ops"},
    )
    weak = KnowledgeObject(
        type="FACT",
        title="team intro notes",
        content={"note": "a short note about kubernetes scheduling"},
        scope={"domain": "ops"},
    )
    store.upsert(strong)
    store.upsert(weak)

    hits = index.search(content="kubernetes scheduling")
    assert len(hits) == 2
    assert hits[0].knowledge_id == strong.knowledge_id, "more/better matches rank first"
    assert hits[0].score > hits[1].score
    # provenance travels with the hit, read back from the authority store
    assert hits[0].status == "RAW" and hits[0].type == "PLAYBOOK"
    assert hits[0].knowledge.knowledge_id == strong.knowledge_id

    # field-scoped searches
    assert [h.knowledge_id for h in index.search(title="scheduling")] == [strong.knowledge_id]
    assert [h.knowledge_id for h in index.search(subject="kubernetes")] == [strong.knowledge_id]
    assert [h.knowledge_id for h in index.search(predicate="scheduling")] == [strong.knowledge_id]

    # empty query fails closed instead of "match everything"
    with pytest.raises(Exception):
        index.search()
    # FTS syntax in the query is tokenized + quoted, never executed as grammar
    injected = index.search(content='"kubernetes" OR 1=1 --')
    assert injected == [], "AND-ed tokens: no doc contains '1'; nothing matched-all"
    assert len(index.search(content='"kubernetes" --')) == 2, "quoting survives, no crash"


def test_retrieval_index_is_accelerator_authority_survives_drop_and_rebuild(tmp_path):
    store, index, _, _ = make_store(tmp_path)
    strong = KnowledgeObject(
        type="PLAYBOOK", title="kubernetes pod scheduling playbook",
        content={"subject": "kubernetes", "predicate": "scheduling", "object": "pods",
                 "steps": "kubernetes scheduling bin packing"},
        scope={"domain": "ops"},
    )
    weak = KnowledgeObject(
        type="FACT", title="intro notes",
        content={"note": "a note about kubernetes scheduling"}, scope={"domain": "ops"},
    )
    store.upsert(strong)
    store.upsert(weak)
    before = index.search(content="kubernetes scheduling")
    assert len(before) == 2

    # destroy the accelerator entirely
    index.drop()

    # the authority store is untouched and fully readable
    assert store.count() == 2
    assert store.get(strong.knowledge_id).title == strong.title
    assert store.list_all(status="RAW")

    # search refuses to answer from a missing accelerator (no silent "empty")
    with pytest.raises(RetrievalIndexMissing):
        index.search(content="kubernetes")

    # rebuild uses ONLY the authority store as source
    assert index.rebuild() == 2
    after = index.search(content="kubernetes scheduling")
    assert [h.knowledge_id for h in after] == [h.knowledge_id for h in before]

    # ghost index rows can never fabricate knowledge: remove the authority row
    raw = sqlite3.connect(store.db_path)
    raw.execute("DELETE FROM knowledge_objects WHERE knowledge_id = ?", (weak.knowledge_id,))
    raw.commit()
    raw.close()
    hits = index.search(content="kubernetes")
    assert all(h.knowledge_id != weak.knowledge_id for h in hits), "index is never the authority"


def test_direct_status_mutation_blocked_at_storage_layer(tmp_path):
    store, _, lifecycle, _ = make_store(tmp_path)
    obj = make_fact()
    store.upsert(obj)
    ev = _support(lifecycle, obj.knowledge_id, "source-a")
    lifecycle.promote(obj.knowledge_id, evidence_refs=[ev])

    foreign = sqlite3.connect(store.db_path)
    with pytest.raises(sqlite3.Error):
        foreign.execute(
            "UPDATE knowledge_objects SET status = 'GOLD' WHERE knowledge_id = ?",
            (obj.knowledge_id,),
        )
    foreign.close()
    assert store.get(obj.knowledge_id).status is KnowledgeStatus.CURATED
    assert len(store.history(obj.knowledge_id)) == 1


def test_unknown_knowledge_id_fails_closed(tmp_path):
    store, _, _, _ = make_store(tmp_path)
    with pytest.raises(KnowledgeNotFound):
        store.get("kn_does_not_exist00000000")
    assert store.find("kn_does_not_exist00000000") is None
