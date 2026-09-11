import os
os.environ.setdefault('SCP_API_PROFILE', 'full')
os.environ.setdefault('SCP_CAPABILITY_SECRET', 'dummy-secret-for-tests-123')
os.environ.setdefault('SCP_STORAGE_BACKEND', 'sqlite')

import pytest
from fastapi.testclient import TestClient
from scp.api_server import app

client = TestClient(app)

def test_swe_bench_compat():
    '''FA-13: Cover SWE-Bench compatibility route'''
    payload = {
        "model": "scp-agent",
        "messages": [{"role": "user", "content": "hello"}]
    }
    resp = client.post('/swe-bench/v1/chat/completions', json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "scp-agent"
    assert data["choices"][0]["message"]["content"] == "Function execution deferred to agent loop."
