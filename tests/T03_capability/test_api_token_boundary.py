import pytest
import os
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from scp.api.routes import pc_controller_routes, hands_routes, web_control_routes

@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setenv("SCP_PC_CONTROLLER_TOKEN", "strict_test_token")
    app = FastAPI()
    
    # Middleware to mock client as 127.0.0.1
    @app.middleware("http")
    async def mock_ip(request: Request, call_next):
        request.scope["client"] = ("127.0.0.1", 12345)
        return await call_next(request)
        
    app.include_router(pc_controller_routes.router)
    app.include_router(hands_routes.router)
    app.include_router(web_control_routes.router)
    return TestClient(app)

def test_localhost_requires_token_pc_kill(api_client):
    # Without token -> 403
    resp = api_client.post("/v3/pc/kill", json={"reason": "test"}, headers={})
    assert resp.status_code == 403, "Localhost bypass allowed on /v3/pc/kill"
    
    # With valid token -> 200
    resp = api_client.post("/v3/pc/kill", json={"reason": "test"}, headers={"X-SCP-PC-Token": "strict_test_token"})
    assert resp.status_code == 200
    
    # Clean up global state
    import shutil
    from pathlib import Path
    data_dir = Path(__file__).resolve().parents[2] / "data" / "pc_controller"
    kill_switch_path = data_dir / "KILL_SWITCH"
    if kill_switch_path.exists():
        kill_switch_path.unlink()

def test_localhost_requires_token_hands_status(api_client):
    # Without token -> 403
    resp = api_client.get("/v3/hands/status", headers={})
    assert resp.status_code == 403, f"Localhost bypass allowed on /v3/hands/status. Got {resp.status_code}"

def test_localhost_requires_token_web_status(api_client):
    # Without token -> 403
    resp = api_client.get("/v3/web/status", headers={})
    assert resp.status_code == 403, f"Localhost bypass allowed on /v3/web/status. Got {resp.status_code}"
