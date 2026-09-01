from __future__ import annotations

import asyncio


class FakeProvider:
    def __init__(self, name: str, answer: str):
        self.PROVIDER_NAME = name
        self.answer = answer
        self.calls = 0
        self.enabled = True

    async def chat(self, question: str, context: str = "", system_prompt: str = "", prioritize_free: bool = False):
        self.calls += 1
        return self.answer, f"{self.PROVIDER_NAME}:local-model"


class FakeGateway:
    def __init__(self, providers):
        self.providers = list(providers)

    def provider_candidates(self, task: str):
        assert task == "judge"
        return list(self.providers)


def _run(gateway):
    from scp.runtime.multi_llm_crosscheck import cross_verify

    return asyncio.run(
        cross_verify(
            "Is the supplied answer supported?",
            "Yes.",
            context="The supplied evidence says yes.",
            gateway=gateway,
        )
    )


def test_cross_verify_selects_two_distinct_provider_families_before_calling():
    first = FakeProvider("family_a", "PASS")
    duplicate_family = FakeProvider("family_a", "PASS")
    second = FakeProvider("family_b", "PASS")

    result = _run(FakeGateway([first, duplicate_family, second]))

    assert result["consensus"] == "agree"
    assert result["final"] == "PASS"
    assert result["primary"]["provider"].startswith("family_a:")
    assert result["secondary"]["provider"].startswith("family_b:")
    assert first.calls == 1
    assert duplicate_family.calls == 0
    assert second.calls == 1


def test_cross_verify_distinct_provider_disagreement_fails_closed():
    first = FakeProvider("family_a", "PASS")
    second = FakeProvider("family_b", "FAIL")

    result = _run(FakeGateway([first, second]))

    assert result["consensus"] == "disagree"
    assert result["final"] is None


def test_cross_verify_one_provider_family_is_unavailable_not_consensus():
    first = FakeProvider("family_a", "PASS")
    duplicate_family = FakeProvider("family_a", "PASS")

    result = _run(FakeGateway([first, duplicate_family]))

    assert result["consensus"] == "missing_distinct_providers"
    assert result["final"] is None
    assert first.calls == 1
    assert duplicate_family.calls == 0
