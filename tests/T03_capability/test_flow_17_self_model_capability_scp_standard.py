import os
os.environ.setdefault('SCP_API_PROFILE', 'full')
os.environ.setdefault('SCP_CAPABILITY_SECRET', 'dummy-secret-for-tests-123')
os.environ.setdefault('SCP_STORAGE_BACKEND', 'sqlite')

import pytest
from fastapi.testclient import TestClient
from scp.api_server import app

client = TestClient(app)

def test_v106_capabilities_recompute():
    '''FA-13: Cover Self Model capability recomputation'''
    resp = client.get('/v106/capabilities/intelligence.zero_cost')
    assert resp.status_code == 200
    data = resp.json()
    assert 'status' in data
    assert 'maturity' in data
