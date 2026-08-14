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
