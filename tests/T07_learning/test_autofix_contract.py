import pytest
import os
import shutil
import tempfile
from pathlib import Path
from scp.autofix.engine import AutoFixEngine

# ==============================================================================
# T07 - LEARNING / AUTOFIX CONTRACT
# ==============================================================================
# This suite forces the AutoFix Engine to adhere to the Complete SCP Standard:
# 1. Quarantine & Snapshot: Fixes must occur in a bounded sandbox/snapshot first.
# 2. Catastrophic Forgetting Guard: Fixes that break security must be rejected.
# 3. Reversibility: If independent verification fails, the original file remains.
# ==============================================================================

class DummyBugReport:
    def __init__(self, file_path, issue, proposed_fix, degrades_security=False):
        self.file_path = file_path
        self.issue = issue
        self.proposed_fix = proposed_fix
        self.degrades_security = degrades_security

class DummyIndependentVerifier:
    def verify_snapshot(self, snapshot_path):
        # A mock verifier that reads the snapshot and checks for catastrophic forgetting
        content = open(snapshot_path).read()
        if "SECURITY_GUARD_REMOVED" in content:
            return False
        return True

def test_autofix_must_create_snapshot_before_patching(tmp_path):
    """
    Contract: AutoFixEngine must not mutate the target file directly during the
    reasoning/patching phase. It must create a verifiable snapshot.
    """
    target = tmp_path / "app.py"
    target.write_text("def run(): pass\n")
    
    engine = AutoFixEngine(str(tmp_path))
    report = DummyBugReport(str(target), "Missing return", "def run(): return True")
    
    # We expect the engine to have a mechanism to process in quarantine
    # If the engine doesn't have `process_bug_in_sandbox` or similar, this will fail
    # reflecting that the current SCP is lacking the T07 standard.
    if not hasattr(engine, 'process_bug_in_sandbox'):
        pytest.fail("BLOCKED: AutoFixEngine lacks 'process_bug_in_sandbox' required for T07 blast-radius containment.")
        
    sandbox_info = engine.process_bug_in_sandbox(report)
    
    # Target file must remain untouched during sandbox phase
    assert target.read_text() == "def run(): pass\n"
    assert sandbox_info.snapshot_path != str(target)
    assert os.path.exists(sandbox_info.snapshot_path)

def test_autofix_catastrophic_forgetting_guard(tmp_path):
    """
    Contract: An autofix that resolves a bug but removes a security guard must 
    fail the independent verifier and automatically rollback.
    """
    target = tmp_path / "auth.py"
    target.write_text("def login(): check_auth(); return True\n")
    
    engine = AutoFixEngine(str(tmp_path))
    # Malicious fix: fixes something but drops check_auth()
    report = DummyBugReport(str(target), "Fix typo", "def login(): return True", degrades_security=True)
    
    if not hasattr(engine, 'process_and_verify'):
        pytest.fail("BLOCKED: AutoFixEngine lacks 'process_and_verify' for Independent Verifier integration.")
    
    result = engine.process_and_verify(report, verifier=DummyIndependentVerifier())
    
    assert result.status == "REJECTED_BY_VERIFIER"
    assert result.reason == "CATASTROPHIC_FORGETTING"
    
    # Ensure rollback happened
    assert target.read_text() == "def login(): check_auth(); return True\n"
