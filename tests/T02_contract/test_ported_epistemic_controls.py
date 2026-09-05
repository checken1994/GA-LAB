from scp.epistemic.lineage import IndependenceStatus, LineageStore
from scp.meta.pass_why import PassWhyAsker
from scp.meta.source_diversity import SourceDiversityAuditor


def test_pass_why_flags_pass_without_evidence():
    result = PassWhyAsker().check(
        verdict="PASS",
        confidence=0.82,
        evidence=[],
        antibody_results=[],
        sources=[],
    )
    assert result.review_required is True
    assert "PASS_WITHOUT_EVIDENCE" in result.reason_codes


def test_pass_why_does_not_upgrade_or_rewrite_non_pass_verdict():
    result = PassWhyAsker().check(
        verdict="UNKNOWN",
        confidence=0.99,
        evidence=[],
        antibody_results=[],
        sources=[],
    )
    assert result.review_required is False
    assert result.reason_codes == []


def test_pass_why_detects_ignored_antibody_failure_without_self_assigning_truth():
    result = PassWhyAsker().check(
        verdict="VERIFIED",
        confidence=0.8,
        evidence=[{"stance": "SUPPORT", "evidence_id": "ev_1"}, {"stance": "SUPPORT", "evidence_id": "ev_2"}],
        antibody_results=[{"passed": False, "antibody": "selection_bias"}],
        sources=["https://a.example/x", "https://b.example/y"],
    )
    assert result.review_required is True
    assert "IGNORED_ANTIBODY_FAILURE" in result.reason_codes


def test_source_diversity_uses_lineage_authority_not_domain_guess(tmp_path):
    lineage = LineageStore(tmp_path / "lineage.sqlite")
    lineage.record_relation(
        "src_a",
        "src_b",
        status=IndependenceStatus.SAME_LINEAGE,
        basis=[{"type": "explicit_shared_upstream"}],
    )
    lineage.record_relation(
        "src_a",
        "src_c",
        status=IndependenceStatus.INDEPENDENT,
        basis=[{"type": "explicit_distinct_origin"}],
    )
    lineage.record_relation(
        "src_b",
        "src_c",
        status=IndependenceStatus.INDEPENDENT,
        basis=[{"type": "explicit_distinct_origin"}],
    )

    result = SourceDiversityAuditor(lineage).audit(
        evidence=[
            {"source_id": "src_a", "source": "https://mirror-one.example/item"},
            {"source_id": "src_b", "source": "https://mirror-two.example/item"},
            {"source_id": "src_c", "source": "https://independent.example/item"},
        ]
    )

    # Three distinct domains are NOT silently counted as three lineages.
    assert result.unique_domains == 3
    assert result.lineage_assessed is True
    assert result.known_independent_lineages == 2
    assert result.shared_lineage_pairs == 1


def test_source_diversity_without_lineage_stays_review_not_ok():
    result = SourceDiversityAuditor().audit(
        evidence=[
            {"source": "https://a.example/1"},
            {"source": "https://b.example/2"},
            {"source": "https://c.example/3"},
        ]
    )
    assert result.lineage_assessed is False
    assert result.recommendation == "REVIEW"
    assert "LINEAGE_NOT_ASSESSED" in result.findings


def test_cognitive_engine_wires_pass_why_and_source_diversity(monkeypatch):
    monkeypatch.setenv("SCP_COGNITIVE_LAYERS", "pass_why,source_diversity")
    from scp.meta.cognitive_engine import CognitiveEngine

    result = CognitiveEngine().analyze(
        question="Is claim X verified?",
        domain="general",
        verdict="PASS",
        confidence=0.9,
        sources_succeeded=["https://a.example/x"],
        sources_failed=[],
        why_plan=None,
        reality_check={},
        evidence={},
    )

    assert result["pass_review"]["review_required"] is True
    assert "PASS_WITHOUT_EVIDENCE" in result["pass_review"]["reason_codes"]
    assert result["source_diversity"]["recommendation"] == "REVIEW"


def test_cognitive_gate_pass_why_blocks_pass_without_evidence(tmp_path, monkeypatch):
    # Prevent the legacy audit log from touching the shared project DB during
    # this contract test; gate behavior itself is what is under test.
    monkeypatch.setattr("scp.meta.cognitive_gate._DB_AVAILABLE", False)
    from scp.meta.cognitive_gate import CognitiveGate

    gated, reasons, original = CognitiveGate().evaluate(
        verdict="PASS",
        confidence=0.9,
        cognitive_result={
            "pass_review": {
                "review_required": True,
                "reason_codes": ["PASS_WITHOUT_EVIDENCE"],
            }
        },
        evidence_type="entity_fact",
        sources_succeeded=[],
        question="claim x",
        domain="general",
    )
    assert original == "PASS"
    assert gated == "UNKNOWN"
    assert any("PassWhy" in reason for reason in reasons)


def test_cognitive_gate_does_not_use_unassessed_domain_diversity_as_lineage(monkeypatch):
    monkeypatch.setattr("scp.meta.cognitive_gate._DB_AVAILABLE", False)
    from scp.meta.cognitive_gate import CognitiveGate

    gated, reasons, _ = CognitiveGate().evaluate(
        verdict="PASS",
        confidence=0.8,
        cognitive_result={
            "source_diversity": {
                "lineage_assessed": False,
                "recommendation": "REVIEW",
                "unique_domains": 4,
            }
        },
        evidence_type="deterministic_evaluation",
        sources_succeeded=["a", "b", "c", "d"],
        question="deterministic claim",
        domain="logic",
    )
    assert gated == "PASS"
    assert reasons == []


def test_epistemic_audit_materializes_missing_piece_into_current_open_question_authority(tmp_path):
    from types import SimpleNamespace
    import sqlite3

    from scp.knowledge.epistemic_audit_authority import EpistemicAuditAuthority
    from scp.knowledge.learning_db import LearningDB
    from scp.knowledge.open_question_authority import OpenQuestionAuthority

    db = LearningDB(tmp_path / "learning.sqlite")
    audit = EpistemicAuditAuthority(open_question_authority=OpenQuestionAuthority(db))
    plan = SimpleNamespace(
        expected_answer_type="numeric",
        evidence_type="real_time_market_data",
        proof_criteria="one source returned a number",
        falsification_criteria="",
    )

    result = audit.review_candidate(
        question="What is the current value?",
        domain="finance",
        verdict="PASS",
        confidence=0.9,
        evidence=[{"stance": "SUPPORT", "source": "https://one.example/value"}],
        sources=["https://one.example/value"],
        verification_plan=plan,
        materialize_question=True,
        related_claim_refs=["claim_1"],
    )

    assert result.review_required is True
    assert result.open_question_id is not None
    assert "VERIFICATION_PLAN_INCOMPLETE" in result.reason_codes

    with sqlite3.connect(db.db_path) as conn:
        q = conn.execute(
            "SELECT trigger, status FROM open_questions WHERE question_id=?",
            (result.open_question_id,),
        ).fetchone()
        pieces = conn.execute(
            "SELECT COUNT(*) FROM missing_pieces WHERE question_id=?",
            (result.open_question_id,),
        ).fetchone()[0]
    assert q == ("INSUFFICIENT_EVIDENCE", "OPEN")
    assert pieces >= 1


def test_epistemic_audit_counter_questions_do_not_use_legacy_reverification_queue(monkeypatch):
    from scp.knowledge.epistemic_audit_authority import EpistemicAuditAuthority

    authority = EpistemicAuditAuthority()
    called = {"legacy_queue": False}

    def _forbidden(*args, **kwargs):
        called["legacy_queue"] = True
        raise AssertionError("legacy pending_reverification queue must not be used by P1 audit bridge")

    monkeypatch.setattr(authority.counter_questions, "_enqueue_for_reverification", _forbidden)
    result = authority.review_candidate(
        question="What dosage applies?",
        domain="medical",
        verdict="UNKNOWN",
        confidence=0.2,
        evidence=[],
        sources=[],
    )

    assert called["legacy_queue"] is False
    assert result.counter_questions


def test_cognitive_orchestrator_exposes_current_p1_epistemic_audit_bridge(tmp_path):
    from scp.knowledge.benchmark_authority import BenchmarkAuthority
    from scp.knowledge.cognitive_orchestrator import CognitiveOrchestrator
    from scp.knowledge.contradiction_authority import ContradictionAuthority
    from scp.knowledge.experiment_authority import ExperimentAuthority
    from scp.knowledge.hypothesis_authority import HypothesisAuthority
    from scp.knowledge.knowledge_control_db import KnowledgeControlDB
    from scp.knowledge.learning_db import LearningDB
    from scp.knowledge.lesson_authority import LessonAuthority
    from scp.knowledge.open_question_authority import OpenQuestionAuthority
    from scp.knowledge.revalidation_authority import RevalidationAuthority

    k_db = KnowledgeControlDB(tmp_path / "k.sqlite")
    l_db = LearningDB(tmp_path / "l.sqlite")
    orchestrator = CognitiveOrchestrator(
        k_db,
        l_db,
        RevalidationAuthority(k_db),
        ContradictionAuthority(k_db),
        OpenQuestionAuthority(l_db),
        HypothesisAuthority(l_db),
        ExperimentAuthority(l_db),
        LessonAuthority(l_db),
        BenchmarkAuthority(l_db),
    )

    result = orchestrator.review_candidate(
        question="Is this supported?",
        domain="general",
        verdict="PASS",
        confidence=0.85,
        evidence=[],
        sources=[],
        materialize_question=True,
    )
    assert result.review_required is True
    assert result.open_question_id is not None
