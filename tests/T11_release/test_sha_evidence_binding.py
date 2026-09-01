import pytest

# ==============================================================================
# T11 - SHA EVIDENCE BINDING & RELEASE AUTHORITY
# ==============================================================================
# Focus: Separating Reference Version from Tested SHA.
# Evidence is only valid for the exact SHA it was generated against.
# ==============================================================================

def test_sha_evidence_binding_rejects_stale_head():
    """
    Proves that if HEAD changes, old evidence is strictly invalidated.
    """
    try:
        from scp.release.evidence_authority import EvidenceAuthority
    except ImportError:
        pytest.fail("BLOCKED: SCP lacks 'EvidenceAuthority' for T11 SHA binding (R2, R3).")
        
    auth = EvidenceAuthority()
    
    # Create evidence bound to SHA X
    evidence = auth.create_evidence(tested_sha="commit_X")
    
    # Validate against SHA Y (Head changed)
    is_valid = auth.validate_evidence(evidence, current_head="commit_Y")
    
    assert is_valid is False, "BLOCKED: EvidenceAuthority accepted evidence from a stale SHA (Violates PASS != TRUE)."
