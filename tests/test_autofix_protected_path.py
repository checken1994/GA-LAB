import pytest
from unittest.mock import patch
from scp.autofix.runner import run_once
from scp.autofix.classifier import BugReport, BugTier

class DummyWhyResult:
    allowed = True

@patch("scp.meta.why_gate.WhyGate.gate")
def test_autofix_protected_path_blocked(mock_gate):
    mock_gate.return_value = DummyWhyResult()
    
    bug = BugReport(
        file='scp/autofix/policy_gate.py',
        line=1,
        bug_type='test_bug',
        description='Test bug',
        suggested_fix='<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE',
        tier=BugTier.TIER_1_AUTO_FIX
    )
    summary = run_once(bugs=[bug], deterministic_only=False)
    
    assert len(summary['details']) == 1
    assert summary['details'][0]['result']['action'] == 'protected_path_blocked'
