"""External authority governance (governance.external_authority).

CE-S11-03 contract: when an external authority connector action is requested,
the authority path is ExternalAuthorityGovernance -> HumanComprehension ->
HumanAuthority -> CapabilityAuthority, with effects REPORT_ONLY_by_default,
evidence_bundle_required and explicit_authority_if_send_allowed.

must_not_effect (S11 forbidden path):
- unconfigured_external_write: a connector that is not registered, or whose
  mode is not explicitly SEND_ALLOWED with a valid human-approved
  comprehension bundle, can never produce an outbound write. Unconfigured
  requests degrade to a bundle-only REPORT_ONLY result, and
  ``assert_no_unconfigured_write`` raises if a caller tries to send anyway.
- Raw credentials are refused by contract: only a ``credential_ref`` (an
  opaque reference resolved elsewhere, e.g. by the SecretBroker) is accepted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from scp.governance.comprehension import ComprehensionResult, ComprehensionStatus


class AuthorityMode(str, Enum):
    REPORT_ONLY = "REPORT_ONLY"
    SEND_ALLOWED = "SEND_ALLOWED"


class ExternalActionStatus(str, Enum):
    REPORT_ONLY = "REPORT_ONLY"
    BUNDLE_ONLY = "BUNDLE_ONLY"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED_TO_SEND = "APPROVED_TO_SEND"
    REQUIRE_EVIDENCE = "REQUIRE_EVIDENCE"
    DENIED = "DENIED"


class UnconfiguredExternalWrite(RuntimeError):
    """Raised when a send is attempted through an unconfigured/ungoverned path."""


@dataclass(frozen=True)
class ConnectorConfig:
    connector_id: str
    allowed_event_types: tuple[str, ...]
    risk_ceiling: int  # 0-100; requests above the ceiling are denied
    credential_ref: str  # opaque reference only; raw secrets are refused
    mode: AuthorityMode = AuthorityMode.REPORT_ONLY
    post_submit_verification_required: bool = True

    def __post_init__(self) -> None:
        if not str(self.connector_id or "").strip():
            raise ValueError("connector_id is required")
        if not self.allowed_event_types:
            raise ValueError("connector must declare allowed_event_types")
        if not 0 <= int(self.risk_ceiling) <= 100:
            raise ValueError("risk_ceiling must be within 0..100")
        if not str(self.credential_ref or "").strip():
            raise ValueError("credential_ref (opaque reference) is required")


@dataclass(frozen=True)
class ExternalActionRequest:
    connector_id: str
    event_type: str
    payload_summary: str
    risk_level: int  # 0-100, caller-declared and validated against ceiling
    credential_ref: str = ""

    def __post_init__(self) -> None:
        if any("\x00" in c for c in (self.event_type, self.payload_summary)):
            raise ValueError("control characters are not allowed in external action requests")
        if not 0 <= int(self.risk_level) <= 100:
            raise ValueError("risk_level must be within 0..100")


@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    supporting_evidence_ids: tuple[str, ...]
    conclusion: str

    def __post_init__(self) -> None:
        if not str(self.bundle_id or "").strip():
            raise ValueError("evidence bundle requires bundle_id")
        if not self.supporting_evidence_ids:
            raise ValueError("evidence bundle requires supporting evidence")
        if not str(self.conclusion or "").strip():
            raise ValueError("evidence bundle requires a stated conclusion")

    def is_sufficient(self) -> bool:
        return bool(self.supporting_evidence_ids) and bool(str(self.conclusion or "").strip())


@dataclass(frozen=True)
class ExternalAuthorityDecision:
    status: ExternalActionStatus
    reasons: tuple[str, ...]
    report_event: dict = field(default_factory=dict)
    submit_receipt: dict | None = None  # set only after an authorized send + verification

    @property
    def write_authorized(self) -> bool:
        return self.status is ExternalActionStatus.APPROVED_TO_SEND


@dataclass(frozen=True)
class PostSubmitVerification:
    verified: bool
    checks: tuple[str, ...]
    reasons: tuple[str, ...]


class ExternalAuthorityGovernance:
    """Gatekeeper for outbound actions through external authority connectors."""

    def __init__(self) -> None:
        self._connectors: dict[str, ConnectorConfig] = {}
        self._seen_submissions: dict[str, str] = {}

    def register_connector(self, config: ConnectorConfig) -> None:
        self._connectors[config.connector_id] = config

    def connector(self, connector_id: str) -> ConnectorConfig | None:
        return self._connectors.get(connector_id)

    def request_action(
        self,
        request: ExternalActionRequest,
        evidence: EvidenceBundle | None,
        comprehension: ComprehensionResult | None,
    ) -> ExternalAuthorityDecision:
        config = self._connectors.get(request.connector_id)
        report_event = {
            "connector_id": request.connector_id,
            "event_type": request.event_type,
            "payload_summary": request.payload_summary,
            "risk_level": request.risk_level,
            "credential_ref": request.credential_ref or None,
        }

        # 1. unconfigured_external_write is forbidden: unconfigured connectors
        #    degrade to a bundle-only REPORT_ONLY artifact, never a send.
        if config is None:
            return ExternalAuthorityDecision(
                ExternalActionStatus.BUNDLE_ONLY,
                (
                    "connector is not configured; no external write possible",
                    "request retained as evidence bundle only (REPORT_ONLY by default)",
                ),
                report_event,
            )

        # 2. Raw credentials are refused; only the opaque ref may transit.
        if request.credential_ref and request.credential_ref != config.credential_ref:
            return ExternalAuthorityDecision(
                ExternalActionStatus.DENIED,
                ("credential_ref does not match the configured brokered reference",),
                report_event,
            )

        # 3. Event type and risk ceiling checks (explicit authority scope).
        if request.event_type not in config.allowed_event_types:
            return ExternalAuthorityDecision(
                ExternalActionStatus.DENIED,
                (f"event_type {request.event_type!r} is outside the connector's allowed scope",),
                report_event,
            )
        if request.risk_level > config.risk_ceiling:
            return ExternalAuthorityDecision(
                ExternalActionStatus.DENIED,
                (
                    f"risk_level {request.risk_level} exceeds connector ceiling {config.risk_ceiling}",
                ),
                report_event,
            )

        # 4. evidence_bundle_required: no send path exists without one.
        if evidence is None or not evidence.is_sufficient():
            return ExternalAuthorityDecision(
                ExternalActionStatus.REQUIRE_EVIDENCE,
                ("evidence bundle required before any external action",),
                report_event,
            )

        report_event["evidence_bundle_id"] = evidence.bundle_id

        # 5. REPORT_ONLY mode (the default) never sends, by construction.
        if config.mode is AuthorityMode.REPORT_ONLY:
            return ExternalAuthorityDecision(
                ExternalActionStatus.REPORT_ONLY,
                (
                    "connector mode is REPORT_ONLY; action recorded, nothing sent",
                    "explicit SEND_ALLOWED authority is required for any outbound write",
                ),
                report_event,
            )

        # 6. SEND_ALLOWED still requires a comprehension-certified approval.
        if comprehension is None or comprehension.status is not ComprehensionStatus.UNDERSTOOD_APPROVED:
            return ExternalAuthorityDecision(
                ExternalActionStatus.WAITING_APPROVAL,
                (
                    "send-capable connector is approval-gated: waiting for a "
                    "comprehension-certified human approval",
                ),
                report_event,
            )

        return ExternalAuthorityDecision(
            ExternalActionStatus.APPROVED_TO_SEND,
            (
                "explicit send authority granted: configured connector, in-scope event, "
                "risk within ceiling, evidence bundle present, comprehension certified",
            ),
            report_event,
        )

    def assert_no_unconfigured_write(self, decision: ExternalAuthorityDecision) -> None:
        if decision.status in {ExternalActionStatus.BUNDLE_ONLY, ExternalActionStatus.REPORT_ONLY} and (
            decision.write_authorized or decision.submit_receipt
        ):
            raise UnconfiguredExternalWrite(
                "forbidden path unconfigured_external_write: a non-send decision "
                "cannot carry a submit receipt"
            )
        if not decision.write_authorized and decision.submit_receipt is not None:
            raise UnconfiguredExternalWrite(
                "forbidden path unconfigured_external_write: submit receipt exists "
                f"for status {decision.status.value}"
            )

    def record_submission(
        self,
        decision: ExternalAuthorityDecision,
        submission: dict,
    ) -> PostSubmitVerification:
        """Post-submit verification (CE-S11-03): only authorized sends may be
        recorded, the receipt must match the decision, and repeats are
        rejected so a send is never silently duplicated."""
        self.assert_no_unconfigured_write(
            ExternalAuthorityDecision(decision.status, decision.reasons, submit_receipt=submission)
        )
        checks: list[str] = []
        reasons: list[str] = []
        report = decision.report_event or {}
        if submission.get("connector_id") != report.get("connector_id"):
            reasons.append("submission connector_id does not match the approved decision")
        else:
            checks.append("connector_id_matches")
        if submission.get("event_type") != report.get("event_type"):
            reasons.append("submission event_type does not match the approved decision")
        else:
            checks.append("event_type_matches")
        receipt_id = str(submission.get("submission_id") or "").strip()
        if not receipt_id:
            reasons.append("submission receipt requires a submission_id for dedupe")
        else:
            checks.append("submission_id_present")
        if receipt_id and receipt_id in self._seen_submissions:
            reasons.append("duplicate submission receipt; send is idempotent-blocked")
        if not reasons and receipt_id:
            self._seen_submissions[receipt_id] = str(submission.get("connector_id") or "")
        return PostSubmitVerification(not reasons, tuple(checks), tuple(reasons))


__all__ = [
    "AuthorityMode",
    "ConnectorConfig",
    "EvidenceBundle",
    "ExternalActionRequest",
    "ExternalActionStatus",
    "ExternalAuthorityDecision",
    "ExternalAuthorityGovernance",
    "PostSubmitVerification",
    "UnconfiguredExternalWrite",
]
