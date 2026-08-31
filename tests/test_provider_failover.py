"""Failover đa API: OpenRouter (primary) → env extras → Groq (fallback).

Chaos-style hermetic tests: giả lập 429/endpoint chết/breaker open bằng fake
client — không gọi mạng thật. Kèm runtime test cho Sandbox Job Object
(chaos test của Gemini đã chứng minh sandbox cũ tự sát — test này chứng minh
bản fix CHẠY ĐƯỢC trong Job Object thật).
"""
from __future__ import annotations

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
    from scp.llm_gateway.client import LLMGateway, OpenRouterProvider

    monkeypatch.setenv("SCP_LLM_FALLBACK_PROVIDERS", "deepseek:DEEPSEEK_API_KEY:DEEPSEEK_BASE_URL:DEEPSEEK_MODEL")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key-123456")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")

    gateway = LLMGateway()
    _keyed(monkeypatch, OpenRouterProvider)

    chain = gateway._provider_chain("chat")
    names = [p.PROVIDER_NAME for p in chain]
    assert names == ["openrouter", "deepseek", "groq"]

    # Cả OpenRouter lẫn Groq chết → deepseek cứu
    gateway.openrouter_chat._client = FakeClient([FakeResponse(429)])
    gateway._extra_providers["chat"][0]._client = FakeClient([FakeResponse(200, "deepseek answers")])

    answer, label = asyncio.run(gateway.chat("q", task="chat"))
    assert answer == "deepseek answers"
    assert label.startswith("deepseek:")


def test_all_providers_down_fails_closed(monkeypatch):
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


# ---------------------------------------------------------------------------
# Sandbox Job Object — chaos test của Gemini đã chứng minh bản cũ tự sát
# (ResumeThread với PROCESS handle). Bản fix phải chạy được THẬT trên Windows.
# ---------------------------------------------------------------------------
def test_sandbox_executes_command_inside_job_object():
    import platform

    if platform.system() != "Windows":
        pytest.skip("Job Object sandbox is Windows-specific")
    import tempfile, os
    from scp.security.os_sandbox import ProcessIsolationEnvironment, isolation_capability
    from scp.security.capability_epoch import CapabilityAuthority

    assert isolation_capability()["job_object"] is True, "pywin32 phải có để test này chạy"

    with tempfile.TemporaryDirectory() as tmp:
        authority = CapabilityAuthority(state_path=os.path.join(tmp, "caps.sqlite3"))
        token = authority.issue("sandbox-verify")
        pie = ProcessIsolationEnvironment(authority)
        result = pie.execute_bounded(token, ["cmd", "/c", "echo", "alive-in-job-object"])
        assert result.returncode == 0
        assert "alive-in-job-object" in result.stdout


def test_sandbox_rejects_invalid_capability():
    import platform

    if platform.system() != "Windows":
        pytest.skip("Job Object sandbox is Windows-specific")
    import tempfile, os
    from scp.security.os_sandbox import ProcessIsolationEnvironment
    from scp.security.capability_epoch import CapabilityAuthority, CapabilityToken

    with tempfile.TemporaryDirectory() as tmp:
        authority = CapabilityAuthority(state_path=os.path.join(tmp, "caps.sqlite3"))
        pie = ProcessIsolationEnvironment(authority)
        forged = CapabilityToken(subject="intruder", epoch=999, token_id="fake", issued_at=0.0)
        with pytest.raises(PermissionError):
            pie.execute_bounded(forged, ["cmd", "/c", "echo", "should-not-run"])
