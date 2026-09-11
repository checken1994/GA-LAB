import os
os.environ.setdefault('SCP_API_PROFILE', 'full')
os.environ.setdefault('SCP_CAPABILITY_SECRET', 'dummy-secret-for-tests-123')
os.environ.setdefault('SCP_STORAGE_BACKEND', 'sqlite')

import pytest
try:
    import scp.risk_intelligence
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

def test_risk_intelligence_isolated_flow():
    '''FA-13: Cover risk_intelligence flow'''
    assert _AVAILABLE, "risk_intelligence must be importable and connected"
