"""Derived promotion authority for the S06 Knowledge Runtime.

M8 must never treat caller counts, opaque ids, model confidence, or an
arbitrary EvidenceStore row as truth authority.  This adapter derives:
* evidence existence/integrity from canonical EvidenceStore,
* independent support from canonical LineageStore,
* Reality verification from strict, immutable RealityVerifier result
  payloads bound to this exact knowledge id, scope, and input evidence.

A Reality result is recognized only when it is a TEST_RESULT collected
by the canonical ``scp-reality-verifier`` collector and its immutable
payload satisfies ``scp.reality_verification.v1``.  MODEL_RESPONSE and
caller metadata are never accepted as verification authority.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

from scp.contracts.verdicts import Verdict, parse_verdict
from scp.epistemic.evidence_store import EvidenceIntegrityError, EvidenceStore
from scp.epistemic.lineage import LineageStore


class PromotionAuthorityError(RuntimeError):
    """Canonical promotion evidence is missing or invalid (fail closed)."""


@dataclass(frozen=True)
class IndependentSupport:
    evidence_refs: tuple[str, ...]
    source_ids: tuple[str, ...]
    known_independent_lineages: int
    unknown_pairs: int
    shared_lineage_pairs: int


@dataclass(frozen=True)
class RealityAssessment:
    evidence_id: str
    episode_id: str
    adversarial_check_passed: bool
    counterexample_check_passed: bool
    temporal_stability: bool


@dataclass(frozen=True)
class GoldAssessment:
    episode_ids: tuple[str, ...]
    repeated_verification: bool
    adversarial_check_passed: bool
    counterexample_check_passed: bool
    temporal_stability: bool


class PromotionAuthority:
    """Read-only derivation layer over canonical epistemic authorities."""

    REALITY_SCHEMA = "scp.reality_verification.v1"
    REALITY_COLLECTOR = "scp-reality-verifier"

    def __init__(self, evidence_store: EvidenceStore, lineage_store: LineageStore) -> None:
        self.evidence_store = evidence_store
        self.lineage_store = lineage_store

    @staticmethod
    def _refs(refs: Sequence[str]) -> list[str]:
        return list(dict.fromkeys(str(ref).strip() for ref in refs if str(ref).strip()))

    def _load(self, refs: Sequence[str]) -> list[dict]:
        normalized = self._refs(refs)
        if not normalized:
            raise PromotionAuthorityError("at least one canonical evidence ref is required")
        records: list[dict] = []
        for ref in normalized:
            try:
                records.append(self.evidence_store.get(ref))
            except (KeyError, EvidenceIntegrityError) as exc:
                raise PromotionAuthorityError(
                    f"evidence ref {ref!r} is missing or failed EvidenceStore integrity"
                ) from exc
        return records

    def require_support(self, refs: Sequence[str]) -> tuple[dict, ...]:
        """Every support occurrence must exist and pass canonical integrity."""
        return tuple(self._load(refs))

    def assess_independent_support(self, refs: Sequence[str]) -> IndependentSupport:
        records = self._load(refs)
        source_ids: list[str] = []
        for record in records:
            source_id = str(record.get("source_id") or "").strip()
            if not source_id:
                raise PromotionAuthorityError(
                    f"evidence {record['evidence_id']} has no source_id; independence is UNKNOWN"
                )
            source_ids.append(source_id)
        assessment = self.lineage_store.assess_independent_support(source_ids)
        return IndependentSupport(
            evidence_refs=tuple(record["evidence_id"] for record in records),
            source_ids=tuple(sorted(set(source_ids))),
            known_independent_lineages=int(assessment["known_independent_lineages"]),
            unknown_pairs=int(assessment["unknown_pairs"]),
            shared_lineage_pairs=int(assessment["shared_lineage_pairs"]),
        )

    def _parse_reality(
        self,
        record: dict,
        *,
        knowledge_id: str,
        scope: dict,
        support_refs: Sequence[str],
    ) -> RealityAssessment:
        if str(record.get("kind") or "").upper() != "TEST_RESULT":
            raise PromotionAuthorityError(
                f"evidence {record['evidence_id']} is not TEST_RESULT Reality evidence"
            )
        if str(record.get("collector_id") or "") != self.REALITY_COLLECTOR:
            raise PromotionAuthorityError(
                f"evidence {record['evidence_id']} was not produced by canonical RealityVerifier"
            )
        try:
            payload = json.loads(self.evidence_store.read_content(record["evidence_id"]).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise PromotionAuthorityError("Reality evidence payload is not canonical JSON") from exc
        if not isinstance(payload, dict) or payload.get("schema") != self.REALITY_SCHEMA:
            raise PromotionAuthorityError("Reality evidence schema is not recognized")
        if str(payload.get("knowledge_id") or "") != str(knowledge_id):
            raise PromotionAuthorityError("Reality evidence is bound to a different knowledge_id")
        if payload.get("knowledge_scope") != scope:
            raise PromotionAuthorityError("Reality evidence scope does not match knowledge scope")
        try:
            verdict = parse_verdict(payload.get("verdict"))
        except ValueError as exc:
            raise PromotionAuthorityError("Reality evidence verdict is invalid") from exc
        if verdict is not Verdict.VERIFIED:
            raise PromotionAuthorityError(f"Reality verdict is {verdict.value}, not VERIFIED")
        if payload.get("temporal_validity") is not True:
            raise PromotionAuthorityError("Reality evidence did not establish temporal_validity")
        postconditions = payload.get("postconditions")
        if not isinstance(postconditions, list) or not postconditions:
            raise PromotionAuthorityError("Reality evidence has no independently checked postconditions")
        if any(not isinstance(item, dict) or item.get("passed") is not True for item in postconditions):
            raise PromotionAuthorityError("Reality evidence contains an unpassed postcondition")

        inputs = self._refs(payload.get("input_evidence_refs") or [])
        allowed = set(self._refs(support_refs))
        if not inputs or not set(inputs).issubset(allowed):
            raise PromotionAuthorityError(
                "Reality evidence is not bound to the canonical support evidence for this knowledge"
            )
        self.require_support(inputs)

        episode_id = str(payload.get("episode_id") or record.get("attempt_id") or "").strip()
        if not episode_id:
            raise PromotionAuthorityError("Reality evidence lacks a durable episode_id")
        return RealityAssessment(
            evidence_id=str(record["evidence_id"]),
            episode_id=episode_id,
            adversarial_check_passed=payload.get("adversarial_check") is True,
            counterexample_check_passed=payload.get("counterexample_check") is True,
            temporal_stability=payload.get("temporal_stability") is True,
        )

    def require_verification(
        self,
        refs: Sequence[str],
        *,
        knowledge_id: str,
        scope: dict,
        support_refs: Sequence[str],
    ) -> tuple[RealityAssessment, ...]:
        records = self._load(refs)
        return tuple(
            self._parse_reality(
                record,
                knowledge_id=knowledge_id,
                scope=scope,
                support_refs=support_refs,
            )
            for record in records
        )

    def assess_gold(
        self,
        refs: Sequence[str],
        *,
        knowledge_id: str,
        scope: dict,
        support_refs: Sequence[str],
        min_episodes: int,
    ) -> GoldAssessment:
        assessments = self.require_verification(
            refs,
            knowledge_id=knowledge_id,
            scope=scope,
            support_refs=support_refs,
        )
        episodes = tuple(sorted({item.episode_id for item in assessments}))
        return GoldAssessment(
            episode_ids=episodes,
            repeated_verification=len(episodes) >= int(min_episodes),
            adversarial_check_passed=bool(assessments)
            and all(item.adversarial_check_passed for item in assessments),
            counterexample_check_passed=bool(assessments)
            and all(item.counterexample_check_passed for item in assessments),
            temporal_stability=bool(assessments)
            and all(item.temporal_stability for item in assessments),
        )
