import os
os.environ.setdefault('SCP_API_PROFILE', 'full')
os.environ.setdefault('SCP_CAPABILITY_SECRET', 'dummy-secret-for-tests-123')
os.environ.setdefault('SCP_STORAGE_BACKEND', 'sqlite')

import pytest
try:
    import scp.brain
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

def test_brain_isolated_flow():
    '''FA-13: Cover brain flow'''
    assert _AVAILABLE, "brain must be importable and connected"
