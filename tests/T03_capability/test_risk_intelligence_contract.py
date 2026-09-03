import pytest

# ==============================================================================
# T03 - RISK INTELLIGENCE CONTRACT (S10: CE-S10-03 gates [T03,T09],
# CE-S10-04 gates [T03,T09,T11])
# ==============================================================================
# The owner-locked principle: SCP may auto-contain ONLY inside infrastructure
# it actually controls; real-world/public risk demands independent
# verification + evidence-backed alerting + authorized human escalation.
# PR0-PR5 must be graded; post/social volume NEVER decides R4/R5 (1000 copies
# of one source = 1 lineage); Emergency Evidence Bundle replaces bare alarms;
# the Alert Router has NO default broadcast rights.
#
# Status: the risk_intelligence subsystem does not exist in production yet.
# This contract test stays RED as BLOCKED_MISSING_IMPLEMENTATION until the
# authorities below are implemented for real. Stubs are forbidden.
# ==============================================================================

REQUIRED_AUTHORITIES = {
    "risk_classifier": "PR0-PR5 graded verdicts from evidence, not post volume",
    "evidence_bundle": "Emergency Evidence Bundle with independent_lineages, contradictions, unknowns, official_confirmation",
    "alert_router": "CYBER/HEALTH/FIRE/INFRA/INTERNAL routing; not-configured -> bundle only; approval -> WAITING_APPROVAL",
    "incident_state": "OBSERVED..RESOLVED state machine with CONTRADICTED/INSUFFICIENT_EVIDENCE branches",
}


def test_risk_intelligence_authorities_exist_and_obey_the_contract():
    try:
        from scp.risk_intelligence.alert_router import AlertRouter  # noqa: F401
        from scp.risk_intelligence.evidence_bundle import EmergencyEvidenceBundle  # noqa: F401
        from scp.risk_intelligence.incident_state import IncidentStateMachine  # noqa: F401
        from scp.risk_intelligence.risk_classifier import RiskClassifier  # noqa: F401
    except ImportError as exc:
        pytest.fail(
            "PRODUCT_BLOCKED: the S10 Risk Intelligence subsystem is not implemented "
            f"(import failed: {exc}). Required production authorities: {sorted(REQUIRED_AUTHORITIES)}. "
            "Contract each must satisfy once implemented: "
            "(1) RiskClassifier grades PR0-PR5 from independent evidence; syndication "
            "volume alone can never yield PR4/PR5; "
            "(2) containment actions resolve only through CapabilityAuthority over "
            "SCP-owned infrastructure - RiskAuthority must never call tools directly "
            "(forbidden edge RiskAuthority -> Tool); "
            "(3) EmergencyEvidenceBundle carries incident_id, risk_type, location, "
            "independent_lineages, contradictions, unknowns, confidence, "
            "official_confirmation, recommended_actions; "
            "(4) AlertRouter default is REPORT_ONLY/bundle-only; unconfigured channel "
            "never sends; approval-gated channels return WAITING_APPROVAL; no public "
            "broadcast without explicit human authority; "
            "(5) IncidentStateMachine walks OBSERVED->SUSPECTED->CORROBORATING->"
            "CONFIRMED->CONTAINING->ESCALATED->MONITORING->RESOLVED with "
            "CONTRADICTED->CLOSED_FALSE_POSITIVE and INSUFFICIENT_EVIDENCE branches; "
            "(6) false-positive defense: PR4/PR5 requires >=1 official source OR >=2 "
            "truly independent lineages AND freshness AND location validation, except "
            "directly-observed owned sensors; missing-source exception must record "
            "official_confirmation=False."
        )


def test_risk_authority_cannot_hold_default_public_broadcast_capability():
    """Even after implementation, no default Twitter/mass-SMS/emergency-call
    capability may exist in the registry for the risk subsystem."""
    pytest.fail(
        "PRODUCT_BLOCKED: the capability registry contains no explicit deny-record "
        "for public broadcast primitives (post_social/mass_sms/emergency_call) "
        "originating from the risk subsystem. Register the deny-contract in the "
        "capability registry + ActionRegistry so the absence is machine-enforced, "
        "then re-shape this test to probe the registry directly."
    )
