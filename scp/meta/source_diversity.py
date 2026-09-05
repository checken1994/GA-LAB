"""
SCP V3 Source Diversity Audit port, adapted to P0 SourceIdentity/Lineage.

Donor lineage:
  scp-v3-world-standard.zip::scp-backend/services/meta_cognition/source_diversity.py

The donor's concentration checks are retained.  Its old assumption
"same domain => same lineage" is intentionally NOT retained: current
``LineageStore`` is the authority for source independence and UNKNOWN
independence contributes zero independent support.
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_MAX_SINGLE_SOURCE_SHARE = 0.40
_MAX_SINGLE_DOMAIN_SHARE = 0.50
_MIN_UNIQUE_SOURCES = 3


@dataclass
class SourceDiversityResult:
    audited_at: float = field(default_factory=time.time)
    total_evidence: int = 0
    unique_sources: int = 0
    unique_domains: int = 0
    top_source_share: float = 0.0
    top_domain_share: float = 0.0
    concentration_score: float = 0.0
    known_independent_lineages: int = 0
    unknown_lineage_pairs: int = 0
    shared_lineage_pairs: int = 0
    lineage_assessed: bool = False
    lineage_risk_score: float = 1.0
    overall_score: float = 0.0
    recommendation: str = "REVIEW"  # OK | WATCH | CAPTURE_RISK | REVIEW
    findings: list[str] = field(default_factory=list)
    top_sources: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "audited_at": datetime.fromtimestamp(self.audited_at, tz=timezone.utc).isoformat(),
            "total_evidence": self.total_evidence,
            "unique_sources": self.unique_sources,
            "unique_domains": self.unique_domains,
            "top_source_share": round(self.top_source_share, 4),
            "top_domain_share": round(self.top_domain_share, 4),
            "concentration_score": round(self.concentration_score, 4),
            "known_independent_lineages": self.known_independent_lineages,
            "unknown_lineage_pairs": self.unknown_lineage_pairs,
            "shared_lineage_pairs": self.shared_lineage_pairs,
            "lineage_assessed": self.lineage_assessed,
            "lineage_risk_score": round(self.lineage_risk_score, 4),
            "overall_score": round(self.overall_score, 4),
            "recommendation": self.recommendation,
            "findings": list(self.findings),
            "top_sources": list(self.top_sources[:10]),
        }


class SourceDiversityAuditor:
    """Detect evidence concentration without manufacturing independence.

    ``lineage_store`` may be a current ``scp.epistemic.lineage.LineageStore``.
    When it is absent or cannot assess the supplied source ids, the result stays
    REVIEW rather than assuming sources are independent.
    """

    def __init__(self, lineage_store: Any = None) -> None:
        self.lineage_store = lineage_store

    def audit(
        self,
        evidence: Optional[Iterable[dict[str, Any]]] = None,
        *,
        source_ids: Optional[Iterable[str]] = None,
    ) -> SourceDiversityResult:
        result = SourceDiversityResult()
        try:
            evidence_items = [item for item in (evidence or []) if isinstance(item, dict)]
            supplied_source_ids = [str(item).strip() for item in (source_ids or []) if str(item).strip()]

            source_counts: Counter[str] = Counter()
            domain_counts: Counter[str] = Counter()
            derived_source_ids: list[str] = []

            for item in evidence_items:
                source_id = str(item.get("source_id") or "").strip()
                source = str(item.get("source") or item.get("url") or source_id or "unknown").strip()
                source_counts[source.lower()] += 1
                domain = self._extract_domain(source)
                if domain:
                    domain_counts[domain] += 1
                if source_id:
                    derived_source_ids.append(source_id)

            # If the caller has only source ids (common on current LineageStore
            # paths), include them in concentration accounting without pretending
            # they are web domains.
            if not evidence_items and supplied_source_ids:
                for source_id in supplied_source_ids:
                    source_counts[source_id.lower()] += 1

            result.total_evidence = sum(source_counts.values())
            result.unique_sources = len(source_counts)
            result.unique_domains = len(domain_counts)

            if not source_counts:
                result.findings.append("NO_SOURCE_EVIDENCE")
                result.recommendation = "REVIEW"
                return result

            top_source, top_count = source_counts.most_common(1)[0]
            result.top_source_share = top_count / result.total_evidence
            result.top_sources = [
                {"source": src, "count": count, "share": round(count / result.total_evidence, 4)}
                for src, count in source_counts.most_common(10)
            ]
            if domain_counts:
                result.top_domain_share = domain_counts.most_common(1)[0][1] / result.total_evidence

            result.concentration_score = self._compute_concentration(
                result.top_source_share,
                result.top_domain_share,
                result.unique_sources,
            )

            lineage_source_ids = sorted(set(supplied_source_ids + derived_source_ids))
            if self.lineage_store is not None and lineage_source_ids:
                assessment = self.lineage_store.assess_independent_support(lineage_source_ids)
                result.lineage_assessed = True
                result.known_independent_lineages = int(assessment.get("known_independent_lineages", 0))
                result.unknown_lineage_pairs = int(assessment.get("unknown_pairs", 0))
                result.shared_lineage_pairs = int(assessment.get("shared_lineage_pairs", 0))
                # Conservative risk: unknown/shared relations cannot be treated as
                # diversity.  A single explicitly independent group is still weak
                # diversity for a multi-source Internet claim.
                source_count = max(1, int(assessment.get("source_count", len(lineage_source_ids))))
                result.lineage_risk_score = max(
                    0.0,
                    1.0 - min(1.0, result.known_independent_lineages / source_count),
                )
            else:
                result.lineage_assessed = False
                result.lineage_risk_score = 1.0
                result.findings.append("LINEAGE_NOT_ASSESSED")

            result.overall_score = max(
                0.0,
                1.0 - max(result.concentration_score, result.lineage_risk_score),
            )

            if result.top_source_share > _MAX_SINGLE_SOURCE_SHARE:
                result.findings.append(
                    f"TOP_SOURCE_CONCENTRATION:{result.top_source_share:.3f}>{_MAX_SINGLE_SOURCE_SHARE:.2f}"
                )
            if result.top_domain_share > _MAX_SINGLE_DOMAIN_SHARE:
                result.findings.append(
                    f"TOP_DOMAIN_CONCENTRATION:{result.top_domain_share:.3f}>{_MAX_SINGLE_DOMAIN_SHARE:.2f}"
                )
            if result.unique_sources < _MIN_UNIQUE_SOURCES:
                result.findings.append(
                    f"FEW_UNIQUE_SOURCES:{result.unique_sources}<{_MIN_UNIQUE_SOURCES}"
                )

            if result.lineage_assessed:
                if result.known_independent_lineages <= 1 and result.unique_sources > 1:
                    result.findings.append("INSUFFICIENT_KNOWN_INDEPENDENT_LINEAGES")
                if result.unknown_lineage_pairs:
                    result.findings.append(f"UNKNOWN_LINEAGE_PAIRS:{result.unknown_lineage_pairs}")

            if not result.lineage_assessed:
                # Concentration findings are still reported, but without the
                # current Lineage authority we cannot label the sources as
                # captured/independent with authority. Keep the epistemic
                # recommendation at REVIEW.
                result.recommendation = "REVIEW"
            elif result.concentration_score >= 0.70 or (
                result.known_independent_lineages <= 1 and result.unique_sources >= 3
            ):
                result.recommendation = "CAPTURE_RISK"
            elif result.overall_score < 0.60:
                result.recommendation = "WATCH"
            else:
                result.recommendation = "OK"

            if not result.findings:
                result.findings.append("SOURCE_DIVERSITY_OK_WITHIN_ASSESSED_SCOPE")
            return result
        except Exception as exc:
            # Fail closed: the V3 donor accidentally returned recommendation=OK
            # on audit failure.  Current SCP must surface UNKNOWN/REVIEW.
            logger.exception("[source_diversity] audit failed")
            result.recommendation = "REVIEW"
            result.lineage_assessed = False
            result.lineage_risk_score = 1.0
            result.overall_score = 0.0
            result.findings = [f"AUDIT_ERROR:{type(exc).__name__}"]
            return result

    @staticmethod
    def _compute_concentration(top_source_share: float, top_domain_share: float, unique_sources: int) -> float:
        score = 0.0
        if top_source_share > _MAX_SINGLE_SOURCE_SHARE:
            score += (top_source_share - _MAX_SINGLE_SOURCE_SHARE) / (1.0 - _MAX_SINGLE_SOURCE_SHARE)
        if top_domain_share > _MAX_SINGLE_DOMAIN_SHARE:
            score += (top_domain_share - _MAX_SINGLE_DOMAIN_SHARE) / (1.0 - _MAX_SINGLE_DOMAIN_SHARE)
        if unique_sources < _MIN_UNIQUE_SOURCES:
            score += 0.30
        return min(1.0, score)

    @staticmethod
    def _extract_domain(source: str) -> str:
        value = str(source or "").strip().lower()
        if not value or value == "unknown":
            return ""
        try:
            if "://" in value:
                return (urlparse(value).hostname or "").lower()
        except Exception:
            return ""
        return ""


__all__ = ["SourceDiversityAuditor", "SourceDiversityResult"]
