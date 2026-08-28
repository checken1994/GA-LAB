from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx

from scp import api_server
from scp.security.dos_protection import DoSAlert


def test_api_429_is_boundary_response_with_retry_after(monkeypatch) -> None:
    alert = DoSAlert(
        alert_type="rate_limit",
        severity="critical",
        message="test rate limit",
        action_taken="block",
        status_code=429,
        recommended_headers={"Retry-After": "60"},
    )

    class FakeDos:
        def check_request(self, ip: str):
            return alert

    fake_judge = SimpleNamespace(dos_protection=FakeDos())
    monkeypatch.setattr(api_server, "get_judge", lambda: fake_judge)

    async def call() -> httpx.Response:
        transport = httpx.ASGITransport(app=api_server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/ask",
                json={"question": "boundary rate-limit probe", "session_id": "boundary-429"},
            )

    response = asyncio.run(call())
    assert response.status_code == 429
    assert response.headers["Retry-After"]
    assert response.json()["error"]["type"] == "rate_limit_error"
