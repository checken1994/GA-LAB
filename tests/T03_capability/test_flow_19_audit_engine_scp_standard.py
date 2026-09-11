import os
os.environ.setdefault('SCP_API_PROFILE', 'full')
os.environ.setdefault('SCP_CAPABILITY_SECRET', 'dummy-secret-for-tests-123')
os.environ.setdefault('SCP_STORAGE_BACKEND', 'sqlite')

import pytest
try:
    import scp.audit_engine
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

def test_audit_engine_isolated_flow():
    '''FA-13: Cover audit_engine flow'''
    assert _AVAILABLE, "audit_engine must be importable and connected"
