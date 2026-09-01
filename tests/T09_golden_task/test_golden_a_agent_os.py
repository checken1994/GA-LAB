import pytest
import os
import tempfile
from scp.task_kernel import TaskKernel

# ==============================================================================
# T09 - GOLDEN A (AGENT OS EXECUTION FLOW)
# ==============================================================================
# Focus: Task execution through the 13 layers.
# MUST act on real post-state, not just `assert True`
# ==============================================================================

def test_golden_a_agent_os_strict_flow():
    """
    Contract: A full execution flow must create a task, issue a capability,
    execute bounded, observe real state, and persist evidence.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "kernel.db")
        
        try:
            from scp.core.capability_token import CapabilityManager
            from scp.reality.independent_verifier import IndependentVerifier
            kernel = TaskKernel(db_path)
            
            # Initiate flow
            task_id = kernel.create_task("test_write")
            cap_manager = CapabilityManager()
            token = cap_manager.issue_token("write_file", tmp)
            
            # Execute bounded action (MUST modify real filesystem)
            target_file = os.path.join(tmp, "artifact.txt")
            success = kernel.execute_with_capability_lease(task_id, token, lambda: open(target_file, "w").write("real_state"))
            
            # Observation and Verification
            verifier = IndependentVerifier()
            evidence = verifier.verify_file_exists(target_file)
            
            # Persistence
            kernel.persist_evidence(task_id, evidence)
            
            # Assertion MUST be on the post-state
            assert os.path.exists(target_file), "Agent OS failed to modify reality."
            assert evidence.is_valid, "Evidence verification failed."
            
        except ImportError:
            pytest.fail("BLOCKED: Missing Agent OS components (TaskKernel capabilities, IndependentVerifier, CapabilityManager).")
        except AttributeError as e:
            pytest.fail(f"BLOCKED: Agent OS API incomplete: {e}")
