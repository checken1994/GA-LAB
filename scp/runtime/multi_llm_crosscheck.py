"""Multi-provider factual cross-check.

The verification contract is provider-family independence, not merely two model
calls.  A previous implementation relied on the gateway's global round-robin
counter to make consecutive calls land on different providers. Under concurrent
/ask traffic those calls interleaved, so a single verification could receive
OpenRouter+OpenRouter (or provider2+provider2) and fail with
``insufficient_independence`` even while a distinct healthy provider existed.

This module now makes the independence constraint explicit: after the primary
verdict, the secondary call is selected only from provider families different
from the primary family.  No global serialization is required.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("scp.runtime.multi_llm_crosscheck")


def _provider_family(label: str | None) -> str:
    value = str(label or "").strip()
    if not value:
        return ""
    return value.split(":", 1)[0]


async def _chat_excluding_family(
    gateway: Any,
    question: str,
    *,
    context: str,
    system_prompt: str,
    task: str,
    excluded_family: str,
) -> tuple[str | None, str]:
    """Call a healthy provider whose family differs from ``excluded_family``.

    The gateway currently exposes its provider chain through ``_provider_chain``
    rather than a public constrained-routing API.  Keeping the selection here is
    preferable to weakening the independence invariant or serializing all judge
    traffic behind a global lock.  If a future gateway adds a public exclusion
    API this helper can delegate to it without changing cross_verify semantics.
    """
    chain_factory = getattr(gateway, "_provider_chain", None)
    if not callable(chain_factory):
        content, provider = await gateway.chat(
            question,
            context=context,
            system_prompt=system_prompt,
            task=task,
        )
        if content is not None and _provider_family(provider) != excluded_family:
            return content, provider
        return None, "none:distinct-provider-unavailable"

    try:
        chain = list(chain_factory(task))
    except Exception as exc:
        logger.warning("[MULTI-LLM] unable to inspect provider chain for %s: %s", task, exc)
        return None, "none:provider-chain-error"

    candidates = [
        provider
        for provider in chain
        if bool(getattr(provider, "enabled", False))
        and str(getattr(provider, "PROVIDER_NAME", "")) != excluded_family
    ]
    healthy = []
    degraded = []
    for provider in candidates:
        breaker = getattr(provider, "_breaker", None)
        try:
            is_open = bool(breaker.is_open()) if breaker is not None else False
        except Exception:
            is_open = True
        (degraded if is_open else healthy).append(provider)

    for provider in [*healthy, *degraded]:
        try:
            content, label = await provider.chat(
                question,
                context=context,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            logger.warning(
                "[MULTI-LLM] distinct provider %s failed: %s",
                getattr(provider, "PROVIDER_NAME", "?"),
                exc,
            )
            continue
        if content is None:
            continue
        if _provider_family(label) == excluded_family:
            logger.error(
                "[MULTI-LLM] provider exclusion violated: excluded=%s returned=%s",
                excluded_family,
                label,
            )
            continue
        return content, label

    return None, "none:distinct-provider-unavailable"


async def cross_verify(
    question: str,
    ai_answer: str,
    context: str = "",
    verdict_tier1: bool = True,
) -> dict[str, Any]:
    """Verify one answer using two distinct provider families.

    Returns a final PASS/FAIL only when both semantic verdicts are available,
    their provider families differ, and both verdicts agree. Missing providers,
    disagreement, or lost independence remain fail-closed as ``final=None``.
    """
    from scp.runtime.judge_llm import _parse_verdict
    from scp.llm_gateway import get_gateway

    gateway = get_gateway()
    prompt = (
        f"Question: {question}\nContext: {context}\nAI Answer: {ai_answer}\n"
        "Evaluate if the AI Answer correctly answers the Question based ONLY on "
        "the Context (if provided) or general knowledge. Output only PASS or FAIL."
    )
    system = "You are a factual judge. You MUST output exactly the word PASS or FAIL and nothing else."

    results: dict[str, dict[str, Any]] = {}

    try:
        primary_content, primary_provider = await gateway.chat(
            prompt,
            system_prompt=system,
            task="judge",
        )
        results["primary"] = {
            "verdict": _parse_verdict(primary_content),
            "provider": primary_provider,
        }
    except Exception as exc:
        results["primary"] = {
            "verdict": None,
            "provider": f"error:{type(exc).__name__}",
        }

    p = results["primary"]["verdict"]
    p_provider = str(results["primary"].get("provider", "?"))
    p_family = _provider_family(p_provider)

    try:
        if p is not None and p_family and p_family not in {"none", "error"}:
            secondary_content, secondary_provider = await _chat_excluding_family(
                gateway,
                prompt,
                context="",
                system_prompt=system,
                task="autofix",
                excluded_family=p_family,
            )
        else:
            secondary_content, secondary_provider = await gateway.chat(
                prompt,
                system_prompt=system,
                task="autofix",
            )
        results["secondary"] = {
            "verdict": _parse_verdict(secondary_content),
            "provider": secondary_provider,
        }
    except Exception as exc:
        results["secondary"] = {
            "verdict": None,
            "provider": f"error:{type(exc).__name__}",
        }

    s = results["secondary"]["verdict"]
    s_provider = str(results["secondary"].get("provider", "?"))
    s_family = _provider_family(s_provider)

    if p is not None and s is not None:
        if not p_family or not s_family or p_family == s_family:
            consensus = "insufficient_independence"
            final = None
        elif p == s:
            consensus = "agree"
            final = p
        else:
            consensus = "disagree"
            final = None
    else:
        consensus = "missing_distinct_providers"
        final = None

    logger.info(
        "[MULTI-LLM] primary(%s)=%s secondary(%s)=%s consensus=%s final=%s",
        p_provider,
        p,
        s_provider,
        s,
        consensus,
        final,
    )
    return {
        "consensus": consensus,
        "primary": results.get("primary", {}),
        "secondary": results.get("secondary", {}),
        "final": final,
    }
