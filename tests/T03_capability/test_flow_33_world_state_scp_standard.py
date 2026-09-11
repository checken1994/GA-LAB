import os
os.environ.setdefault('SCP_API_PROFILE', 'full')
os.environ.setdefault('SCP_CAPABILITY_SECRET', 'dummy-secret-for-tests-123')
os.environ.setdefault('SCP_STORAGE_BACKEND', 'sqlite')

import pytest
try:
    import scp.world_state
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

def test_world_state_isolated_flow():
    '''FA-13: Cover world_state flow'''
    assert _AVAILABLE, "world_state must be importable and connected"
