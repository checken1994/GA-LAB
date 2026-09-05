"""Human comprehension gate for high-stakes approvals (governance.human_comprehension).

CE-S11-01/CE-S11-03 contract: a high-stakes approval may only be accepted when
the human demonstrably understands WHAT will happen, to WHICH resource, with
WHAT consequence, on WHAT evidence, against WHICH contradictions and unknowns,
and HOW the action is rolled back. Approval is comprehension-gated, not a
rubber stamp.

must_not_effect (S11 forbidden paths):
- approval_as_only_control: a certified approval grants NO capability by
  itself; it only certifies understanding and stays subject to
  PolicyAuthority/CapabilityAuthority (see ``ComprehensionResult``).
- implicit_ALLOW_on_UNKNOWN: unresolved unknowns/contradictions can never be
  approved implicitly; every concern must be explicitly acknowledged by the
  approver on the exact bundle digest.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum


class ComprehensionStatus(str, Enum):
    UNDERSTOOD_APPROVED = "UNDERSTOOD_APPROVED"
    REJECTED = "REJECTED"
    BLOCKED_INCOMPLETE_BUNDLE = "BLOCKED_INCOMPLETE_BUNDLE"
    BLOCKED_STALE_APPROVAL = "BLOCKED_STALE_APPROVAL"
    BLOCKED_RUBBER_STAMP = "BLOCKED_RUBBER_STAMP"


@dataclass(frozen=True)
class Concern:
    """A contradiction or unknown that the approver must consciously acknowledge."""

    concern_id: str
    kind: str  # "contradiction" | "unknown"
    description: str


@dataclass(frozen=True)
class ComprehensionBundle:
    """The seven mandatory comprehension fields of a high-stakes proposal."""

    action: str
    resource: str
    consequence: str
    evidence: tuple[str, ...]
    contradictions: tuple[Concern, ...]
    unknowns: tuple[Concern, ...]
    rollback_plan: str
    rollback_verified: bool
    concerns: tuple[Concern, ...] = field(default=())
    digest: str = ""

    def canonical_json(self) -> str:
        return json.dumps(
            {
                "action": self.action,
                "resource": self.resource,
                "consequence": self.consequence,
                "evidence": list(self.evidence),
                "contradictions": [[c.concern_id, c.description] for c in self.contradictions],
                "unknowns": [[u.concern_id, u.description] for u in self.unknowns],
                "rollback_plan": self.rollback_plan,
                "rollback_verified": self.rollback_verified,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class HumanApproval:
    """What the human actually acknowledged. Kept separate from the bundle so
    the gate can compare acknowledgement against the presented material."""

    approver: str
    acknowledged_bundle_digest: str
    acknowledged_concern_ids: tuple[str, ...] = ()
    acknowledged_rollback: bool = False
    comment: str = ""


@dataclass(frozen=True)
class ComprehensionResult:
    status: ComprehensionStatus
    reasons: tuple[str, ...]
    bundle_digest: str = ""
    residual_unknowns: tuple[str, ...] = ()
    # approval_as_only_control is structurally forbidden: this is a constant,
    # not a knob. Understanding alone never authorizes execution.
    grants_capability: bool = False


def _digest(canonical: str) -> str:
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _concern(kind: str, index: int, description: str) -> Concern:
    prefix = "C" if kind == "contradiction" else "U"
    return Concern(concern_id=f"{prefix}-{index}", kind=kind, description=description)


class HumanComprehensionGate:
    """Builds comprehension bundles and validates approvals against them."""

    def build_bundle(
        self,
        *,
        action: str,
        resource: str,
        consequence: str,
        evidence: tuple[str, ...] | list[str] = (),
        contradictions: tuple[str, ...] | list[str] = (),
        unknowns: tuple[str, ...] | list[str] = (),
        rollback_plan: str,
        rollback_verified: bool = False,
    ) -> ComprehensionBundle:
        missing = [
            name
            for name, value in (
                ("action", action),
                ("resource", resource),
                ("consequence", consequence),
                ("rollback_plan", rollback_plan),
            )
            if not str(value or "").strip()
        ]
        if missing:
            # Fail-closed: an incomplete bundle cannot be approved at all.
            raise ValueError(f"incomplete comprehension bundle, missing: {sorted(missing)}")
        if not [item for item in evidence if str(item).strip()]:
            raise ValueError("incomplete comprehension bundle, missing: ['evidence']")

        contradiction_concerns = tuple(
            _concern("contradiction", i, str(text).strip())
            for i, text in enumerate(contradictions, start=1)
            if str(text).strip()
        )
        unknown_concerns = list(
            _concern("unknown", i, str(text).strip())
            for i, text in enumerate(unknowns, start=1)
            if str(text).strip()
        )
        derived_unknowns = list(unknown_concerns)
        if not rollback_verified:
            # An unverified rollback is itself an unknown; it can never be
            # silently promoted to "safe" by the presenter.
            derived_unknowns.append(
                Concern("U-rollback", "unknown", "rollback plan has not been verified")
            )

        bundle = ComprehensionBundle(
            action=str(action).strip(),
            resource=str(resource).strip(),
            consequence=str(consequence).strip(),
            evidence=tuple(str(item).strip() for item in evidence if str(item).strip()),
            contradictions=contradiction_concerns,
            unknowns=tuple(derived_unknowns),
            rollback_plan=str(rollback_plan).strip(),
            rollback_verified=bool(rollback_verified),
        )
        all_concerns = tuple(contradiction_concerns) + tuple(derived_unknowns)
        object.__setattr__(bundle, "concerns", all_concerns)
        object.__setattr__(bundle, "digest", _digest(bundle.canonical_json()))
        return bundle

    def evaluate(self, bundle: ComprehensionBundle, approval: HumanApproval) -> ComprehensionResult:
        # 1. Bundle must still be complete at evaluation time (fail-closed).
        try:
            self.build_bundle(
                action=bundle.action,
                resource=bundle.resource,
                consequence=bundle.consequence,
                evidence=bundle.evidence,
                contradictions=[c.description for c in bundle.contradictions if c.kind == "contradiction"],
                unknowns=[u.description for u in bundle.unknowns if u.concern_id != "U-rollback"],
                rollback_plan=bundle.rollback_plan,
                rollback_verified=bundle.rollback_verified,
            )
        except ValueError as exc:
            return ComprehensionResult(
                ComprehensionStatus.BLOCKED_INCOMPLETE_BUNDLE,
                (f"bundle cannot be approved: {exc}",),
                bundle.digest,
            )

        residual_unknowns = tuple(u.concern_id for u in bundle.unknowns)

        # 2. Approval must be attached to THIS bundle, not a stale/edited one.
        if not approval.approver or not approval.approver.strip():
            return ComprehensionResult(
                ComprehensionStatus.REJECTED, ("approval has no accountable approver",), bundle.digest
            )
        if approval.acknowledged_bundle_digest != bundle.digest:
            return ComprehensionResult(
                ComprehensionStatus.BLOCKED_STALE_APPROVAL,
                (
                    "approval is bound to a different bundle digest "
                    f"(approval={approval.acknowledged_bundle_digest or 'none'} bundle={bundle.digest})"
                ),
                bundle.digest,
            )

        # 3. implicit_ALLOW_on_UNKNOWN is forbidden: every presented concern
        #    must be explicitly acknowledged by the approver.
        acknowledged = {str(cid) for cid in approval.acknowledged_concern_ids}
        unacknowledged = [c.concern_id for c in bundle.concerns if c.concern_id not in acknowledged]
        if unacknowledged:
            return ComprehensionResult(
                ComprehensionStatus.BLOCKED_RUBBER_STAMP,
                (
                    "approval ignored presented concerns without acknowledgement: "
                    + ",".join(unacknowledged),
                ),
                bundle.digest,
                residual_unknowns,
            )

        # 4. The approver must explicitly confirm the rollback understanding.
        if not approval.acknowledged_rollback:
            return ComprehensionResult(
                ComprehensionStatus.BLOCKED_RUBBER_STAMP,
                ("rollback plan was not acknowledged",),
                bundle.digest,
                residual_unknowns,
            )

        reasons = [
            "all seven comprehension fields presented and acknowledged on exact bundle digest",
        ]
        if residual_unknowns:
            reasons.append(
                "unknowns acknowledged explicitly, not implicitly resolved: " + ",".join(residual_unknowns)
            )
        reasons.append(
            "comprehension certified only; grants no capability (approval_as_only_control forbidden)"
        )
        return ComprehensionResult(
            ComprehensionStatus.UNDERSTOOD_APPROVED,
            tuple(reasons),
            bundle.digest,
            residual_unknowns,
        )


__all__ = [
    "ComprehensionBundle",
    "ComprehensionResult",
    "ComprehensionStatus",
    "Concern",
    "HumanApproval",
    "HumanComprehensionGate",
]
