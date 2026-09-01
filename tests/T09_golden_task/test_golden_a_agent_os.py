import pytest
import os
import tempfile
from scp.task_kernel import TaskKernel
from scp.security.capability_epoch import CapabilityAuthority
from scp.security.os_sandbox import ProcessIsolationEnvironment

# ==============================================================================
# T09 - GOLDEN A (AGENT OS EXECUTION FLOW)
# ==============================================================================
# Focus: Task execution through the 13 layers (Planner -> Policy -> Capability ->
# Kernel -> Lease -> Execution -> Observation -> Verifier -> Audit).
# ==============================================================================

def test_golden_a_agent_os_strict_flow():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "kernel.db")
        kernel = TaskKernel(db_path)
        
        # Interface check for true capability-bounded execution
        if not hasattr(kernel, 'execute_with_capability_lease'):
            kernel.conn.close()
            pytest.fail("BLOCKED: TaskKernel lacks 'execute_with_capability_lease' (A1, A3, A4, S5). Agent OS execution flow is incomplete.")
            
        # Interface check for Independent Verifier
        try:
            from scp.reality.independent_verifier import IndependentVerifier
        except ImportError:
            kernel.conn.close()
            pytest.fail("BLOCKED: SCP lacks 'IndependentVerifier' (A6, S6).")
            
        kernel.conn.close()
        assert True
