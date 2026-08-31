from __future__ import annotations
import os

import asyncio

from scp.llm_gateway.client import OpenRouterProvider


def test_openrouter_timeout_recovers_via_task_free_fallback() -> None:
    async def actual() -> tuple[list[str], str | None, str]:
        provider = OpenRouterProvider(task="judge")
        provider._API_KEYS = ["test-key"]
        provider._next_key = lambda: "test-key"  # type: ignore[method-assign]
        calls: list[str] = []
        paid_model = provider.model

        async def fake_call(model: str, messages: list[dict], api_key: str):
            calls.append(model)
            if model == paid_model:
                return None, "ReadTimeout: controlled provider timeout"
            return "recovered fallback answer", None

        provider._call_model = fake_call  # type: ignore[method-assign]
        answer, name = await provider.chat("test")
        return calls, answer, name

    calls, answer, provider_name = asyncio.run(actual())
    expected_primary = os.environ.get(
        "OPENROUTER_MODEL_JUDGE_PRIMARY", "anthropic/claude-3-5-sonnet"
    )
    expected_fallback = os.environ.get(
        "OPENROUTER_MODEL_JUDGE", "nvidia/nemotron-3-super-120b-a12b:free"
    )
    assert calls[:2] == [expected_primary, expected_fallback]
    assert answer == "recovered fallback answer"
    assert provider_name == f"openrouter:{expected_fallback}"
