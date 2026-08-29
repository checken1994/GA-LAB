"""
Mảnh ghép #5 + #43 nâng cấp — Multi-LLM Cross-Check (từ JudgeCoreMixin dead code).

TẠI SAO: DNA #5 — Ảo giác đồng thuận. 1 model duy nhất có thể ảo giác. Judge
cascade hiện tại dùng 2 model NHƯNG CÙNG PROVIDER (OpenRouter). Cross-vendor
verification = dùng model từ provider KHÁC NHAU (OpenRouter + Groq) để giảm
xác suất 2 model cùng ảo giác (independence assumption).

Được wire vào RealityJudge.judge() thay cho single-model cascade.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("scp.runtime.multi_llm_crosscheck")


def cross_verify(
    question: str,
    ai_answer: str,
    context: str = "",
    verdict_tier1: bool = True,
) -> dict[str, Any]:
    """Cross-vendor verification: gửi CÙNG câu hỏi cho 2 provider khác nhau.

    Trả về:
      {"consensus": "agree"|"disagree"|"unavailable",
       "primary": {"verdict": "PASS"|"FAIL"|None, "provider": str},
       "secondary": {"verdict": "PASS"|"FAIL"|None, "provider": str},
       "final": "PASS"|"FAIL"|None}

    Logic:
      - primary (task="judge" → OpenRouter) và secondary (task="autofix" →
        Groq/nhà cung cấp khác) đánh giá độc lập
      - agree PASS → PASS
      - agree FAIL → FAIL
      - disagree → None (escalate cho người)
      - 1 trong 2 unavailable → dùng kết quả của model còn lại (không tự bịa)
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

    results = {}
    for role, task in [("primary", "judge"), ("secondary", "autofix")]:
        try:
            content, provider = gateway.chat_sync(prompt, system_prompt=system, task=task)
            results[role] = {
                "verdict": _parse_verdict(content),
                "provider": provider,
            }
        except Exception as exc:
            results[role] = {"verdict": None, "provider": f"error:{type(exc).__name__}"}

    p = results.get("primary", {}).get("verdict")
    s = results.get("secondary", {}).get("verdict")
    p_provider = results.get("primary", {}).get("provider", "?")
    s_provider = results.get("secondary", {}).get("provider", "?")

    if p is not None and s is not None:
        if p == s:
            consensus = "agree"
            final = p
        else:
            consensus = "disagree"
            final = None  # escalate
    elif p is not None:
        consensus = "single_source"
        final = p
    elif s is not None:
        consensus = "single_source"
        final = s
    else:
        consensus = "unavailable"
        final = None

    logger.info("[MULTI-LLM] primary(%s)=%s secondary(%s)=%s consensus=%s final=%s",
                p_provider, p, s_provider, s, consensus, final)
    return {
        "consensus": consensus,
        "primary": results.get("primary", {}),
        "secondary": results.get("secondary", {}),
        "final": final,
    }
