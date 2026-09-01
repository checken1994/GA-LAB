import pytest
import os
import json

# ==============================================================================
# T07 - EPISTEMIC MISSING-PIECE DISCOVERY
# ==============================================================================
# Focus: SCP must not overclaim ("no bugs found" != "no bugs exist").
# It must publish its blind spots, and when a Reality event (e.g. independent E2E test)
# contradicts its findings, SCP must generate a MissingPieceFinding, not hallucinate.
# ==============================================================================

def test_epistemic_boundary_and_reality_contradiction():
    """
    Contract: When Scanner scans a workspace and finds nothing, it MUST return
    a coverage claim outlining its limits. If Reality proves a bug exists,
    SCP must update its method via a MissingPieceFinding.
    """
    try:
        from scp.knowledge.epistemic_scanner import EpistemicScanner
        from scp.reality.independent_verifier import IndependentVerifier
    except ImportError:
        pytest.fail("BLOCKED: SCP lacks 'EpistemicScanner' and 'IndependentVerifier' (E2, R4). SCP cannot yet recognize its own blind spots.")
        
    scanner = EpistemicScanner()
    
    # Scanner scans and misses an unknown bug class
    findings, coverage_claim = scanner.scan("dummy_workspace")
    assert len(findings) == 0
    assert "eval_input" not in coverage_claim.known_patterns, "Scanner overclaimed knowing an unknown bug class."
    
    # Reality test fails
    verifier = IndependentVerifier()
    reality_result = verifier.run_reality_check("dummy_workspace")
    assert reality_result.passed is False
    
    # SCP must reconcile the contradiction and discover the missing piece
    missing_piece = scanner.reconcile_contradiction(reality_result)
    assert missing_piece is not None
    assert missing_piece.type == "OBSERVATION_BLIND_SPOT"
