"""Current-SCP adapter for restored V3 epistemic controls.

This module wires donor capabilities into the P1 authority model without
reinstating the V3 monolith:

- PassWhyAsker: post-PASS skeptical review;
- MetaFalsifier: verification-plan completeness;
- CounterQuestionEngine: ambiguity/reframing generator;
- SourceDiversityAuditor: concentration/capture audit backed by current LineageStore.

It never promotes knowledge or executes tools.  It can only return an audit
result and optionally materialize a durable OpenQuestion/MissingPiece through
OpenQuestionAuthority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from scp.knowledge.open_question_authority import (
    MissingPieceKind,
    MissingPieceRecord,
    OpenQuestionAuthority,
    OpenQuestionRecord,
    QuestionTrigger,
)
from scp.meta.cognitive_layers.counter_question import CounterQuestionEngine
from scp.meta.cognitive_layers.meta_falsifier import MetaFalsifier
from scp.meta.pass_why import PassWhyAsker
from scp.meta.source_diversity import SourceDiversityAuditor


@dataclass
class EpistemicAuditResult:
    review_required: bool
    reason_codes: list[str] = field(default_factory=list)
    missing_attack_vectors: list[str] = field(default_factory=list)
    counter_questions: list[dict[str, str]] = field(default_factory=list)
    pass_review: dict[str, Any] = field(default_factory=dict)
    source_diversity: dict[str, Any] = field(default_factory=dict)
    open_question_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_required": self.review_required,
            "reason_codes": list(self.reason_codes),
            "missing_attack_vectors": list(self.missing_attack_vectors),
            "counter_questions": list(self.counter_questions),
            "pass_review": dict(self.pass_review),
            "source_diversity": dict(self.source_diversity),
            "open_question_id": self.open_question_id,
        }


class EpistemicAuditAuthority:
    """Compose restored epistemic controls behind current authorities."""

    def __init__(
        self,
        *,
        open_question_authority: OpenQuestionAuthority | None = None,
        lineage_store: Any = None,
    ) -> None:
        self.open_question_authority = open_question_authority
        self.pass_why = PassWhyAsker()
        self.meta_falsifier = MetaFalsifier()
        self.counter_questions = CounterQuestionEngine()
        self.source_diversity = SourceDiversityAuditor(lineage_store=lineage_store)

    def review_candidate(
        self,
        *,
        question: str,
        domain: str,
        verdict: str,
        confidence: float,
        evidence: Any,
        sources: Optional[Iterable[str]] = None,
        source_ids: Optional[Iterable[str]] = None,
        antibody_results: Any = None,
        verification_plan: Any = None,
        materialize_question: bool = False,
        related_claim_refs: Optional[list[str]] = None,
        related_knowledge_refs: Optional[list[str]] = None,
    ) -> EpistemicAuditResult:
        reason_codes: list[str] = []
        missing_vectors: list[str] = []

        pass_review = self.pass_why.check(
            verdict=verdict,
            confidence=confidence,
            evidence=evidence,
            antibody_results=antibody_results,
            sources=sources,
        )
        reason_codes.extend(pass_review.reason_codes)

        if verification_plan is not None:
            meta = self.meta_falsifier.falsify_plan(verification_plan)
            missing_vectors = list(meta.missing_attack_vectors)
            if not meta.plan_complete:
                reason_codes.append("VERIFICATION_PLAN_INCOMPLETE")

        diversity_evidence = self._normalize_evidence(evidence)
        if not diversity_evidence and sources:
            diversity_evidence = [{"source": str(source)} for source in sources]
        diversity = self.source_diversity.audit(diversity_evidence, source_ids=source_ids)
        if diversity.recommendation == "CAPTURE_RISK":
            reason_codes.append("SOURCE_CAPTURE_RISK")
        elif diversity.recommendation == "WATCH":
            reason_codes.append("SOURCE_DIVERSITY_WATCH")
        elif diversity.recommendation == "REVIEW" and (source_ids or sources):
            reason_codes.append("SOURCE_LINEAGE_REVIEW_REQUIRED")

        should_generate_counter = (
            str(verdict or "").upper() in {"UNKNOWN", "PARTIAL", "INSUFFICIENT"}
            or pass_review.review_required
            or bool(missing_vectors)
        )
        counter_payload: list[dict[str, str]] = []
        if should_generate_counter:
            for item in self.counter_questions.generate_counter_questions(
                question,
                domain,
                enqueue_reverification=False,
            ):
                counter_payload.append(
                    {
                        "question": item.counter_question,
                        "type": item.reframing_type,
                        "why": item.why_it_matters,
                    }
                )

        result = EpistemicAuditResult(
            review_required=bool(reason_codes),
            reason_codes=self._dedupe(reason_codes),
            missing_attack_vectors=missing_vectors,
            counter_questions=counter_payload,
            pass_review=pass_review.to_dict(),
            source_diversity=diversity.to_dict(),
        )

        if materialize_question and result.review_required:
            result.open_question_id = self.materialize_open_question(
                audit=result,
                question=question,
                domain=domain,
                related_claim_refs=related_claim_refs or [],
                related_knowledge_refs=related_knowledge_refs or [],
            )
        return result

    def materialize_open_question(
        self,
        *,
        audit: EpistemicAuditResult,
        question: str,
        domain: str,
        related_claim_refs: list[str],
        related_knowledge_refs: list[str],
    ) -> str:
        if self.open_question_authority is None:
            raise RuntimeError("OpenQuestionAuthority is required to materialize audit findings")

        needed_evidence: list[str] = []
        pieces: list[MissingPieceRecord] = []

        for vector in audit.missing_attack_vectors:
            needed_evidence.append(vector)
            pieces.append(
                MissingPieceRecord(
                    question_id="",
                    description=f"Verification plan is missing attack vector: {vector}",
                    kind=MissingPieceKind.MISSING_EVIDENCE,
                    blocks_claims=list(related_claim_refs),
                    needed_evidence=[vector],
                    discovered_by="epistemic_audit_authority",
                )
            )

        for counter in audit.counter_questions:
            pieces.append(
                MissingPieceRecord(
                    question_id="",
                    description=f"Ambiguous framing: {counter['question']}",
                    kind=MissingPieceKind.AMBIGUOUS_SCOPE,
                    blocks_claims=list(related_claim_refs),
                    needed_evidence=[counter.get("why", "")],
                    discovered_by="epistemic_audit_authority",
                )
            )

        if "SOURCE_LINEAGE_REVIEW_REQUIRED" in audit.reason_codes or "SOURCE_CAPTURE_RISK" in audit.reason_codes:
            pieces.append(
                MissingPieceRecord(
                    question_id="",
                    description="Independent source lineage has not been established strongly enough for this claim.",
                    kind=MissingPieceKind.MISSING_EVIDENCE,
                    blocks_claims=list(related_claim_refs),
                    needed_evidence=["independent_source_lineage"],
                    discovered_by="source_diversity_audit",
                )
            )

        if not pieces:
            pieces.append(
                MissingPieceRecord(
                    question_id="",
                    description="Post-PASS skeptical review found unresolved epistemic concerns.",
                    kind=MissingPieceKind.MISSING_EVIDENCE,
                    blocks_claims=list(related_claim_refs),
                    needed_evidence=list(audit.reason_codes),
                    discovered_by="pass_why",
                )
            )

        record = OpenQuestionRecord(
            title=f"Epistemic review: {question[:80]}",
            question=question,
            trigger=self._trigger_for(audit),
            scope={"domain": domain},
            related_claim_refs=list(related_claim_refs),
            related_knowledge_refs=list(related_knowledge_refs),
            needed_observations=self._dedupe(needed_evidence + [item["question"] for item in audit.counter_questions]),
        )
        return self.open_question_authority.formulate_question(record, pieces)

    @staticmethod
    def _normalize_evidence(evidence: Any) -> list[dict[str, Any]]:
        if isinstance(evidence, list):
            return [item for item in evidence if isinstance(item, dict)]
        if isinstance(evidence, tuple):
            return [item for item in evidence if isinstance(item, dict)]
        if isinstance(evidence, dict):
            if not evidence:
                return []
            for key in ("items", "records", "evidence"):
                value = evidence.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [evidence]
        return []

    @staticmethod
    def _trigger_for(audit: EpistemicAuditResult) -> QuestionTrigger:
        if "SOURCE_CAPTURE_RISK" in audit.reason_codes:
            return QuestionTrigger.INSUFFICIENT_EVIDENCE
        if audit.missing_attack_vectors:
            return QuestionTrigger.INSUFFICIENT_EVIDENCE
        return QuestionTrigger.UNKNOWN

    @staticmethod
    def _dedupe(values: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                output.append(text)
        return output


__all__ = ["EpistemicAuditAuthority", "EpistemicAuditResult"]
