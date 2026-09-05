from __future__ import annotations

import asyncio
import itertools
from pathlib import Path

from scp.llm_gateway.zero_cost_guard import ZeroCostDecision, ZeroCostDenied, ZeroCostRequest


def _configure_openrouter(monkeypatch, provider_cls) -> None:
    monkeypatch.setattr(provider_cls, "_API_KEYS", ["test-key"], raising=False)
    monkeypatch.setattr(provider_cls, "_key_cycle", itertools.cycle(["test-key"]), raising=False)
    monkeypatch.setattr(provider_cls, "_dynamic_models_loaded", True, raising=False)


def test_structured_vision_messages_are_denied_before_transport_without_price_authority(monkeypatch):
    from scp.llm_gateway import zero_cost_runtime
    from scp.llm_gateway.client import OpenRouterProvider

    _configure_openrouter(monkeypatch, OpenRouterProvider)
    provider = OpenRouterProvider(task="vision")
    calls = 0

    async def forbidden_transport(*args, **kwargs):
        nonlocal calls
        calls += 1
        return "should-not-run", None

    def deny(*, provider, model, task_class, data_class):
        raise ZeroCostDenied(ZeroCostDecision.DENY_UNKNOWN_PRICE)

    monkeypatch.setattr(zero_cost_runtime, "authorize_outbound", deny)
    monkeypatch.setattr(provider, "_call_model", forbidden_transport)

    messages = [{"role": "user", "content": [{"type": "text", "text": "describe"}]}]
    answer, label = asyncio.run(provider.chat_messages(messages, data_class="INTERNAL"))

    assert answer is None
    assert label == "blocked_zero_cost_proof"
    assert calls == 0


def test_structured_vision_messages_reach_transport_only_after_authorization(monkeypatch):
    from scp.llm_gateway import zero_cost_runtime
    from scp.llm_gateway.client import OpenRouterProvider

    _configure_openrouter(monkeypatch, OpenRouterProvider)
    provider = OpenRouterProvider(task="vision")
    seen = []

    def allow(*, provider, model, task_class, data_class):
        seen.append((provider, model, task_class, str(data_class)))
        return ZeroCostRequest(provider, model, task_class, data_class), None

    async def transport(model, messages, api_key):
        assert messages[0]["role"] == "user"
        return "observed image", None

    monkeypatch.setattr(zero_cost_runtime, "authorize_outbound", allow)
    monkeypatch.setattr(provider, "_call_model", transport)

    answer, label = asyncio.run(
        provider.chat_messages(
            [{"role": "user", "content": [{"type": "text", "text": "describe"}]}],
            data_class="INTERNAL",
        )
    )

    assert answer == "observed image"
    assert label.startswith("openrouter:")
    assert seen
    assert all(item[2] == "vision" for item in seen)


def test_vision_handler_uses_canonical_gateway_and_marks_output_as_observation():
    from scp.capabilities.vision import VisionHandler

    class Gateway:
        def __init__(self):
            self.messages = None

        async def chat_messages(self, messages, *, task, data_class):
            self.messages = messages
            assert task == "vision"
            assert data_class == "INTERNAL"
            return "a small red square", "fixture:free-vlm"

    gateway = Gateway()
    handler = VisionHandler(gateway=gateway)
    observation = asyncio.run(
        handler.observe_image(b"\x89PNG\r\nfixture", "What is visible?", mime_type="image/png")
    )

    assert observation is not None
    assert observation.description == "a small red square"
    assert observation.epistemic_role == "OBSERVATION"
    assert gateway.messages[1]["content"][1]["type"] == "image_url"
    assert gateway.messages[1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")

    source = (Path(__file__).resolve().parents[2] / "scp" / "capabilities" / "vision.py").read_text(encoding="utf-8")
    assert "127.0.0.1:11434" not in source
    assert "urllib.request" not in source
    assert "chat_messages" in source
