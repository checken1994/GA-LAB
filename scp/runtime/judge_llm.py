import logging

from scp.security.env_loader import load_selected_env

load_selected_env()

logger = logging.getLogger("scp.runtime.judge_llm")

_JUDGE_SYSTEM = "You are a factual judge. You MUST output exactly the word PASS or FAIL and nothing else."


def _parse_verdict(content: str | None) -> str | None:
    """PASS | FAIL | None (ambiguous). Máy đọc, không cảm tính."""
    if not content:
        return None
    upper = content.upper()
    has_pass, has_fail = "PASS" in upper, "FAIL" in upper
    if has_pass and not has_fail:
        return "PASS"
    if has_fail and not has_pass:
        return "FAIL"
    return None


def _llm_judge(question: str, ai_answer: str, context: str = "") -> bool | None:
    """Semantic judge — TRI-STATE cascade (Cổng D, 2 tiers).

    Trả về:
      True  — PASS (model phán đúng dựa trên context/knowledge)
      False — FAIL (cả primary lẫn second-opinion model đều chối)
      None  — CHƯA QUYẾT ĐỊNH ĐƯỢC: LLM lỗi, trả lời ambiguous, hoặc
              HAI MODEL BẤT ĐỒNG → caller phải ESCALATE cho người
              (fail-closed đúng nghĩa: không ai bịa quyết định).

    Cascade: primary = task="judge" provider; nếu FAIL → second opinion qua
    task="autofix" provider (model mạnh hơn trong warehouse). Chỉ khi CẢ HAI
    cùng FAIL mới là FAIL thật.
    """
    try:
        from scp.llm_gateway import get_gateway

        prompt = f"Question: {question}\nContext: {context}\nAI Answer: {ai_answer}\nEvaluate if the AI Answer correctly answers the Question based ONLY on the Context (if provided) or general knowledge. Output only PASS or FAIL."
        gateway = get_gateway()
        first_content, _primary = gateway.chat_sync(
            prompt, system_prompt=_JUDGE_SYSTEM, task="judge"
        )
        first = _parse_verdict(first_content)
        if first == "PASS":
            return True
        if first is None:
            logger.warning("LLM judge ambiguous/empty (provider=%s) — escalate", _primary)
            return None
        # Primary nói FAIL → mượn não model mạnh hơn trước khi kết luận.
        second_content, _second = gateway.chat_sync(
            prompt, system_prompt=_JUDGE_SYSTEM, task="autofix"
        )
        second = _parse_verdict(second_content)
        if second == "PASS":
            logger.warning("Judge cascade disagreement (%s=FAIL vs %s=PASS) — escalate", _primary, _second)
            return None
        if second == "FAIL":
            return False
        return None
    except Exception as e:
        print(f"LLM Judge error: {e}")
        return None
