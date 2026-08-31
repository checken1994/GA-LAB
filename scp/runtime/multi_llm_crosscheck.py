"""
Mảnh ghép #5 + #43 nâng cấp — Multi-LLM Cross-Check (từ JudgeCoreMixin dead code).

TẠI SAO: DNA #5 — ảo giác đồng thuận. 1 model duy nhất có thể ảo giác. Judge
cascade hiện tại dùng 2 model NHƯNG CÙNG PROVIDER (OpenRouter). Cross-vendor
verification = dùng model từ provider KHÁC NHAU (OpenRouter + Groq) để giảm
xác suất 2 model cùng ảo giác (independence assumption).

[HOTFIX 2026-08-29] Regression: for-loop bị xóa trong lần edit trước →
cross_verify() luôn trả final=None → mọi /ask UNKNOWN. Đã sửa: for-loop
được thêm lại + groq_judge dùng GroqProvider trực tiếp.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("scp.runtime.multi_llm_crosscheck")


async def cross_verify(
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

    tasks = [("primary", "judge"), ("secondary", "autofix")]


    results: dict[str, dict[str, Any]] = {}
    for role, task in tasks:  # ← FOR-LOOP ĐÃ BỊ XÓA — giờ thêm lại
        try:
            content, provider = await gateway.chat(prompt, system_prompt=system, task=task)
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
        p_fam = p_provider.split(":")[0] if ":" in p_provider else p_provider
        s_fam = s_provider.split(":")[0] if ":" in s_provider else s_provider
        if p_fam == s_fam:
            consensus = "insufficient_independence"
            final = None
        elif p == s:
            consensus = "agree"
            final = p
        else:
            consensus = "disagree"
            final = None  # escalate
    else:
        consensus = "missing_distinct_providers"
        final = None

    logger.info("[MULTI-LLM] primary(%s)=%s secondary(%s)=%s consensus=%s final=%s",
                p_provider, p, s_provider, s, consensus, final)
    return {
        "consensus": consensus,
        "primary": results.get("primary", {}),
        "secondary": results.get("secondary", {}),
        "final": final,
    }
