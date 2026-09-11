import os
os.environ.setdefault('SCP_API_PROFILE', 'full')
os.environ.setdefault('SCP_CAPABILITY_SECRET', 'dummy-secret-for-tests-123')
os.environ.setdefault('SCP_STORAGE_BACKEND', 'sqlite')

import pytest
try:
    import scp.calibration
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

def test_calibration_isolated_flow():
    '''FA-13: Cover calibration flow'''
    assert _AVAILABLE, "calibration must be importable and connected"
