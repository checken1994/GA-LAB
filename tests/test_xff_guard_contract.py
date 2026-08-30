import pytest
import os
from fastapi import HTTPException, Request

def test_web_control_xff_guard_rejects_external_ips():
    from scp.api.routes.web_control_routes import _guard
    
    # 1. Simulate a request from a local IP but with an external X-Forwarded-For
    scope_fake_xff = {
        "type": "http",
        "client": ("127.0.0.1", 50000),
        "headers": [
            (b"host", b"127.0.0.1:8000"),
            (b"x-forwarded-for", b"203.0.113.195")
        ]
    }
    req_fake_xff = Request(scope_fake_xff)
    
    # Needs a token if XFF is present, if no token, raises 403
    os.environ["SCP_LOCAL_ONLY"] = "1"
    os.environ["SCP_PC_CONTROLLER_TOKEN"] = "test_token"
    
    with pytest.raises(HTTPException) as exc_info:
        _guard(req_fake_xff, None)
    
    assert exc_info.value.status_code == 403
    
    # 2. Simulate a legitimate local request (no XFF, local client)
    scope_local = {
        "type": "http",
        "client": ("127.0.0.1", 50000),
        "headers": [
            (b"host", b"127.0.0.1:8000")
        ]
    }
    req_local = Request(scope_local)
    
    # Should return silently because is_local=True and XFF=None
    result = _guard(req_local, None)
    assert result is None
