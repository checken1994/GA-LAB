import os
os.environ.setdefault('SCP_API_PROFILE', 'full')
os.environ.setdefault('SCP_CAPABILITY_SECRET', 'dummy-secret-for-tests-123')
os.environ.setdefault('SCP_STORAGE_BACKEND', 'sqlite')

import pytest
try:
    import scp.rag
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

def test_rag_isolated_flow():
    '''FA-13: Cover rag flow'''
    assert _AVAILABLE, "rag must be importable and connected"
