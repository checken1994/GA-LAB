"""Focused contracts for readiness semantics and request metadata redaction."""
from __future__ import annotations

import asyncio
from pathlib import Path

from starlette.requests import Request

from scp.api_server_parts.helpers import _extract_v98_context
from scp.security.request_context import safe_header_metadata


def _request_with_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/ask",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "server": ("127.0.0.1", 8002),
    }
    return Request(scope)


def test_request_context_keeps_fingerprint_but_redacts_credentials() -> None:
    metadata = safe_header_metadata(
        {
            "User-Agent": "SCP-test-client/1.0",
            "Authorization": "Bearer redacted-value",
            "Cookie": "session=redacted-value",
            "X-SCP-PC-Token": "redacted-value",
            "Accept": "application/json",
        }
    )

    assert metadata["headers"] == {"user-agent": "SCP-test-client/1.0"}
    assert metadata["sensitive_headers_present"] is True
    assert "authorization" not in metadata["header_names"]
    assert "cookie" not in metadata["header_names"]
    assert "redacted-value" not in repr(metadata)


def test_v98_context_does_not_forward_raw_sensitive_headers() -> None:
    request = _request_with_headers(
        [
            (b"user-agent", b"SCP-test-client/1.0"),
            (b"authorization", b"Bearer redacted-value"),
            (b"cookie", b"session=redacted-value"),
            (b"x-scp-pc-token", b"redacted-value"),
        ]
    )

    context = _extract_v98_context(request)

    assert context["headers"] == {"user-agent": "SCP-test-client/1.0"}
    assert context["sensitive_headers_present"] is True
    assert "authorization" not in context["header_names"]
    assert "redacted-value" not in repr(context)


def test_openai_compat_context_does_not_forward_raw_sensitive_headers() -> None:
    from scp.api import _shared

    request = _request_with_headers(
        [
            (b"user-agent", b"SCP-compat-client/1.0"),
            (b"authorization", b"Bearer redacted-value"),
            (b"cookie", b"session=redacted-value"),
        ]
    )

    context = _shared._extract_v98_context(request)

    assert context["headers"] == {"user-agent": "SCP-compat-client/1.0"}
    assert context["sensitive_headers_present"] is True
    assert "redacted-value" not in repr(context)


def test_api_readiness_routes_distinguish_liveness_from_judge_readiness() -> None:
    from fastapi.testclient import TestClient
    from scp import api_server

    old_values = {
        "judge_ready": getattr(api_server.app.state, "judge_ready", None),
        "background_scheduler_started": getattr(
            api_server.app.state, "background_scheduler_started", None
        ),
        "readiness_reason": getattr(api_server.app.state, "readiness_reason", None),
    }
    try:
        api_server.app.state.judge_ready = False
        api_server.app.state.background_scheduler_started = False
        api_server.app.state.readiness_reason = "judge_initialization_pending"
        with TestClient(api_server.app) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 503
            assert client.get("/readiness").status_code == 503

            api_server.app.state.judge_ready = True
            api_server.app.state.background_scheduler_started = True
            api_server.app.state.readiness_reason = None
            assert client.get("/ready").status_code == 200
            assert client.get("/readiness").status_code == 200
    finally:
        for key, value in old_values.items():
            setattr(api_server.app.state, key, value)


def test_api_readiness_distinguishes_liveness_from_judge_readiness() -> None:
    from scp import api_server

    old_values = {
        "judge_ready": getattr(api_server.app.state, "judge_ready", None),
        "background_scheduler_started": getattr(
            api_server.app.state, "background_scheduler_started", None
        ),
        "readiness_reason": getattr(api_server.app.state, "readiness_reason", None),
    }
    try:
        api_server.app.state.judge_ready = False
        api_server.app.state.background_scheduler_started = False
        api_server.app.state.readiness_reason = "judge_initialization_pending"
        initializing = asyncio.run(api_server.readiness())
        assert initializing.status_code == 503

        api_server.app.state.judge_ready = True
        api_server.app.state.background_scheduler_started = True
        api_server.app.state.readiness_reason = None
        ready = asyncio.run(api_server.readiness())
        assert ready.status_code == 200
    finally:
        for key, value in old_values.items():
            setattr(api_server.app.state, key, value)


def test_scheduler_exposes_explicit_readiness_aliases() -> None:
    source = Path("mini-services/loop-scheduler/index.ts").read_text(encoding="utf-8")
    assert 'path === "/ready" || path === "/readiness"' in source
    assert 'status: "ready"' in source


def test_context_rag_kernel_disable_is_not_a_legacy_bypass(monkeypatch) -> None:
    from scp import api_server
    from scp.api_server_parts.helpers import AskRequest

    request = AskRequest(question="evidence question", rag_enabled=True)
    monkeypatch.setenv("SCP_ASK_KERNEL_ENABLED", "0")

    assert api_server._ask_is_context_rag(request) is True
    assert api_server._ask_kernel_enabled(request) is False

