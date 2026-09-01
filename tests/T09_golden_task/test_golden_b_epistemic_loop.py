import pytest
import os

# ==============================================================================
# T09 - GOLDEN B (SCP SELF-IMPROVEMENT EPISTEMIC LOOP)
# ==============================================================================
# Focus: Anomaly -> WHY -> Scan -> Propose -> Snapshot -> Apply ->
# Reality Verify -> Commit/Rollback. Must be C-level (real state changes).
# ==============================================================================

def test_golden_b_epistemic_self_improvement_loop(tmp_path):
    """
    Contract: SCP must execute a real self-improvement loop.
    It must discover a bug, patch it in a sandbox, run reality verification,
    and then commit or rollback based on the independent verifier.
    """
    workspace = tmp_path / "app"
    workspace.mkdir()
    buggy_file = workspace / "logic.py"
    buggy_file.write_text("def auth():\n  return False\n")
    
    try:
        from scp.epistemic_loop import SelfImprovementEngine
        engine = SelfImprovementEngine(str(workspace))
        
        # Real execution flow
        finding = engine.scan_and_find_anomaly()
        assert finding is not None, "Failed to find anomaly."
        
        patch_proposal = engine.propose_fix(finding)
        
        # Snapshot and apply
        snapshot_id = engine.create_snapshot_quarantine()
        engine.apply_candidate(patch_proposal)
        
        # Reality Verify
        from scp.reality.independent_verifier import IndependentVerifier
        verifier = IndependentVerifier()
        is_fixed = verifier.run_reality_check(str(workspace))
        
        if is_fixed:
            engine.commit_to_durable_knowledge()
        else:
            engine.rollback(snapshot_id)
            
        assert "def auth():\n  return True\n" in buggy_file.read_text() or not is_fixed
        
    except ImportError:
        pytest.fail("BLOCKED: SCP lacks 'SelfImprovementEngine' and 'IndependentVerifier' for Golden B C-level flow.")
    except AttributeError as e:
        pytest.fail(f"BLOCKED: Self-Improvement API incomplete: {e}")
