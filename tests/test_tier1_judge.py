"""Two-tier judge (Cổng D): Tier-1 deterministic chém trước LLM; Tier-2
tri-state cascade — None → UNKNOWN/ESCALATE, không bao giờ KILL oan."""
from __future__ import annotations

import pytest

import scp.runtime.judge as judge_mod
from scp.runtime.judge import RealityJudge


@pytest.fixture()
def semantic_gate(monkeypatch):
    calls = {"n": 0}
    state = {"value": True}

    def _fake(question, ai_answer, context=""):
        calls["n"] += 1
        return state["value"]

    monkeypatch.setattr(judge_mod, "_llm_judge", _fake)
    return state, calls


def test_tier1_chops_empty_answer_without_llm(semantic_gate, monkeypatch):
    state, calls = semantic_gate
    verdict = RealityJudge().judge("q", ai_answer="   ")
    assert verdict["verdict"] == "FAIL"
    assert any("REJECT_EMPTY" in f for f in verdict["failures"])
    assert calls["n"] == 0  # LLM không bị đánh thức


def test_tier1_chops_control_chars_without_llm(semantic_gate):
    state, calls = semantic_gate
    verdict = RealityJudge().judge("q", ai_answer="ok\u200b\ufeffanswer")
    assert verdict["verdict"] == "FAIL"
    assert any("REJECT_CONTROL_CHARS" in f for f in verdict["failures"])
    assert calls["n"] == 0


def test_semantic_pass(semantic_gate):
    state, _ = semantic_gate
    state["value"] = True
    verdict = RealityJudge().judge("q", ai_answer="The sky is blue", context="sky is blue")
    assert verdict["verdict"] == "PASS"
    assert verdict["evidence"]["governance_decision"] == "UPHOLD"


def test_semantic_fail(semantic_gate):
    state, _ = semantic_gate
    state["value"] = False
    verdict = RealityJudge().judge("q", ai_answer="The sky is blue")
    assert verdict["verdict"] == "FAIL"
    assert verdict["evidence"]["governance_decision"] == "KILL"


def test_semantic_unavailable_escalates_instead_of_kill(monkeypatch):
    monkeypatch.setattr(judge_mod, "_llm_judge", lambda *a, **k: None)
    verdict = RealityJudge().judge("q", ai_answer="The sky is blue")
    assert verdict["verdict"] == "UNKNOWN"
    assert verdict["evidence"]["governance_decision"] == "ESCALATE"
    assert "semantic_judge_unavailable" in verdict["failures"]


def test_judge_llm_parse_verdict():
    """[MẢNH 3] Contract mới: think-block bị cắt, token CUỐI CÙNG thắng —
    reasoning model không thể lỡ parser bằng suy luận nội bộ."""
    from scp.runtime.judge_llm import _parse_verdict

    assert _parse_verdict("PASS") == "PASS"
    assert _parse_verdict("fail") == "FAIL"
    # Token cuối cùng thắng (đáp án cuối cùng của model là phán quyết)
    assert _parse_verdict("PASS but maybe FAIL") == "FAIL"
    assert _parse_verdict("FAIL ... final: PASS") == "PASS"
    # Think block bị loại trước khi parse — suy luận nội bộ không phải verdict
    assert _parse_verdict("<think>đang nghĩ PASS hay FAIL</think>FAIL") == "FAIL"
    assert _parse_verdict("<think>FAIL</think>PASS") == "PASS"
    assert _parse_verdict("") is None
    assert _parse_verdict(None) is None
    assert _parse_verdict("không có phán quyết nào") is None


def test_judge_llm_cascade_requires_double_fail(monkeypatch):
    """Primary FAIL + second-opinion PASS → None (bất đồng → người)."""
    import scp.runtime.judge_llm as jl

    calls = {"tasks": []}

    def fake_chat_sync(prompt, system_prompt="", task="default"):
        calls["tasks"].append(task)
        content = "FAIL" if task == "judge" else "PASS"
        return content, f"provider:{task}"

    class FakeGateway:
        chat_sync = staticmethod(fake_chat_sync)

    monkeypatch.setattr(jl, "_JUDGE_SYSTEM", jl._JUDGE_SYSTEM)
    monkeypatch.setattr(
        "scp.llm_gateway.get_gateway", lambda: FakeGateway()
    )
    monkeypatch.setattr(jl, "get_gateway", lambda: FakeGateway(), raising=False)
    result = jl._llm_judge("q", "answer", "ctx")
    assert result is None
    assert calls["tasks"] == ["judge", "autofix"]  # cascade đã chạy đủ 2 tầng
