import pytest

# ==============================================================================
# T10 - ADVERSARIAL CHAOS MATRIX
# ==============================================================================
# Focus: Injecting D-level failures at system boundaries to prove recovery.
# ==============================================================================

def test_chaos_matrix_recovers_from_boundary_shatter():
    """
    Simulates crashes at critical boundaries to ensure fail-closed / Reconcile behavior.
    Boundaries:
    1. Scanner crash
    2. Patch generator timeout (WHY provider timeout)
    3. Ledger write fail
    4. Crash post-fix but pre-verify
    5. Crash post-verify but pre-durable reflect
    """
    try:
        from scp.task_kernel import ChaosInjector
    except ImportError:
        pytest.fail("BLOCKED: SCP lacks 'ChaosInjector' for T10 Adversarial bounds testing (A7).")
        
    injector = ChaosInjector()
    
    # Inject ledger write failure
    state = injector.simulate_crash(at_boundary="PRE_LEDGER_WRITE")
    assert state == "RECONCILING", "Failure: System did not enter RECONCILING state after ledger crash."
    
    # Inject post-fix pre-verify crash
    state = injector.simulate_crash(at_boundary="POST_FIX_PRE_VERIFY")
    assert state == "ROLLBACK_PENDING", "Failure: System did not queue rollback for unverified fix crash."
