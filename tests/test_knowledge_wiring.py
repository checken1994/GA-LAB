"""WIRED BRAIN — kho tri thức TOP-1% phải tới được lớp quyết định.

Reality Check v2 wound #3: advise() từng chỉ được gọi từ 1 endpoint cho
người. Hai test này khóa contract: WHY Gate và LLM fix prompt ĐỌC kho tri
thức tại thời điểm quyết định/vá code.
"""
from __future__ import annotations

import json
import time
import types

import pytest

import scp.autofix.llm_fix as llm_fix_mod
import scp.meta.why_gate as why_gate_mod
from scp.core.top_systems_learning import TopSystemsLearner
from scp.meta.why_gate import reset_why_gate


def _seeded_learner(tmp_path) -> TopSystemsLearner:
    learner = TopSystemsLearner(data_dir=str(tmp_path))
    learner._append_ledger([
        {
            "source": "github", "kind": "repository",
            "name": "example/robust-logging",
            "url": "https://github.com/example/robust-logging",
            "stars": 999, "description": "structured logging patterns for exception handling",
            "topic": "observability", "collected_at": time.time(),
        }
    ])
    return learner


def test_why_gate_consumes_warehouse(tmp_path, monkeypatch):
    learner = _seeded_learner(tmp_path)
    monkeypatch.setattr("scp.core.top_systems_learning.get_learner", lambda data_dir="data": learner)
    reset_why_gate()
    gate = why_gate_mod.get_why_gate(data_dir=str(tmp_path))
    result = gate.gate(
        action_type="autofix",
        action_desc="Fix BareExceptPass by adding structured logging",
        context="logger.exception replacement",
    )
    assert "[TOP1%]" in result.necessity_reason
    assert "example/robust-logging" in result.necessity_reason


def test_llm_fix_prompt_includes_warehouse(tmp_path, monkeypatch):
    learner = _seeded_learner(tmp_path)
    monkeypatch.setattr("scp.core.top_systems_learning.get_learner", lambda data_dir="data": learner)
    bug = types.SimpleNamespace(bug_type="BareExceptPass",
                                description="swallows errors silently — add structured logging",
                                file="mod.py", line=10)
    prompt = llm_fix_mod._build_fix_prompt(bug, "try:\n    pass\nexcept Exception:\n    pass")
    assert "SCP TOP-1% KNOWLEDGE WAREHOUSE" in prompt
    assert "example/robust-logging" in prompt


def test_prompt_unchanged_when_warehouse_empty(tmp_path, monkeypatch):
    learner = TopSystemsLearner(data_dir=str(tmp_path))  # empty ledger
    monkeypatch.setattr("scp.core.top_systems_learning.get_learner", lambda data_dir="data": learner)
    bug = types.SimpleNamespace(bug_type="RaceCondition", description="x", file="y.py", line=1)
    prompt = llm_fix_mod._build_fix_prompt(bug, "code")
    assert "SCP TOP-1% KNOWLEDGE WAREHOUSE" not in prompt


def test_github_token_bucket_is_mechanical():
    from scp.core.top_systems_learning import TokenBucket

    bucket = TokenBucket(capacity=1, refill_seconds=0.05)
    bucket.acquire(max_wait=5)  # burst consumed
    waited = bucket.acquire(max_wait=5)  # must WAIT for refill, not pass through
    assert waited > 0
    bucket.acquire(max_wait=5)  # drained again
    with pytest.raises(RuntimeError, match="local_rate_limit_timeout"):
        bucket.acquire(max_wait=0.001)  # no token and no patience → fail-closed
