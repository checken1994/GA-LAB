from pathlib import Path

import scp.meta.why_gate as why_gate


def test_why_provider_ollama_only_uses_gateway(monkeypatch):
    monkeypatch.setenv("SCP_LLM_PROVIDER_MODE", "ollama_only")
    seen = {}

    def fake_chat_sync(prompt, task):
        seen["prompt"] = prompt
        seen["task"] = task
        return "ollama-why", "ollama"

    monkeypatch.setattr("scp.llm_gateway.chat_sync", fake_chat_sync)
    assert why_gate._call_why_provider("bounded prompt") == "ollama-why"
    assert seen == {"prompt": "bounded prompt", "task": "why"}


def test_why_provider_auto_keeps_openrouter_compatibility(monkeypatch):
    monkeypatch.setenv("SCP_LLM_PROVIDER_MODE", "auto")
    seen = {}

    def fake_openrouter(prompt, max_tokens):
        seen["prompt"] = prompt
        seen["max_tokens"] = max_tokens
        return "openrouter-why"

    monkeypatch.setattr("scp.autofix.llm_fix._call_openrouter", fake_openrouter)
    assert why_gate._call_why_provider("compat prompt") == "openrouter-why"
    assert seen == {"prompt": "compat prompt", "max_tokens": 200}


def test_llm_necessity_negative_response_routes_to_uphold(tmp_path, monkeypatch):
    monkeypatch.setenv("SCP_WHY_LLM_ENABLED", "1")

    def fake_provider(prompt):
        if "Tại sao action này cần thiết?" in prompt:
            return "Không cần thiết. Hành động này không có lý do chính đáng."
        return "FALSIFICATION: no issue | SELF_FALSIFIED: no"

    monkeypatch.setattr(why_gate, "_call_why_provider", fake_provider)
    gate = why_gate.WhyGate(data_dir=str(tmp_path))
    reason, necessary = gate._check_necessity("unknown", "nonsense", "")
    result = gate.gate("unknown", "nonsense", "")

    assert "Không cần thiết" in reason
    assert necessary is False
    assert result.decision is why_gate.WhyDecision.UPHOLD
    assert result.allowed is True


def test_llm_necessity_negative_variants_never_approve():
    assert why_gate.WhyGate._parse_llm_necessity("This is not necessarily required") is False
    assert why_gate.WhyGate._parse_llm_necessity("Không nhất thiết phải thực hiện") is False


def test_llm_necessity_ambiguous_response_routes_to_uphold(tmp_path, monkeypatch):
    monkeypatch.setenv("SCP_WHY_LLM_ENABLED", "1")

    def fake_provider(prompt):
        if "Tại sao action này cần thiết?" in prompt:
            return "Tôi chưa đủ thông tin để kết luận."
        return "FALSIFICATION: no issue | SELF_FALSIFIED: no"

    monkeypatch.setattr(why_gate, "_call_why_provider", fake_provider)
    gate = why_gate.WhyGate(data_dir=str(tmp_path))
    reason, necessary = gate._check_necessity("unknown", "nonsense", "")
    ambiguous_reason, ambiguous_necessary = gate._check_necessity("unknown", "nonsense", "")
    result = gate.gate("unknown", "nonsense", "")

    assert "chưa đủ thông tin" in reason
    assert necessary is False
    assert "necessity ambiguous" in ambiguous_reason.lower()
    assert ambiguous_necessary is False
    assert result.decision is why_gate.WhyDecision.UPHOLD


def test_llm_necessity_positive_response_routes_to_allow(tmp_path, monkeypatch):
    monkeypatch.setenv("SCP_WHY_LLM_ENABLED", "1")

    def fake_provider(prompt):
        if "Tại sao action này cần thiết?" in prompt:
            return "Hành động này cần thiết để khôi phục dịch vụ bị lỗi."
        return "FALSIFICATION: no issue | SELF_FALSIFIED: no"

    monkeypatch.setattr(why_gate, "_call_why_provider", fake_provider)
    gate = why_gate.WhyGate(data_dir=str(tmp_path))
    reason, necessary = gate._check_necessity("unknown", "nonsense", "")
    result = gate.gate("unknown", "nonsense", "")

    assert "cần thiết" in reason
    assert necessary is True
    assert result.decision is why_gate.WhyDecision.ALLOW


def test_bare_except_deterministic_fix_accepts_trailing_noqa_comment(tmp_path):
    from scp.autofix.llm_fix import _generate_bare_except_fix

    fixture = tmp_path / "type_flow_verifier.py"
    fixture.write_text(
        "try:\n"
        "    work()\n"
        "except Exception:\n"
        "    pass  # noqa: BLE001\n",
        encoding="utf-8",
    )

    class Bug:
        bug_type = "BareExceptPass"
        file = str(fixture)
        line = 3

    patch = _generate_bare_except_fix(Bug())
    assert patch is not None
    assert "<<<<<<< SEARCH" in patch
    assert "except Exception:" in patch
    assert "logger.debug" in patch


def test_deterministic_bare_except_context_skips_weak_llm(monkeypatch, tmp_path):
    gate = why_gate.WhyGate(data_dir=str(tmp_path))

    def should_not_call(_prompt):
        raise AssertionError("deterministic BareExceptPass path must not call LLM")

    monkeypatch.setattr(why_gate, "_call_why_provider", should_not_call)
    reason, falsified = gate._check_falsification(
        "autofix",
        "Evolve cycle: fix bug C:/scp/type_flow_verifier.py:717",
        "deterministic BareExceptPass logging replacement",
    )
    assert "Local deterministic BareExceptPass" in reason
    assert falsified is False


def test_gate_llm_used_is_true_only_for_calls_during_this_gate(tmp_path: Path, monkeypatch):
    gate = why_gate.WhyGate(data_dir=str(tmp_path))

    def necessity(*_args):
        gate._stats["llm_calls"] += 1
        return "necessary", True

    def falsification(*_args):
        gate._stats["llm_calls"] += 1
        return "safe", False

    monkeypatch.setattr(gate, "_check_necessity", necessity)
    monkeypatch.setattr(gate, "_check_falsification", falsification)
    result = gate.gate(
        action_type="autofix",
        action_desc="fix deterministic BareExceptPass",
        context="deterministic logging replacement",
    )
    assert result.llm_used is True
    assert result.allowed is True

    gate._stats["llm_calls"] = 0
    monkeypatch.setattr(gate, "_check_necessity", lambda *_args: ("regex", True))
    monkeypatch.setattr(gate, "_check_falsification", lambda *_args: ("regex", False))
    result_without_call = gate.gate(
        action_type="autofix",
        action_desc="fix deterministic BareExceptPass",
        context="deterministic logging replacement",
    )
    assert result_without_call.llm_used is False
