import asyncio
import itertools

import pytest

from scp.llm_gateway.client import LLMGateway, OpenRouterProvider


@pytest.fixture
def configured_openrouter(monkeypatch):
    # Synthetic non-secret values only; no network call is made.
    monkeypatch.setattr(OpenRouterProvider, "_API_KEYS", ["test-key-a", "test-key-b"])
    monkeypatch.setattr(
        OpenRouterProvider,
        "_key_cycle",
        itertools.cycle(["test-key-a", "test-key-b"]),
    )


def test_openrouter_429_moves_from_paid_to_task_free(configured_openrouter) -> None:
    async def scenario() -> tuple[str | None, str, list[str]]:
        provider = OpenRouterProvider(task="default")
        provider.model = "paid-model"
        provider.free_fallback = "free-model"
        calls: list[str] = []

        async def fake_call(model, messages, api_key):
            calls.append(model)
            if model == "paid-model":
                return None, "HTTP 429 (quota/rate-limit)"
            return "fallback answer", None

        provider._call_model = fake_call  # type: ignore[method-assign]
        answer, returned_provider = await provider.chat("question")
        return answer, returned_provider, calls

    answer, returned_provider, calls = asyncio.run(scenario())
    assert answer == "fallback answer"
    assert returned_provider == "openrouter:free-model"
    assert calls == ["paid-model", "paid-model", "free-model"]


def test_openrouter_402_moves_to_auto_router_when_task_free_fails(
    configured_openrouter,
) -> None:
    async def scenario() -> tuple[str | None, str, list[str]]:
        provider = OpenRouterProvider(task="default")
        provider.model = "paid-model"
        provider.free_fallback = "free-model"
        calls: list[str] = []

        async def fake_call(model, messages, api_key):
            calls.append(model)
            if model == "paid-model":
                return None, "HTTP 402 (quota/rate-limit)"
            if model == "free-model":
                return None, "HTTP 500"
            return "router answer", None

        provider._call_model = fake_call  # type: ignore[method-assign]
        answer, returned_provider = await provider.chat("question")
        return answer, returned_provider, calls

    answer, returned_provider, calls = asyncio.run(scenario())
    assert answer == "router answer"
    assert returned_provider == "openrouter:openrouter/free"
    assert calls == ["paid-model", "paid-model", "free-model", "openrouter/free"]


def test_openrouter_disabled_or_exhausted_returns_none(configured_openrouter) -> None:
    async def scenario() -> tuple[tuple[str | None, str], tuple[str | None, str]]:
        disabled = OpenRouterProvider(task="default")
        disabled._API_KEYS = []
        disabled._key_cycle = None
        disabled_result = await disabled.chat("question")

        exhausted = OpenRouterProvider(task="default")
        exhausted.model = "paid-model"
        exhausted.free_fallback = "free-model"

        async def fail(model, messages, api_key):
            return None, "timeout"

        exhausted._call_model = fail  # type: ignore[method-assign]
        exhausted_result = await exhausted.chat("question")
        return disabled_result, exhausted_result

    disabled_result, exhausted_result = asyncio.run(scenario())
    assert disabled_result == (None, "none")
    assert exhausted_result == (None, "none")


def test_gateway_returns_none_when_ollama_and_openrouter_fail(monkeypatch) -> None:
    class FailingProvider:
        enabled = True
        model = "synthetic"

        async def chat(self, question, context, system_prompt):
            return None, "none"

        def stats(self):
            return {"enabled": True, "model": self.model}

    gateway = LLMGateway()
    gateway.ollama_default = FailingProvider()
    gateway.openrouter_default = FailingProvider()
    gateway.openrouter = gateway.openrouter_default
    monkeypatch.setenv("SCP_LLM_PROVIDER_MODE", "auto")

    answer, provider = asyncio.run(gateway.chat("question", task="default"))
    assert answer is None
    assert provider == "none"
    assert gateway.stats()["failures"] == 1
