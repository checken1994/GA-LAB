"""Dangerous-knowledge classification (governance.dangerous_knowledge).

CE-S11-05 contract: knowledge proposed for ingestion/execution is classified as
SAFE_REFERENCE, RESTRICTED_REFERENCE, ACTIONABLE_HIGH_RISK or PROHIBITED_RAW.
RESTRICTED and above never become executable instructions: they stay
reference-only, quarantined for human review, or blocked outright.

must_not_effect (S11 forbidden path):
- dangerous_content_as_executable_instruction: only SAFE_REFERENCE content is
  execution-eligible; ``KnowledgeRouteRequest`` for any higher class raises
  ``ForbiddenExecutableRoute``, and ``DangerClassification.execution_eligible``
  is derived from the classification, not from caller-supplied labels.
- Caller-declared labels ("declared_safe") are recorded but never trusted over
  the content signals (learned_content -> governance_override forbidden).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class DangerClass(str, Enum):
    SAFE_REFERENCE = "SAFE_REFERENCE"
    RESTRICTED_REFERENCE = "RESTRICTED_REFERENCE"
    ACTIONABLE_HIGH_RISK = "ACTIONABLE_HIGH_RISK"
    PROHIBITED_RAW = "PROHIBITED_RAW"


_SEVERITY = {
    DangerClass.SAFE_REFERENCE: 0,
    DangerClass.RESTRICTED_REFERENCE: 1,
    DangerClass.ACTIONABLE_HIGH_RISK: 2,
    DangerClass.PROHIBITED_RAW: 3,
}

_RESTRICTED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cve_reference", re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.I)),
    ("pentest_methodology", re.compile(r"\b(penetration[ -]test|exploitation technique|vulnerability assessment)\b", re.I)),
    ("dual_use_tooling", re.compile(r"\b(nmap|metasploit|wireshark|burp suite|sqlmap)\b", re.I)),
    ("malware_analysis", re.compile(r"\b(malware analysis|reverse engineering (?:a )?binary|sandbox escape research)\b", re.I)),
)

_HIGH_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("weaponized_poc", re.compile(r"\b(working exploit|proof[ -]of[ -]concept exploit|remote code execution poc)\b", re.I)),
    ("destructive_command", re.compile(r"\brm\s+-rf\s+[~/\\]|\bmkfs(\.\w+)?\s+|:\(\)\{\s*:\|\:&\s*\};:", re.I)),
    ("reverse_shell_recipe", re.compile(r"\b(?:bash\s+-i\s*>&\s*/dev/tcp/|nc(?:at)?\s+-e\s+/bin/(?:ba)?sh|powershell\s+-enc\s+[A-Za-z0-9+/=]{16,})", re.I)),
    ("credential_theft_procedure", re.compile(r"\b(dump (?:lsass|credentials|password hashes)|mimikatz|pass[- ]the[- ]hash)\b", re.I)),
    ("exploit_chain_steps", re.compile(r"\b(step\s*1.{0,400}step\s*2.{0,400}(?:shell|root|bypass))\b", re.I | re.S)),
)

_PROHIBITED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("raw_exploit_payload", re.compile(r"(?:\$\(|`)\s*(?:curl|wget)\s+[^`\n]{0,200}\|\s*(?:ba)?sh\b", re.I)),
    ("ransomware_builder", re.compile(r"\b(ransomware (?:builder|source)|encrypt (?:all )?files and demand)\b", re.I)),
    ("credential_exfil_raw", re.compile(r"\b(exfiltrat\w+ (?:via|over) (?:dns|icmp|https beacons?))\b", re.I)),
    ("autonomous_exploit_shellcode", re.compile(r"\\x[0-9a-f]{2}(?:\\x[0-9a-f]{2}){15,}", re.I)),
    ("bioweapon_synthesis", re.compile(r"\b(synthesi[sz]e (?:novel )?toxin|engineer (?:a )?pathogen)\b", re.I)),
)


class ForbiddenExecutableRoute(RuntimeError):
    """Raised when restricted-or-worse knowledge is routed to execution."""


@dataclass(frozen=True)
class KnowledgeInput:
    content: str
    title: str = ""
    source: str = ""
    declared_label: str = ""  # recorded, never trusted


@dataclass(frozen=True)
class DangerClassification:
    danger_class: DangerClass
    signals: tuple[str, ...]
    reason: str
    declared_label: str = ""

    @property
    def execution_eligible(self) -> bool:
        # dangerous_content_as_executable_instruction is forbidden: derived
        # strictly from the classification, not from any caller preference.
        return self.danger_class is DangerClass.SAFE_REFERENCE


@dataclass(frozen=True)
class IngestDecision:
    route: str  # "INGEST_REFERENCE" | "QUARANTINE_HUMAN_REVIEW" | "BLOCK_NO_STORAGE"
    classification: DangerClassification
    reference_only: bool
    reasons: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class KnowledgeRouteRequest:
    classification: DangerClassification
    requested_route: str  # e.g. "execution", "knowledge_store", "prompt_context"


class DangerousKnowledgeAuthority:
    def classify(self, knowledge: KnowledgeInput) -> DangerClassification:
        content = str(knowledge.content or "")
        signals: list[str] = []

        def scan(patterns) -> list[str]:
            return [name for name, pattern in patterns if pattern.search(content)]

        restricted = scan(_RESTRICTED_PATTERNS)
        high_risk = scan(_HIGH_RISK_PATTERNS)
        prohibited = scan(_PROHIBITED_PATTERNS)

        if prohibited:
            signals.extend(prohibited)
            danger = DangerClass.PROHIBITED_RAW
            reason = "raw prohibited content present; must not be stored or executed"
        elif high_risk:
            signals.extend(high_risk)
            danger = DangerClass.ACTIONABLE_HIGH_RISK
            reason = "actionable high-risk procedure detected; quarantine for human review"
        elif restricted:
            signals.extend(restricted)
            danger = DangerClass.RESTRICTED_REFERENCE
            reason = "dual-use/security-research reference; reference-only, not executable"
        else:
            danger = DangerClass.SAFE_REFERENCE
            reason = "no dangerous-knowledge signals detected"

        # Caller labels never override content signals.
        if knowledge.declared_label and knowledge.declared_label.upper() != danger.value:
            signals.append(f"declared_label_ignored:{knowledge.declared_label}")
        return DangerClassification(
            danger_class=danger,
            signals=tuple(signals),
            reason=reason,
            declared_label=str(knowledge.declared_label or ""),
        )

    def ingest(self, knowledge: KnowledgeInput) -> IngestDecision:
        classification = self.classify(knowledge)
        if classification.danger_class is DangerClass.SAFE_REFERENCE:
            return IngestDecision("INGEST_REFERENCE", classification, False, (classification.reason,))
        if classification.danger_class is DangerClass.RESTRICTED_REFERENCE:
            return IngestDecision(
                "INGEST_REFERENCE",
                classification,
                True,
                (classification.reason, "stored as reference-only; execution routing forbidden"),
            )
        if classification.danger_class is DangerClass.ACTIONABLE_HIGH_RISK:
            return IngestDecision(
                "QUARANTINE_HUMAN_REVIEW", classification, True, (classification.reason,)
            )
        return IngestDecision(
            "BLOCK_NO_STORAGE",
            classification,
            True,
            (classification.reason, "only a content hash and safe summary may be retained"),
        )

    def route(self, request: KnowledgeRouteRequest) -> IngestDecision | None:
        """Validate a routing request against the classification.

        Only SAFE_REFERENCE may be routed to "execution"; restricted or worse
        raises ForbiddenExecutableRoute (fail-closed).
        """
        classification = request.classification
        requested = str(request.requested_route or "").strip().lower()
        if requested in {"execution", "execute", "tool_call", "auto_execution"}:
            if not classification.execution_eligible:
                raise ForbiddenExecutableRoute(
                    f"forbidden path dangerous_content_as_executable_instruction: "
                    f"{classification.danger_class.value} cannot be routed to execution"
                )
            return IngestDecision("EXECUTE", classification, False, ("safe reference routed to execution",))
        if requested in {"knowledge_store", "reference", "prompt_context"}:
            if classification.danger_class is DangerClass.PROHIBITED_RAW:
                return IngestDecision(
                    "BLOCK_NO_STORAGE",
                    classification,
                    True,
                    ("prohibited raw content cannot enter any store or prompt context",),
                )
            reference_only = not classification.execution_eligible
            route_name = (
                "INGEST_REFERENCE"
                if classification.danger_class in {DangerClass.SAFE_REFERENCE, DangerClass.RESTRICTED_REFERENCE}
                else "QUARANTINE_HUMAN_REVIEW"
            )
            reasons = ["routing respects content-derived classification"]
            if reference_only:
                reasons.append("restricted content is reference-only; execution routing forbidden")
            return IngestDecision(route_name, classification, reference_only, tuple(reasons))
        raise ValueError(f"unknown requested_route: {request.requested_route!r}")


__all__ = [
    "DangerClass",
    "DangerClassification",
    "DangerousKnowledgeAuthority",
    "ForbiddenExecutableRoute",
    "IngestDecision",
    "KnowledgeInput",
    "KnowledgeRouteRequest",
]
