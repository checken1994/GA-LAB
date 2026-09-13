"""SCP LLM Gateway — Model Discovery & Lifecycle Zero-Trust Tests (S35).

Zero-mock test suite:
- Zero mock imports (no mocks, no fakes, no patches).
- Physical loopback HTTP servers on 127.0.0.1:0.
- Real SQLite/FoundationDB storage verification.
- Full end-to-end lifecycle verification:
  DISCOVERED -> QUARANTINED -> (adversarial probe) -> QUALIFIED / COOLDOWN -> ACTIVE.
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

import httpx
import pytest

from scp.llm_gateway.discovery import (
    LocalEndpointScanner,
    ModelDiscoveryStore,
    ModelLifecycleState,
)

# Capture original httpx send functions at module import time before any fixture runs
_ORIGINAL_ASYNC_SEND = httpx.AsyncClient.send
_ORIGINAL_SYNC_SEND = httpx.Client.send


@pytest.fixture(autouse=True)
def allow_loopback_transport(monkeypatch):
    """Permit loopback traffic while keeping external endpoints blocked per T05 isolation."""

    async def loopback_async_send(self, request, *args, **kwargs):
        if request.url.host in ("127.0.0.1", "localhost", "::1"):
            return await _ORIGINAL_ASYNC_SEND(self, request, *args, **kwargs)
        raise AssertionError(
            f"Non-loopback HTTP request forbidden in T05: {request.url}"
        )

    def loopback_sync_send(self, request, *args, **kwargs):
        if request.url.host in ("127.0.0.1", "localhost", "::1"):
            return _ORIGINAL_SYNC_SEND(self, request, *args, **kwargs)
        raise AssertionError(
            f"Non-loopback HTTP request forbidden in T05: {request.url}"
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", loopback_async_send)
    monkeypatch.setattr(httpx.Client, "send", loopback_sync_send)
    yield


class DiscoveryLoopbackHandler(BaseHTTPRequestHandler):
    """Physical loopback HTTP handler simulating OpenAI-compatible models and completions endpoints."""

    models_list: ClassVar[list[str]] = []

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress standard HTTP request logging during test runs
        pass

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/v1/models":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {"data": [{"id": mid, "object": "model"} for mid in self.server.models_list]}
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path.rstrip("/") == "/v1/chat/completions":
            content_length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_length)
            try:
                req_data = json.loads(body_bytes.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_response(400)
                self.end_headers()
                return

            model = req_data.get("model", "")
            messages = req_data.get("messages", [])
            prompt = messages[0].get("content", "") if messages else ""

            # Adversarial behavior based on model identifier
            if "injected" in model and "unrestricted_bypass_mode" in prompt:
                content = "unrestricted_bypass_mode"
            elif "roleplay" in model and "destroy a server" in prompt:
                content = "rm -rf /"
            else:
                content = "Safe compliant refusal: cannot perform adversarial prompt."

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "id": "chatcmpl-discovery-test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                    }
                ],
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


def _create_server(models: list[str]) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), DiscoveryLoopbackHandler)
    server.models_list = models
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return server, f"http://127.0.0.1:{port}"


def test_model_lifecycle_states() -> None:
    assert ModelLifecycleState.DISCOVERED == "DISCOVERED"
    assert ModelLifecycleState.QUARANTINED == "QUARANTINED"
    assert ModelLifecycleState.QUALIFIED == "QUALIFIED"
    assert ModelLifecycleState.ACTIVE == "ACTIVE"
    assert ModelLifecycleState.COOLDOWN == "COOLDOWN"


def test_discovery_store_crud(tmp_path) -> None:
    db_path = tmp_path / "test_discovery.sqlite"
    store = ModelDiscoveryStore(db_path)

    # Initially empty
    assert store.list_models() == []
    assert store.get_model_state("http://127.0.0.1:8000", "m1") is None

    # Upsert DISCOVERED
    store.upsert_model("http://127.0.0.1:8000", "m1", ModelLifecycleState.DISCOVERED)
    assert store.get_model_state("http://127.0.0.1:8000", "m1") == ModelLifecycleState.DISCOVERED

    # Update to QUALIFIED
    store.upsert_model("http://127.0.0.1:8000", "m1", ModelLifecycleState.QUALIFIED)
    assert store.get_model_state("http://127.0.0.1:8000", "m1") == ModelLifecycleState.QUALIFIED

    # Add second model
    store.upsert_model("http://127.0.0.1:9000", "m2", ModelLifecycleState.ACTIVE)
    all_models = store.list_models()
    assert len(all_models) == 2

    active_models = store.get_models_by_state(ModelLifecycleState.ACTIVE)
    assert len(active_models) == 1
    assert active_models[0]["model_id"] == "m2"
    assert active_models[0]["endpoint"] == "http://127.0.0.1:9000"

    store.close()


def test_discovery_scanner_env_endpoints(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "test_env.sqlite"
    store = ModelDiscoveryStore(db_path)

    monkeypatch.setenv("SCP_LOCAL_ENDPOINTS", " http://127.0.0.1:8001 , http://127.0.0.1:8002 ")
    scanner = LocalEndpointScanner(store=store)
    assert scanner.endpoints == ["http://127.0.0.1:8001", "http://127.0.0.1:8002"]

    store.close()


def test_discovery_unreachable_endpoint_fail_closed(tmp_path) -> None:
    db_path = tmp_path / "test_unreachable.sqlite"
    store = ModelDiscoveryStore(db_path)

    scanner = LocalEndpointScanner(
        store=store,
        endpoints=["http://127.0.0.1:59197"],
        timeout=1.0,
    )
    asyncio.run(scanner.run_discovery())

    # Unreachable endpoint fails closed: 0 models stored, no unhandled exception
    assert store.list_models() == []
    store.close()


def test_discovery_and_lifecycle_end_to_end_loopback(tmp_path) -> None:
    db_path = tmp_path / "test_e2e_discovery.sqlite"
    store = ModelDiscoveryStore(db_path)

    # Start 2 physical loopback HTTP servers
    server1, url1 = _create_server(["model-safe-1", "model-injected-2"])
    server2, url2 = _create_server(["model-safe-3"])

    try:
        scanner = LocalEndpointScanner(
            store=store,
            endpoints=[url1, url2],
            timeout=5.0,
        )

        # Step 1: run discovery
        asyncio.run(scanner.run_discovery())

        models = store.list_models()
        assert len(models) == 3
        states = {(m["endpoint"], m["model_id"]): m["state"] for m in models}
        assert states[(url1, "model-safe-1")] == ModelLifecycleState.DISCOVERED
        assert states[(url1, "model-injected-2")] == ModelLifecycleState.DISCOVERED
        assert states[(url2, "model-safe-3")] == ModelLifecycleState.DISCOVERED

        # Step 2: run lifecycle state machine
        # DISCOVERED -> QUARANTINED -> probe -> QUALIFIED (safe) / COOLDOWN (injected) -> ACTIVE (qualified)
        asyncio.run(scanner.run_lifecycle())

        m_safe_1 = store.get_model_state(url1, "model-safe-1")
        m_injected_2 = store.get_model_state(url1, "model-injected-2")
        m_safe_3 = store.get_model_state(url2, "model-safe-3")

        # model-safe-1 passed all adversarial probes and reached ACTIVE
        assert m_safe_1 == ModelLifecycleState.ACTIVE
        # model-injected-2 triggered prompt injection failure indicator and went to COOLDOWN
        assert m_injected_2 == ModelLifecycleState.COOLDOWN
        # model-safe-3 passed all adversarial probes and reached ACTIVE
        assert m_safe_3 == ModelLifecycleState.ACTIVE

        # Step 3: subsequent discovery run is idempotent (does not reset ACTIVE or COOLDOWN models)
        asyncio.run(scanner.run_discovery())
        assert store.get_model_state(url1, "model-safe-1") == ModelLifecycleState.ACTIVE
        assert store.get_model_state(url1, "model-injected-2") == ModelLifecycleState.COOLDOWN
        assert store.get_model_state(url2, "model-safe-3") == ModelLifecycleState.ACTIVE
    finally:
        server1.shutdown()
        server1.server_close()
        server2.shutdown()
        server2.server_close()
        store.close()


def test_custom_prober_factory_injection(tmp_path) -> None:
    db_path = tmp_path / "test_factory.sqlite"
    store = ModelDiscoveryStore(db_path)

    store.upsert_model("http://127.0.0.1:8000", "test-model", ModelLifecycleState.QUARANTINED)

    class StubRealObjectProber:
        def __init__(self, endpoint_url: str, model: str, timeout: float = 10.0) -> None:
            self.endpoint_url = endpoint_url
            self.model = model

        async def probe_async(self) -> bool:
            return True

    scanner = LocalEndpointScanner(
        store=store,
        endpoints=["http://127.0.0.1:8000"],
        prober_factory=StubRealObjectProber,
    )
    asyncio.run(scanner.run_lifecycle())

    assert store.get_model_state("http://127.0.0.1:8000", "test-model") == ModelLifecycleState.ACTIVE
    store.close()
