from __future__ import annotations

import asyncio

from scp.llm_gateway.client import OpenRouterProvider


def test_openrouter_timeout_recovers_via_configured_fallback() -> None:
    """The contract is recovery via the provider's configured fallback.

    A concrete model name is deployment data, not a runtime invariant. This
    test follows the production provider object so a model rotation cannot make
    CI red while failover behavior remains correct.
    """

    async def actual() -> tuple[list[str], str | None, str, str, str]:
        provider = OpenRouterProvider(task="judge")
        provider._API_KEYS = ["test-key"]
        provider._next_key = lambda: "test-key"  # type: ignore[method-assign]
        calls: list[str] = []
        paid_model = provider.model
        fallback_model = provider.free_fallback

        async def fake_call(model: str, messages: list[dict], api_key: str):
            calls.append(model)
            if model == paid_model:
                return None, "ReadTimeout: controlled provider timeout"
            return "recovered fallback answer", None

        provider._call_model = fake_call  # type: ignore[method-assign]
        answer, name = await provider.chat("test")
        return calls, answer, name, paid_model, fallback_model

    calls, answer, provider_name, paid_model, fallback_model = asyncio.run(actual())
    assert calls[:2] == [paid_model, fallback_model]
    assert answer == "recovered fallback answer"
    assert provider_name == f"openrouter:{fallback_model}"
