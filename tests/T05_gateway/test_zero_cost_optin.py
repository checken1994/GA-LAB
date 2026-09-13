"""Opt-in zero-cost wall policy tests (S18, owner directive 2026-09-13).

The exact-$0 wall must be an OPT-IN deployment policy keyed on
``SCP_LLM_COST_MODE=free_only`` — not a compile-time mandate that silently
kills every LLM call when the variable is unset (the container bug).

These tests pin BOTH branches against the real authorize_outbound /
record_outbound_sent boundary, so strictness INCREASES (FA-01: nothing is
weakened, skipped or xfailed):

  * default (SCP_LLM_COST_MODE unset)  -> passthrough allow, guard never built;
  * opt-in (SCP_LLM_COST_MODE=free_only) -> wall still denies unknown price.
"""
from __future__ import annotations

import pytest

from scp.llm_gateway import zero_cost_runtime
from scp.llm_gateway.zero_cost_guard import (
    ZeroCostDecision,
    ZeroCostDenied,
)


def test_cost_wall_default_off_is_passthrough_and_builds_no_guard(monkeypatch):
    # The T05 autouse fixture sets SCP_LLM_COST_MODE=free_only; a default
    # deployment leaves it UNSET. Removing it here is the *precondition* the
    # policy depends on, not a weakening: unset must mean "wall not installed".
    monkeypatch.delenv("SCP_LLM_COST_MODE", raising=False)
    assert zero_cost_runtime._guard is None

    request, proof = zero_cost_runtime.authorize_outbound(
        provider="anypaid",
        model="gpt-4o",
        task_class="default",
    )

    assert proof is None
    assert request.provider == "anypaid"
    assert request.model == "gpt-4o"
    assert request.task_class == "default"
    # Wall bypassed: no guard construction, no proof-store/DB, no validation.
    assert zero_cost_runtime._guard is None
    assert zero_cost_runtime._store is None

    # record_outbound_sent is a no-op while the policy is inactive.
    assert zero_cost_runtime.record_outbound_sent(request, proof) == ""
    assert zero_cost_runtime._guard is None
    assert zero_cost_runtime._store is None


def test_cost_wall_opt_in_still_denies_unknown_price(monkeypatch):
    # Same call, policy explicitly opted in: the wall is authoritative again.
    monkeypatch.setenv("SCP_LLM_COST_MODE", "free_only")

    with pytest.raises(ZeroCostDenied) as exc:
        zero_cost_runtime.authorize_outbound(
            provider="anypaid",
            model="gpt-4o",
            task_class="default",
        )

    assert exc.value.decision is ZeroCostDecision.DENY_UNKNOWN_PRICE


def test_free_only_policy_active_reads_env(monkeypatch):
    # Case/whitespace tolerant positive, and every non-free_only form is off.
    monkeypatch.setenv("SCP_LLM_COST_MODE", "  FREE_ONLY ")
    assert zero_cost_runtime._free_only_policy_active() is True

    for value in ("", "paid", "hybrid", "Free-Only-ish", "0"):
        monkeypatch.setenv("SCP_LLM_COST_MODE", value)
        assert zero_cost_runtime._free_only_policy_active() is False

    monkeypatch.delenv("SCP_LLM_COST_MODE", raising=False)
    assert zero_cost_runtime._free_only_policy_active() is False
