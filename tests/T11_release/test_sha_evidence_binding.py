import pytest
import os
import subprocess

# ==============================================================================
# T11 - SHA EVIDENCE BINDING & RELEASE AUTHORITY
# ==============================================================================
# Focus: C-Level Evidence Binding. The evidence must be cryptographically
# bound to the exact Git SHA and rejected if HEAD changes.
# ==============================================================================

def test_sha_evidence_binding_rejects_real_stale_head(tmp_path):
    """
    Contract: Create evidence on current SHA. Create a temporary commit.
    Validate evidence against new SHA -> Must Reject.
    Must also check DNA hash, Skill hashes, and manifest.
    """
    try:
        from scp.release.evidence_authority import EvidenceAuthority
    except ImportError:
        pytest.fail("BLOCKED: SCP lacks 'EvidenceAuthority' for C-level SHA binding (R2, R3).")
        
    auth = EvidenceAuthority(repo_path=os.getcwd())
    
    # 1. Capture current HEAD
    current_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    
    # 2. Generate Real Evidence
    evidence_file = tmp_path / "evidence.json"
    auth.generate_evidence(output=str(evidence_file), tested_sha=current_sha)
    
    # 3. Modify Reality (Create a fake commit)
    subprocess.check_call(["git", "commit", "--allow-empty", "-m", "fake commit for T11 test"])
    new_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    
    try:
        # 4. Validation MUST fail
        is_valid = auth.validate_evidence(str(evidence_file), current_head=new_sha)
        assert is_valid is False, "BLOCKED: EvidenceAuthority accepted evidence from a stale SHA (Violates PASS != TRUE)."
    finally:
        # 5. Cleanup the fake commit
        subprocess.check_call(["git", "reset", "--hard", current_sha])
