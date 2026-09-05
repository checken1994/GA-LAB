"""
SCP V3 Pass-Why port, adapted to the current SCP authority model.

Donor lineage:
  scp-v3-world-standard.zip::scp-backend/services/meta_cognition/pass_why.py

The V3 capability asks a second question after a candidate PASS:
"Why did this pass?"  It is a falsification/review control, not a truth
engine.  In the current SCP it may request review and emit reasons, but it
must never self-upgrade an epistemic verdict.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class PassWhyResult:
    """Result of a post-PASS skeptical review.

    ``confidence_penalty`` is retained for backward compatibility with the V3
    donor.  It is advisory only; current SCP truth/promotion authority must not
    derive VERIFIED from this number or from model confidence.
    """

    suspicious: bool = False
    review_required: bool = False
    confidence_penalty: float = 0.0
    reasons: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    checks_run: int = 0
    checks_failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "suspicious": self.suspicious,
            "review_required": self.review_required,
            "confidence_penalty": round(self.confidence_penalty, 4),
            "reasons": list(self.reasons),
            "reason_codes": list(self.reason_codes),
            "checks_run": self.checks_run,
            "checks_failed": self.checks_failed,
        }


class PassWhyAsker:
    """Ask ``Why PASS?`` before a PASS is treated as trustworthy.

    The donor logic is preserved, with two authority corrections:
    - both legacy ``PASS`` and canonical ``VERIFIED`` candidates can be audited;
    - failures request review; they never directly manufacture FAIL/VERIFIED.
    """

    _PASS_LIKE = {"PASS", "VERIFIED"}

    @staticmethod
    def _normalize_evidence(evidence: Any) -> list[dict[str, Any]]:
        if evidence is None:
            return []
        if isinstance(evidence, dict):
            if not evidence:
                return []
            # A caller may pass a single evidence item or a wrapper containing a
            # list.  Preserve only dict-shaped evidence records.
            for key in ("items", "evidence", "records"):
                value = evidence.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [evidence]
        if isinstance(evidence, (list, tuple)):
            return [item for item in evidence if isinstance(item, dict)]
        return []

    @staticmethod
    def _normalize_antibodies(results: Any) -> list[dict[str, Any]]:
        if results is None:
            return []
        if isinstance(results, dict):
            results = results.get("results", results.get("antibodies", []))
        if not isinstance(results, (list, tuple)):
            return []
        normalized: list[dict[str, Any]] = []
        for item in results:
            if isinstance(item, dict):
                normalized.append(item)
            elif hasattr(item, "to_dict"):
                try:
                    value = item.to_dict()
                    if isinstance(value, dict):
                        normalized.append(value)
                except Exception:
                    continue
        return normalized

    @staticmethod
    def _source_domain(source: str) -> str:
        value = str(source or "").strip().lower()
        if not value:
            return ""
        try:
            if "://" in value:
                return (urlparse(value).hostname or "").lower()
        except Exception:
            return ""
        return value.split("/", 1)[0]

    def check(
        self,
        verdict: str,
        confidence: float,
        evidence: Any,
        antibody_results: Any = None,
        sources: Optional[Iterable[str]] = None,
    ) -> PassWhyResult:
        result = PassWhyResult()
        normalized_verdict = str(verdict or "").upper().strip()
        if normalized_verdict not in self._PASS_LIKE:
            return result

        try:
            evidence_items = self._normalize_evidence(evidence)
            antibody_items = self._normalize_antibodies(antibody_results)
            source_items = [str(src) for src in (sources or []) if str(src).strip()]
            result.checks_run = 5

            # V3 check 1: positive evidence must exist; absence-of-refutation is
            # not positive support.
            if not evidence_items:
                self._fail(
                    result,
                    "PASS_WITHOUT_EVIDENCE",
                    "PASS/VERIFIED candidate has no evidence; absence of detected error is not proof.",
                    0.10,
                )
            else:
                stance_values = {
                    str(item.get("stance", "")).upper().strip()
                    for item in evidence_items
                    if item.get("stance") is not None
                }
                # Only enforce SUPPORT semantics when the caller actually supplies
                # stance labels.  Current EvidenceStore occurrence records are not
                # required to use the V3 SUPPORT/REFUTE vocabulary.
                if stance_values and "SUPPORT" not in stance_values:
                    self._fail(
                        result,
                        "NO_SUPPORTING_EVIDENCE",
                        f"Candidate has {len(evidence_items)} evidence record(s) but none is labelled SUPPORT.",
                        0.08,
                    )

            # V3 check 2: overconfidence is a calibration smell, not truth proof.
            if confidence > 0.95:
                self._fail(
                    result,
                    "OVERCONFIDENCE_REVIEW",
                    f"Model confidence {confidence:.2f} exceeds 0.95; calibration review required.",
                    0.05,
                )

            # V3 check 3: ignored antibody failure.
            failed_antibodies = sum(1 for item in antibody_items if item.get("passed") is False)
            if failed_antibodies:
                self._fail(
                    result,
                    "IGNORED_ANTIBODY_FAILURE",
                    f"Candidate PASS coexists with {failed_antibodies} antibody failure(s).",
                    0.10,
                )

            # V3 check 4: same-domain concentration is a capture signal only.  It
            # MUST NOT be interpreted as authoritative lineage identity; current
            # LineageStore owns that question.
            domains = {self._source_domain(src) for src in source_items}
            domains.discard("")
            if len(source_items) > 2 and len(domains) == 1:
                self._fail(
                    result,
                    "SINGLE_DOMAIN_CONCENTRATION",
                    f"All {len(source_items)} observed sources concentrate in one domain; check LineageStore before counting independent support.",
                    0.05,
                )

            # V3 check 5: thin evidence + high confidence.
            if len(evidence_items) < 2 and confidence > 0.70:
                self._fail(
                    result,
                    "THIN_EVIDENCE_HIGH_CONFIDENCE",
                    f"Confidence {confidence:.2f} is high with only {len(evidence_items)} evidence record(s).",
                    0.07,
                )

            result.review_required = result.suspicious
            if result.suspicious:
                logger.info(
                    "[pass_why] candidate requires review: failed=%s codes=%s",
                    result.checks_failed,
                    result.reason_codes,
                )
            return result
        except Exception as exc:
            # The old donor comment said fail-closed but returned a mere confidence
            # penalty.  Current SCP makes the fail-closed state explicit.
            logger.exception("[pass_why] audit failed")
            result.suspicious = True
            result.review_required = True
            result.checks_failed += 1
            result.confidence_penalty = max(result.confidence_penalty, 0.05)
            result.reason_codes.append("PASS_WHY_AUDIT_ERROR")
            result.reasons.append(f"Pass-Why audit failed; keep candidate under review: {type(exc).__name__}")
            return result

    @staticmethod
    def _fail(result: PassWhyResult, code: str, reason: str, penalty: float) -> None:
        result.suspicious = True
        result.checks_failed += 1
        result.confidence_penalty += penalty
        result.reason_codes.append(code)
        result.reasons.append(reason)


_asker: Optional[PassWhyAsker] = None


def get_pass_why_asker() -> PassWhyAsker:
    global _asker
    if _asker is None:
        _asker = PassWhyAsker()
    return _asker


def reset_pass_why_asker() -> None:
    global _asker
    _asker = None


__all__ = [
    "PassWhyAsker",
    "PassWhyResult",
    "get_pass_why_asker",
    "reset_pass_why_asker",
]
