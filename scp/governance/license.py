"""License/copyright governance for knowledge and artifacts (governance.license_copyright).

CE-S11-05 contract: knowledge/artifacts proposed for ingestion, redistribution,
execution or external release are evaluated against their license status and
yield ALLOW/RESTRICT/QUARANTINE/DENY/REQUIRE_HUMAN together with provenance and
usage constraints.

must_not_effect (S11 forbidden paths):
- unknown_license_as_unrestricted: an unknown/unparseable license is never
  ALLOW. All usages of an unknown-license artifact are QUARANTINE, and
  ``assert_no_forbidden_effect`` raises on any attempt to mark such an
  artifact "unrestricted".
- License identifiers that are not in the known policy table are treated as
  unknown (fail-closed), not as permissive by default.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LicenseStatus(str, Enum):
    ALLOW = "ALLOW"
    RESTRICT = "RESTRICT"
    REQUIRE_HUMAN = "REQUIRE_HUMAN"
    QUARANTINE = "QUARANTINE"
    DENY = "DENY"


class Usage(str, Enum):
    INGESTION = "INGESTION"
    REDISTRIBUTION = "REDISTRIBUTION"
    EXECUTION = "EXECUTION"
    EXTERNAL_RELEASE = "EXTERNAL_RELEASE"


_SEVERITY = {
    LicenseStatus.ALLOW: 0,
    LicenseStatus.RESTRICT: 1,
    LicenseStatus.REQUIRE_HUMAN: 2,
    LicenseStatus.QUARANTINE: 3,
    LicenseStatus.DENY: 4,
}


class ForbiddenLicensePath(RuntimeError):
    """Raised when a caller tries to materialize an S11 forbidden path."""


@dataclass(frozen=True)
class ProvenanceRecord:
    artifact_id: str
    license_id: str | None
    source: str | None
    version: str | None = None
    copyright_holder: str | None = None


@dataclass(frozen=True)
class LicenseDecision:
    artifact_id: str
    usage: Usage
    status: LicenseStatus
    license_family: str
    constraints: tuple[str, ...]
    provenance: dict
    reason: str


# SPDX-like family table. Anything not present here is UNKNOWN (fail-closed).
_LICENSE_FAMILIES: dict[str, str] = {
    "MIT": "permissive",
    "MIT-0": "permissive",
    "BSD-2-CLAUSE": "permissive",
    "BSD-3-CLAUSE": "permissive",
    "APACHE-2.0": "permissive",
    "ISC": "permissive",
    "ZLIB": "permissive",
    "UNLICENSE": "permissive",
    "CC0-1.0": "permissive",
    "PSF-2.0": "permissive",
    "CC-BY-4.0": "attribution",
    "CC-BY-3.0": "attribution",
    "CC-BY-SA-4.0": "attribution_sharealike",
    "LGPL-2.1-ONLY": "copyleft_weak",
    "LGPL-3.0-ONLY": "copyleft_weak",
    "MPL-2.0": "copyleft_weak",
    "EPL-2.0": "copyleft_weak",
    "GPL-2.0-ONLY": "copyleft_strong",
    "GPL-3.0-ONLY": "copyleft_strong",
    "AGPL-3.0-ONLY": "copyleft_strong",
    "CC-BY-NC-4.0": "noncommercial",
    "CC-BY-NC-SA-4.0": "noncommercial",
    "CC-BY-NC-ND-4.0": "noncommercial",
    "CC-BY-ND-4.0": "no_derivatives",
    "PROPRIETARY": "proprietary",
    "COMMERCIAL": "proprietary",
    "LICENSEREF-PROPRIETARY": "proprietary",
    "BSL-1.1": "proprietary",
}

_UNKNOWN_LICENSE_TOKENS = {"", "UNKNOWN", "NOASSERTION", "NONE", "LICENSEREF-UNKNOWN", "OTHER"}

# usage -> family -> status
_POLICY: dict[Usage, dict[str, LicenseStatus]] = {
    Usage.INGESTION: {
        "permissive": LicenseStatus.ALLOW,
        "attribution": LicenseStatus.ALLOW,
        "attribution_sharealike": LicenseStatus.ALLOW,
        "copyleft_weak": LicenseStatus.ALLOW,
        "copyleft_strong": LicenseStatus.ALLOW,
        "noncommercial": LicenseStatus.ALLOW,
        "no_derivatives": LicenseStatus.ALLOW,
        "proprietary": LicenseStatus.RESTRICT,
    },
    Usage.REDISTRIBUTION: {
        "permissive": LicenseStatus.ALLOW,
        "attribution": LicenseStatus.ALLOW,
        "attribution_sharealike": LicenseStatus.RESTRICT,
        "copyleft_weak": LicenseStatus.RESTRICT,
        "copyleft_strong": LicenseStatus.RESTRICT,
        "noncommercial": LicenseStatus.REQUIRE_HUMAN,
        "no_derivatives": LicenseStatus.REQUIRE_HUMAN,
        "proprietary": LicenseStatus.DENY,
    },
    Usage.EXECUTION: {
        "permissive": LicenseStatus.ALLOW,
        "attribution": LicenseStatus.ALLOW,
        "attribution_sharealike": LicenseStatus.ALLOW,
        "copyleft_weak": LicenseStatus.ALLOW,
        "copyleft_strong": LicenseStatus.RESTRICT,
        "noncommercial": LicenseStatus.RESTRICT,
        "no_derivatives": LicenseStatus.ALLOW,
        "proprietary": LicenseStatus.REQUIRE_HUMAN,
    },
    Usage.EXTERNAL_RELEASE: {
        "permissive": LicenseStatus.ALLOW,
        "attribution": LicenseStatus.ALLOW,
        "attribution_sharealike": LicenseStatus.RESTRICT,
        "copyleft_weak": LicenseStatus.RESTRICT,
        "copyleft_strong": LicenseStatus.REQUIRE_HUMAN,
        "noncommercial": LicenseStatus.DENY,
        "no_derivatives": LicenseStatus.REQUIRE_HUMAN,
        "proprietary": LicenseStatus.DENY,
    },
}

_FAMILY_CONSTRAINTS: dict[str, str] = {
    "permissive": "preserve_license_notice",
    "attribution": "attribution_required",
    "attribution_sharealike": "share_alike_required",
    "copyleft_weak": "file_level_copyleft_obligations",
    "copyleft_strong": "copyleft_obligations_apply_to_derivatives",
    "noncommercial": "noncommercial_use_only",
    "no_derivatives": "no_derivatives",
    "proprietary": "vendor_license_terms_apply",
}


class LicenseAuthority:
    def __init__(self, denied_license_ids: set[str] | None = None) -> None:
        self._denied = {self._normalize(x) for x in (denied_license_ids or set())}

    @staticmethod
    def _normalize(license_id: str | None) -> str:
        return str(license_id or "").strip().upper().replace("_", "-")

    def family_of(self, license_id: str | None) -> str:
        normalized = self._normalize(license_id)
        if normalized in _UNKNOWN_LICENSE_TOKENS or normalized in self._denied:
            return "unknown" if normalized not in self._denied else "denied"
        return _LICENSE_FAMILIES.get(normalized, "unknown")

    @staticmethod
    def _provenance_complete(record: ProvenanceRecord) -> bool:
        return bool(str(record.source or "").strip()) and bool(str(record.artifact_id or "").strip())

    def evaluate(self, record: ProvenanceRecord, usage: Usage) -> LicenseDecision:
        if not str(record.artifact_id or "").strip():
            raise ValueError("provenance record requires artifact_id")
        family = self.family_of(record.license_id)
        provenance = {
            "artifact_id": record.artifact_id,
            "license_id": (record.license_id or "").strip() or None,
            "source": (record.source or "").strip() or None,
            "version": (record.version or "").strip() or None,
            "copyright_holder": (record.copyright_holder or "").strip() or None,
        }

        if family == "denied":
            return LicenseDecision(
                record.artifact_id,
                usage,
                LicenseStatus.DENY,
                family,
                ("license_is_explicitly_denied_by_policy",),
                provenance,
                f"license {record.license_id!r} is on the explicit deny list",
            )

        if family == "unknown":
            # unknown_license_as_unrestricted is forbidden: unknown is
            # QUARANTINE for every usage, with provenance recorded.
            return LicenseDecision(
                record.artifact_id,
                usage,
                LicenseStatus.QUARANTINE,
                family,
                ("quarantined_until_license_resolved", "no_redistribution", "no_external_release"),
                provenance,
                f"license is unknown/unrecognized ({record.license_id!r}); "
                "quarantine applied instead of unrestricted use",
            )

        status = _POLICY[usage][family]
        constraints = [_FAMILY_CONSTRAINTS[family]]
        if record.copyright_holder:
            constraints.append(f"attribute_copyright_holder:{record.copyright_holder}")

        if not self._provenance_complete(record):
            # A known license without provenance cannot be attributed, so the
            # decision escalates to a human instead of flowing through.
            status = _worse(status, LicenseStatus.REQUIRE_HUMAN)
            constraints.append("provenance_incomplete_requires_human")
        return LicenseDecision(
            record.artifact_id,
            usage,
            status,
            family,
            tuple(constraints),
            provenance,
            f"{usage.value} of {family} license {record.license_id!r} -> {status.value}",
        )

    def evaluate_bundle(
        self, records: tuple[ProvenanceRecord, ...] | list[ProvenanceRecord], usage: Usage
    ) -> LicenseDecision:
        decisions = [self.evaluate(record, usage) for record in records]
        if not decisions:
            raise ValueError("license bundle requires at least one provenance record")
        worst = max(decisions, key=lambda d: _SEVERITY[d.status])
        constraints: list[str] = []
        for decision in decisions:
            for constraint in decision.constraints:
                if constraint not in constraints:
                    constraints.append(constraint)
        return LicenseDecision(
            artifact_id="+".join(d.artifact_id for d in decisions),
            usage=usage,
            status=worst.status,
            license_family="bundle",
            constraints=tuple(constraints),
            provenance={"components": [d.provenance for d in decisions]},
            reason=f"bundle worst-case {worst.status.value} from {worst.reason}",
        )

    def assert_no_forbidden_effect(self, record: ProvenanceRecord, proposed_effect: str) -> None:
        """Enforce S11 forbidden paths at the point of effect.

        - license_unknown -> unrestricted_redistribution is FORBIDDEN.
        - unknown/denied license -> any redistribution/release effect is
          FORBIDDEN (a distribution effect requires a resolved ALLOW status).
        """
        effect = str(proposed_effect or "").strip().lower().replace("-", "_")
        if not effect:
            return
        family = self.family_of(record.license_id)
        if family == "unknown" and "unrestricted" in effect:
            raise ForbiddenLicensePath(
                f"forbidden path license_unknown -> {proposed_effect}: "
                "unknown license can never be unrestricted"
            )
        if family in {"denied", "unknown"} and ("redistribution" in effect or "release" in effect):
            raise ForbiddenLicensePath(
                f"forbidden path license_{family} -> {proposed_effect}: "
                "distribution effect requires a resolved, ALLOW status"
            )


def _worse(a: LicenseStatus, b: LicenseStatus) -> LicenseStatus:
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


__all__ = [
    "ForbiddenLicensePath",
    "LicenseAuthority",
    "LicenseDecision",
    "LicenseStatus",
    "ProvenanceRecord",
    "Usage",
]
