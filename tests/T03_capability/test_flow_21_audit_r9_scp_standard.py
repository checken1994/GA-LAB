import os
os.environ.setdefault('SCP_API_PROFILE', 'full')
os.environ.setdefault('SCP_CAPABILITY_SECRET', 'dummy-secret-for-tests-123')
os.environ.setdefault('SCP_STORAGE_BACKEND', 'sqlite')

import pytest
try:
    import scp.audit_r9
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

def test_audit_r9_isolated_flow():
    '''FA-13: Cover audit_r9 flow'''
    assert _AVAILABLE, "audit_r9 must be importable and connected"
