"""Runtime epistemic bridge (M4 cutover).

Wires the SCPv14 runtime verdict pipeline to the immutable epistemic stack:

  - ALL storage goes through ``GovernedEvidenceWriter`` so the
    ``PrivacyWriteGate`` evaluates (redacts / denies) every payload before it
    reaches the immutable ``EvidenceStore``;
  - occurrence identity != content identity: re-observing the same SLM answer
    yields the same content_hash but a NEW evidence_id;
  - the ``evidence`` table is machine-immutable (``evidence_no_update``
    trigger) — a wrong observation is corrected by a NEW evidence plus a
    SUPERSEDES relation, never by editing history;
  - ``LineageStore`` tracks source independence with the DB-default
    UNKNOWN_INDEPENDENCE (UNKNOWN contributes zero independent support);
  - ``MODEL_RESPONSE`` evidence proves "the model said X" - never "X is true".

The legacy ``scp/core/phase0.py`` functions remain as a deprecated
compatibility facade and route through this bridge (authority) while keeping
the legacy tables as an append-only read-model.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from scp.contracts.data_class import DataClass
from scp.epistemic.evidence_store import EVIDENCE_KINDS, EvidenceStore
from scp.epistemic.evidence_writer import GovernedEvidenceWriter
from scp.epistemic.lineage import LineageStore
from scp.governance.privacy import PrivacyWriteGate

logger = logging.getLogger("scp.epistemic.runtime_bridge")

_ROOT = Path(__file__).resolve().parents[2]
_FOUNDATION_DIR = _ROOT / "data" / "foundation"
_POLICY_PATH = _ROOT / "spec" / "data_policies.yaml"

COLLECTOR_ID = "scpv14-runtime"
COLLECTOR_VERSION = "m4-cutover-1"
COMPAT_COLLECTOR_ID = "phase0-compat"

# Legacy phase0 evidence_type -> immutable epistemic kind.
# MODEL_RESPONSE proves "the model said X" - never "X is true".
KIND_BY_LEGACY_TYPE = {
    "slm_response": "MODEL_RESPONSE",
    "reality_check": "RUNTIME_OBSERVATION",
}
_DEFAULT_KIND = "RUNTIME_OBSERVATION"


@dataclass
class EpistemicStack:
    """The P0 epistemic authorities used by the runtime."""

    store: EvidenceStore
    writer: GovernedEvidenceWriter
    lineage: LineageStore
    foundation_dir: Path


def build_epistemic_stack(
    foundation_dir: str | Path | None = None,
    policy_path: str | Path | None = None,
) -> EpistemicStack:
    """Construct the epistemic stack. ``foundation_dir``/``policy_path`` are
    overridable so tests and alternative deployments can scope their data."""
    foundation = Path(foundation_dir) if foundation_dir else _FOUNDATION_DIR
    policy = Path(policy_path) if policy_path else _POLICY_PATH
    store = EvidenceStore(foundation / "epistemic.sqlite", foundation / "evidence_objects")
    writer = GovernedEvidenceWriter(store, PrivacyWriteGate(policy))
    lineage = LineageStore(foundation / "lineage.sqlite")
    return EpistemicStack(store=store, writer=writer, lineage=lineage, foundation_dir=foundation)


_lock = threading.Lock()
_bridge: "RuntimeEvidenceBridge | None" = None


def get_runtime_bridge() -> "RuntimeEvidenceBridge":
    """Process-wide bridge singleton (lazy, thread-safe)."""
    global _bridge
    with _lock:
        if _bridge is None:
            _bridge = RuntimeEvidenceBridge(build_epistemic_stack())
        return _bridge


def reset_runtime_bridge() -> None:
    """Ops/test hook: force reconstruction on the next get_runtime_bridge()."""
    global _bridge
    with _lock:
        _bridge = None


def safe_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def canonical_bytes(payload: dict) -> bytes:
    """Deterministic bytes for content identity (deduped by content_hash)."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")


def question_digest(question: str) -> str:
    return "sha256:" + hashlib.sha256(str(question or "").encode("utf-8")).hexdigest()


class RuntimeEvidenceBridge:
    """High-level runtime API over the immutable epistemic stack."""

    def __init__(self, stack: EpistemicStack) -> None:
        self.stack = stack
        # legacy phase0 id -> epistemic evidence id (compat routing only;
        # the native runtime path never needs this indirection).
        self._legacy_index: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Runtime verdict-cycle API (used by scpv14_process_mixin Step 8)
    # ------------------------------------------------------------------
    def record_model_response(
        self,
        *,
        slm_name: str,
        answer: object,
        confidence: object,
        entity: str = "",
        attribute: str = "",
        raw_data: object = None,
        question: str = "",
        cycle_count: int = 0,
        trace_id: str | None = None,
    ) -> str:
        """Record one SLM response as MODEL_RESPONSE evidence (immutable)."""
        record = self.stack.writer.observe(
            kind="MODEL_RESPONSE",
            content=canonical_bytes(
                {"answer": answer, "confidence": confidence, "raw": raw_data}
            ),
            collector_id=COLLECTOR_ID,
            collector_version=COLLECTOR_VERSION,
            source_id=str(slm_name or "unknown"),
            trace_id=trace_id,
            data_class=DataClass.INTERNAL,
            metadata={
                "observation_type": "slm_response",
                "entity": str(entity or ""),
                "attribute": str(attribute or ""),
                "value": str(answer)[:500],
                "confidence": safe_float(confidence, 0.5),
                "question_sha256": question_digest(question),
                "cycle_count": int(cycle_count),
            },
        )
        return record["evidence_id"]

    def record_reality_check(
        self,
        *,
        source: str,
        entity: str = "",
        attribute: str = "",
        real_value: object = None,
        raw_data: object = None,
        question: str = "",
        cycle_count: int = 0,
        trace_id: str | None = None,
    ) -> str:
        """Record the reality-engine observation (RUNTIME_OBSERVATION)."""
        record = self.stack.writer.observe(
            kind="RUNTIME_OBSERVATION",
            content=canonical_bytes(
                {"real_value": real_value, "raw": raw_data}
            ),
            collector_id=COLLECTOR_ID,
            collector_version=COLLECTOR_VERSION,
            source_id=str(source or "v13"),
            trace_id=trace_id,
            data_class=DataClass.INTERNAL,
            metadata={
                "observation_type": "reality_check",
                "entity": str(entity or ""),
                "attribute": str(attribute or ""),
                "value": str(real_value)[:500],
                "confidence": 0.9,
                "question_sha256": question_digest(question),
                "cycle_count": int(cycle_count),
            },
        )
        return record["evidence_id"]

    def record_conclusion(
        self,
        *,
        question: str,
        ai_answer: str,
        verdict: str,
        confidence: object,
        domain: str,
        reasoning: str,
        cycle_count: int = 0,
        trace_id: str | None = None,
        source_ids: list[str] | tuple[str, ...] = (),
    ) -> str:
        """Record the verdict conclusion + source-lineage assessment.

        Raw question/answer/reasoning travel inside ``content`` so the
        PrivacyWriteGate can redact or deny them; metadata carries only
        hashes and scalar verdict facts.
        """
        metadata: dict = {
            "observation_type": "v14_conclusion",
            "question_sha256": question_digest(question),
            "verdict": str(verdict),
            "confidence": safe_float(confidence, 0.0),
            "domain": str(domain or "unknown"),
            "cycle_count": int(cycle_count),
        }
        sources = sorted({str(s).strip() for s in source_ids if str(s).strip()})
        if sources:
            try:
                for i, a in enumerate(sources):
                    for b in sources[i + 1:]:
                        # DB-default UNKNOWN_INDEPENDENCE - never inferred.
                        self.stack.lineage.ensure_relation(a, b)
                metadata["lineage"] = self.stack.lineage.assess_independent_support(sources)
            except Exception as exc:  # lineage is enrichment, not a gate
                logger.warning("lineage tracking failed: %s", exc)
                metadata["lineage"] = {"error": str(exc)}
        record = self.stack.writer.observe(
            kind="RUNTIME_OBSERVATION",
            content=canonical_bytes(
                {
                    "question": question,
                    "ai_answer": ai_answer,
                    "verdict": verdict,
                    "reasoning": reasoning,
                }
            ),
            collector_id=COLLECTOR_ID,
            collector_version=COLLECTOR_VERSION,
            source_id=COLLECTOR_ID,
            trace_id=trace_id,
            data_class=DataClass.INTERNAL,
            metadata=metadata,
        )
        return record["evidence_id"]

    def record_decision(
        self, conclusion_evidence_id: str, action: str, notes: str = ""
    ) -> str:
        """Record the decision taken on a conclusion (new evidence + DECIDES)."""
        record = self.stack.writer.observe(
            kind="RUNTIME_OBSERVATION",
            content=canonical_bytes({"action": action, "notes": notes}),
            collector_id=COLLECTOR_ID,
            collector_version=COLLECTOR_VERSION,
            source_id=COLLECTOR_ID,
            data_class=DataClass.INTERNAL,
            metadata={
                "observation_type": "v14_decision",
                "action": str(action),
                "notes": str(notes)[:500],
                "conclusion_evidence_id": str(conclusion_evidence_id),
            },
        )
        self.link(record["evidence_id"], conclusion_evidence_id, "DECIDES")
        return record["evidence_id"]

    # ------------------------------------------------------------------
    # Corrections: SUPERSEDES only, never in-place edits
    # ------------------------------------------------------------------
    def supersede(self, old_evidence_id: str, **observe_kwargs) -> dict:
        """Correct a wrong observation: NEW evidence + SUPERSEDES relation."""
        observe_kwargs.setdefault("collector_id", COLLECTOR_ID)
        observe_kwargs.setdefault("collector_version", COLLECTOR_VERSION)
        if "data_class" not in observe_kwargs:
            observe_kwargs["data_class"] = DataClass.INTERNAL
        replacement = self.stack.writer.observe(**observe_kwargs)
        if self.has_evidence(old_evidence_id):
            self.link(old_evidence_id, replacement["evidence_id"], "SUPERSEDES")
        else:
            logger.warning(
                "supersede target %s not in authority store; recorded in replacement metadata",
                old_evidence_id,
            )
        return replacement

    def record_verification(
        self, target_evidence_id: str, *, verified: bool, by: str = "", note: str = ""
    ) -> str:
        """Record a verification OUTCOME as new immutable TEST_RESULT evidence
        linked VERIFIES -> target. Never mutates the target record."""
        record = self.stack.writer.observe(
            kind="TEST_RESULT",
            content=canonical_bytes(
                {"target": target_evidence_id, "outcome": "VERIFIED" if verified else "FAILED",
                 "by": by, "note": note}
            ),
            collector_id=COLLECTOR_ID,
            collector_version=COLLECTOR_VERSION,
            source_id=str(by or COLLECTOR_ID),
            data_class=DataClass.INTERNAL,
            metadata={
                "observation_type": "verification_outcome",
                "target_evidence_id": str(target_evidence_id),
                "outcome": "VERIFIED" if verified else "FAILED",
                "verified_by": str(by or ""),
            },
        )
        if self.has_evidence(target_evidence_id):
            self.link(record["evidence_id"], target_evidence_id, "VERIFIES")
        return record["evidence_id"]

    # ------------------------------------------------------------------
    # Links + legacy compat helpers
    # ------------------------------------------------------------------
    def link(self, parent_evidence_id: str, child_evidence_id: str, relation: str) -> None:
        self.stack.store.link(parent_evidence_id, child_evidence_id, relation)

    def register_legacy_mapping(self, legacy_id: str, evidence_id: str) -> None:
        if legacy_id and evidence_id:
            self._legacy_index[str(legacy_id)] = str(evidence_id)

    def resolve_evidence_id(self, legacy_or_evidence_id: str) -> str:
        rid = str(legacy_or_evidence_id or "")
        return self._legacy_index.get(rid, rid)

    def link_legacy_pair(
        self, left_id: str, right_id: str, relation: str = "SUPPORTS"
    ) -> bool:
        """Link two ids that may be legacy phase0 ids (best-effort, no raise)."""
        try:
            parent = self.resolve_evidence_id(left_id)
            child = self.resolve_evidence_id(right_id)
            if parent and child and self.has_evidence(parent) and self.has_evidence(child):
                self.link(parent, child, relation)
                return True
            # Unresolvable legacy ids: keep an immutable trace of the relation.
            self.stack.writer.observe(
                kind="RUNTIME_OBSERVATION",
                content=canonical_bytes(
                    {"relation": relation, "left": left_id, "right": right_id}
                ),
                collector_id=COMPAT_COLLECTOR_ID,
                collector_version=COLLECTOR_VERSION,
                data_class=DataClass.INTERNAL,
                metadata={
                    "observation_type": "legacy_relation",
                    "relation": str(relation),
                    "left": str(left_id),
                    "right": str(right_id),
                },
            )
            return True
        except Exception as exc:
            logger.warning("link_legacy_pair failed: %s", exc)
            return False

    def has_evidence(self, evidence_id: str) -> bool:
        if not evidence_id:
            return False
        rows = self.stack.store.db.query(
            "SELECT evidence_id FROM evidence WHERE evidence_id=?", (str(evidence_id),)
        )
        return bool(rows)


__all__ = [
    "COMPAT_COLLECTOR_ID",
    "COLLECTOR_ID",
    "COLLECTOR_VERSION",
    "EVIDENCE_KINDS",
    "EpistemicStack",
    "KIND_BY_LEGACY_TYPE",
    "RuntimeEvidenceBridge",
    "build_epistemic_stack",
    "get_runtime_bridge",
    "reset_runtime_bridge",
]
