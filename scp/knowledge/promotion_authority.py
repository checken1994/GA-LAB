"""Promotion authority for SCP knowledge maturity.

This module preserves the original P1-03 YAML/KnowledgeControlDB authority API
(`DecisionAction`, `PromotionDecision`, `assess`, `commit`) and extends the same
public authority with the S06 runtime derivations required by Issue #37.

For S06, caller counts, opaque ids, model confidence, and arbitrary evidence
metadata carry no maturity authority. Support is integrity-checked through the
canonical EvidenceStore, independence is derived through LineageStore, and
Reality evidence must be an immutable, scope-bound verification result.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Sequence

import yaml

from scp.contracts.time import now_utc_iso
from scp.contracts.verdicts import Verdict, parse_verdict
from scp.epistemic.evidence_store import EvidenceIntegrityError, EvidenceStore
from scp.epistemic.lineage import LineageStore
from scp.knowledge.knowledge_control_db import KnowledgeControlDB


class DecisionAction(str, Enum):
    PROMOTE = "PROMOTE"
    HOLD = "HOLD"
    UNDER_REVIEW = "UNDER_REVIEW"
    DEMOTE = "DEMOTE"
    RETIRE = "RETIRE"
    BLOCKED = "BLOCKED"


@dataclass
class PromotionDecision:
    action: DecisionAction | str
    knowledge_id: str
    from_status: str
    target_status: str
    decided_status: str
    reason_codes: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    missing_pieces: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    decision_timestamp: str = ""
    decision_id: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.action, str):
            self.action = DecisionAction(self.action.upper())
        if not self.decision_timestamp:
            self.decision_timestamp = now_utc_iso()


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
    """Single promotion authority preserving P1 API and adding S06 derivation.

    Supported construction modes are intentionally explicit:

    * ``PromotionAuthority(KnowledgeControlDB, policy_path)`` for the original
      P1-03 policy assessment/decision ledger API.
    * ``PromotionAuthority(EvidenceStore, LineageStore)`` for S06 runtime
      evidence/lineage/Reality derivation.

    A method used in the wrong mode fails closed instead of guessing.
    """

    REALITY_SCHEMA = "scp.reality_verification.v1"
    REALITY_COLLECTOR = "scp-reality-verifier"

    def __init__(
        self,
        authority_store: KnowledgeControlDB | EvidenceStore,
        policy_or_lineage: str | Path | LineageStore,
    ) -> None:
        self.db: KnowledgeControlDB | None = None
        self.policy_path: Path | None = None
        self.policy_data: dict[str, Any] | None = None
        self.evidence_store: EvidenceStore | None = None
        self.lineage_store: LineageStore | None = None

        if isinstance(authority_store, KnowledgeControlDB):
            if isinstance(policy_or_lineage, LineageStore):
                raise TypeError("KnowledgeControlDB mode requires a promotion policy path")
            self.db = authority_store
            self.policy_path = Path(policy_or_lineage)
            with open(self.policy_path, "r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle)
            if not isinstance(loaded, dict):
                raise ValueError("promotion policy must be a mapping")
            self.policy_data = loaded
            return

        if isinstance(authority_store, EvidenceStore):
            if not isinstance(policy_or_lineage, LineageStore):
                raise TypeError("EvidenceStore mode requires canonical LineageStore")
            self.evidence_store = authority_store
            self.lineage_store = policy_or_lineage
            return

        raise TypeError("unsupported promotion authority store")

    # ------------------------------------------------------------------
    # Original P1-03 policy/ledger authority API. Preserve this contract.
    # ------------------------------------------------------------------
    def _require_policy_mode(self) -> tuple[KnowledgeControlDB, dict[str, Any]]:
        if self.db is None or self.policy_data is None:
            raise PromotionAuthorityError(
                "P1 policy assessment requires KnowledgeControlDB + policy path"
            )
        return self.db, self.policy_data

    def assess(
        self,
        knowledge_id: str,
        current_status: str,
        target_status: str,
        context: Dict[str, Any],
        profile_name: str = "factual_general",
    ) -> PromotionDecision:
        _db, policy_data = self._require_policy_mode()
        transition_key = f"{current_status}_TO_{target_status}".upper()

        try:
            profile = policy_data["profiles"][profile_name]
        except (KeyError, TypeError):
            return PromotionDecision(
                action=DecisionAction.BLOCKED,
                knowledge_id=knowledge_id,
                from_status=current_status,
                target_status=target_status,
                decided_status=current_status,
                reason_codes=["BLOCKED_UNKNOWN_PROMOTION_POLICY"],
                missing_pieces=[f"profile {profile_name} not found"],
            )

        if transition_key not in profile:
            return PromotionDecision(
                action=DecisionAction.BLOCKED,
                knowledge_id=knowledge_id,
                from_status=current_status,
                target_status=target_status,
                decided_status=current_status,
                reason_codes=["INVALID_TRANSITION"],
                missing_pieces=[f"transition {transition_key} not in profile"],
            )

        rules = profile[transition_key].get("require", {})
        missing: list[str] = []
        for rule_key, expected_val in rules.items():
            actual_val = context.get(rule_key)
            if actual_val != expected_val:
                missing.append(f"{rule_key} (expected {expected_val}, got {actual_val})")

        if missing:
            return PromotionDecision(
                action=DecisionAction.HOLD,
                knowledge_id=knowledge_id,
                from_status=current_status,
                target_status=target_status,
                decided_status=current_status,
                reason_codes=["REQUIREMENTS_NOT_MET"],
                missing_pieces=missing,
            )

        return PromotionDecision(
            action=DecisionAction.PROMOTE,
            knowledge_id=knowledge_id,
            from_status=current_status,
            target_status=target_status,
            decided_status=target_status,
            reason_codes=["ALL_REQUIREMENTS_MET"],
        )

    def commit(self, decision: PromotionDecision) -> str:
        db, _policy_data = self._require_policy_mode()
        decision_id = db.record_promotion_decision(
            {
                "knowledge_id": decision.knowledge_id,
                "from_status": decision.from_status,
                "requested_status": decision.target_status,
                "decided_status": decision.decided_status,
                "decision_type": decision.action.value,
                "verdict": "APPROVED"
                if decision.action == DecisionAction.PROMOTE
                else "DENIED",
                "reason_codes": decision.reason_codes,
                "missing_piece_refs": decision.missing_pieces,
            }
        )
        decision.decision_id = decision_id
        if decision.decided_status != decision.from_status:
            db.record_status_event(
                {
                    "knowledge_id": decision.knowledge_id,
                    "from_status": decision.from_status,
                    "to_status": decision.decided_status,
                    "decision_id": decision_id,
                    "reason_codes": decision.reason_codes,
                }
            )
        return decision_id

    # ------------------------------------------------------------------
    # S06 derived authority. Caller-provided maturity assertions are ignored.
    # ------------------------------------------------------------------
    def _require_runtime_mode(self) -> tuple[EvidenceStore, LineageStore]:
        if self.evidence_store is None or self.lineage_store is None:
            raise PromotionAuthorityError(
                "S06 runtime authority requires canonical EvidenceStore + LineageStore"
            )
        return self.evidence_store, self.lineage_store

    @staticmethod
    def _refs(refs: Sequence[str]) -> list[str]:
        return list(dict.fromkeys(str(ref).strip() for ref in refs if str(ref).strip()))

    def _load(self, refs: Sequence[str]) -> list[dict]:
        evidence_store, _lineage_store = self._require_runtime_mode()
        normalized = self._refs(refs)
        if not normalized:
            raise PromotionAuthorityError("at least one canonical evidence ref is required")
        records: list[dict] = []
        for ref in normalized:
            try:
                records.append(evidence_store.get(ref))
            except (KeyError, EvidenceIntegrityError) as exc:
                raise PromotionAuthorityError(
                    f"evidence ref {ref!r} is missing or failed EvidenceStore integrity"
                ) from exc
        return records

    def require_support(self, refs: Sequence[str]) -> tuple[dict, ...]:
        """Every support occurrence must exist and pass canonical integrity."""
        return tuple(self._load(refs))

    def assess_independent_support(self, refs: Sequence[str]) -> IndependentSupport:
        _evidence_store, lineage_store = self._require_runtime_mode()
        records = self._load(refs)
        source_ids: list[str] = []
        for record in records:
            source_id = str(record.get("source_id") or "").strip()
            if not source_id:
                raise PromotionAuthorityError(
                    f"evidence {record['evidence_id']} has no source_id; independence is UNKNOWN"
                )
            source_ids.append(source_id)
        assessment = lineage_store.assess_independent_support(source_ids)
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
        evidence_store, _lineage_store = self._require_runtime_mode()
        if str(record.get("kind") or "").upper() != "TEST_RESULT":
            raise PromotionAuthorityError(
                f"evidence {record['evidence_id']} is not TEST_RESULT Reality evidence"
            )
        if str(record.get("collector_id") or "") != self.REALITY_COLLECTOR:
            raise PromotionAuthorityError(
                f"evidence {record['evidence_id']} was not produced by canonical RealityVerifier"
            )
        try:
            payload = json.loads(
                evidence_store.read_content(record["evidence_id"]).decode("utf-8")
            )
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
            raise PromotionAuthorityError(
                "Reality evidence has no independently checked postconditions"
            )
        if any(
            not isinstance(item, dict) or item.get("passed") is not True
            for item in postconditions
        ):
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
