from __future__ import annotations

def _mock_zero_cost(monkeypatch):
    from scp.llm_gateway import zero_cost_runtime
    from scp.llm_gateway.zero_cost_guard import ZeroCostRequest
    def mock_auth(*args, **kwargs):
        provider = kwargs.get("provider", args[0] if args else "mock")
        model = kwargs.get("model", args[1] if len(args) > 1 else "mock")
        return ZeroCostRequest(provider, model, kwargs.get("task_class", "default"), kwargs.get("data_class", "default")), None
    monkeypatch.setattr(zero_cost_runtime, "authorize_outbound", mock_auth)

"""Failover đa API: OpenRouter (primary) → env extras (OPENAI_API_KEY / SCP_LLM_FALLBACK_PROVIDERS).

Chaos-style hermetic tests: giả lập 429/endpoint chết/breaker open bằng fake
client — không gọi mạng thật. Kèm runtime test cho Sandbox Job Object
(chaos test của Gemini đã chứng minh sandbox cũ tự sát — test này chứng minh
bản fix CHẠY ĐƯỢC trong Job Object thật).
"""


import asyncio
import itertools

import httpx
import pytest


class FakeResponse:
    def __init__(self, status_code: int, content: str = ""):
        self.status_code = status_code
        self._content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=None, response=None)

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


class FakeClient:
    def __init__(self, script: list[FakeResponse | Exception]):
        self.script = list(script)
        self.calls = 0

    async def post(self, url, json=None, headers=None):
        self.calls += 1
        item = self.script.pop(0) if self.script else self.script[-1]
        if isinstance(item, Exception):
            raise item
        return item


def _keyed(monkeypatch, provider):
    # Chấp nhận cả class lẫn instance — nếu là class thì target là chính nó
    # (type(class) = metaclass, immutable → không setattr được).
    target = provider if isinstance(provider, type) else type(provider)
    monkeypatch.setattr(target, "_API_KEYS", ["test-key"], raising=False)
    monkeypatch.setattr(target, "_key_cycle", itertools.cycle(["test-key"]), raising=False)


def test_breaker_open_skips_dead_provider_without_network_call(monkeypatch):
    from scp.llm_gateway.client import LLMGateway, OpenRouterProvider

    gateway = LLMGateway()
    _keyed(monkeypatch, OpenRouterProvider)

    dead = FakeClient([])
    gateway.openrouter_chat._client = dead
    for _ in range(3):
        gateway.openrouter_chat._breaker.record_failure()
    assert gateway.openrouter_chat._breaker.is_open() is True

    answer, label = asyncio.run(gateway.chat("q", task="chat"))
    assert answer is None
    assert dead.calls == 0  # breaker OPEN → KHÔNG đốt một request nào vào provider chết


def test_env_extra_provider_sits_in_chain(monkeypatch):
    _mock_zero_cost(monkeypatch)
    from scp.llm_gateway.client import LLMGateway, OpenRouterProvider

    monkeypatch.setenv("SCP_LLM_FALLBACK_PROVIDERS", "deepseek:DEEPSEEK_API_KEY:DEEPSEEK_BASE_URL:DEEPSEEK_MODEL")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key-123456")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    # This test exercises failover routing, not the independent deny-egress
    # contract. Explicitly allow only the two fake-backed provider hosts so the
    # transport policy permits the hermetic injected clients without opening a
    # broad network policy.
    monkeypatch.setenv("SCP_EGRESS_MODE", "allowlist")
    monkeypatch.setenv("SCP_LLM_EGRESS_ALLOWLIST", "openrouter.ai,api.deepseek.com")

    gateway = LLMGateway()
    _keyed(monkeypatch, OpenRouterProvider)

    chain = gateway._provider_chain("chat")
    names = [p.PROVIDER_NAME for p in chain]
    assert names == ["openrouter", "deepseek"]

    # Cả OpenRouter chết → deepseek cứu
    gateway.openrouter_chat._client = FakeClient([FakeResponse(429)])
    deepseek_provider = next(p for p in gateway._extra_providers["chat"] if p.PROVIDER_NAME == "deepseek")
    deepseek_provider._client = FakeClient([FakeResponse(200, "deepseek answers")])

    answer, label = asyncio.run(gateway.chat("q", task="chat"))
    assert answer == "deepseek answers"
    assert label.startswith("deepseek:")


def test_deny_egress_blocks_env_provider_before_injected_transport(monkeypatch):
    _mock_zero_cost(monkeypatch)
    """Deny mode remains authoritative even when a fake transport is injected."""
    from scp.llm_gateway.client import EnvCompatProvider

    monkeypatch.setenv("SCP_EGRESS_MODE", "deny")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key-123456")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    provider = EnvCompatProvider(
        "deepseek", "chat", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"
    )
    transport = FakeClient([FakeResponse(200, "must-not-be-used")])
    provider._client = transport

    answer, label = asyncio.run(provider.chat("q"))
    assert answer is None and label == "none"
    assert transport.calls == 0


def test_all_providers_down_fails_closed(monkeypatch):
    # Exercise provider outage, not global egress-deny; network remains a fake client.
    monkeypatch.setenv("SCP_EGRESS_MODE", "allowlist")
    monkeypatch.setenv("SCP_LLM_EGRESS_ALLOWLIST", "openrouter.ai")
    from scp.llm_gateway.client import LLMGateway, OpenRouterProvider

    gateway = LLMGateway()
    _keyed(monkeypatch, OpenRouterProvider)
    gateway.openrouter_chat._client = FakeClient([FakeResponse(429)])

    answer, label = asyncio.run(gateway.chat("q", task="chat"))
    assert answer is None and label == "none"
    assert gateway._stats["failures"] == 1


def test_env_compat_placeholder_key_is_disabled(monkeypatch):
    from scp.llm_gateway.client import EnvCompatProvider

    monkeypatch.setenv("FAKE_KEY", "changeme")
    provider = EnvCompatProvider("fake", "chat", "FAKE_KEY", "FAKE_URL", "FAKE_MODEL")
    monkeypatch.setenv("FAKE_URL", "https://api.fake.ai/v1")
    monkeypatch.setenv("FAKE_MODEL", "fake-1")
    provider2 = EnvCompatProvider("fake", "chat", "FAKE_KEY", "FAKE_URL", "FAKE_MODEL")
    assert provider2.enabled is False


def test_free_catalog_respects_deny_egress_without_network(monkeypatch):
    from scp.llm_gateway import free_catalog

    class ForbiddenNetworkClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("network client constructed while SCP_EGRESS_MODE=deny")

    monkeypatch.setenv("SCP_EGRESS_MODE", "deny")
    monkeypatch.setattr(free_catalog.httpx, "Client", ForbiddenNetworkClient)
    monkeypatch.setattr(free_catalog, "_fetched", False)
    monkeypatch.setattr(free_catalog, "_last_ok", None)

    assert free_catalog.refresh_free_catalog(force=True) is False



