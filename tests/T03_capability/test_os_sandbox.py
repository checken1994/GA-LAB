import pytest
import platform
import tempfile
import os
from scp.security.os_sandbox import ProcessIsolationEnvironment, isolation_capability
from scp.security.capability_epoch import CapabilityAuthority, CapabilityToken

def test_sandbox_executes_command_inside_job_object():
    if platform.system() != "Windows":
        pytest.skip("Job Object sandbox is Windows-specific")
    assert isolation_capability()["job_object"] is True, "pywin32 must be present"
    with tempfile.TemporaryDirectory() as tmp:
        authority = CapabilityAuthority(state_path=os.path.join(tmp, "caps.sqlite3"))
        token = authority.issue("sandbox-verify")
        pie = ProcessIsolationEnvironment(authority)
        result = pie.execute_bounded(token, ["cmd", "/c", "echo", "alive-in-job-object"])
        assert result.returncode == 0
        assert "alive-in-job-object" in result.stdout

def test_sandbox_rejects_invalid_capability():
    if platform.system() != "Windows":
        pytest.skip("Job Object sandbox is Windows-specific")
    with tempfile.TemporaryDirectory() as tmp:
        authority = CapabilityAuthority(state_path=os.path.join(tmp, "caps.sqlite3"))
        pie = ProcessIsolationEnvironment(authority)
        forged = CapabilityToken(subject="intruder", epoch=999, token_id="fake", issued_at=0.0)
        with pytest.raises(PermissionError):
            pie.execute_bounded(forged, ["cmd", "/c", "echo", "should-not-run"])
