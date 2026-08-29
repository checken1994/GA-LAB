import logging

from scp.security.env_loader import load_selected_env

load_selected_env()

logger = logging.getLogger("scp.runtime.judge_llm")


def _llm_judge(question: str, ai_answer: str, context: str = "") -> bool:
    """Semantic PASS/FAIL judge.

    TẠI SAO qua gateway: trước đây hàm này POST thẳng tới
    http://127.0.0.1:11434 (Ollama local, model llama3.2) — khi Ollama bị
    gỡ bỏ, judge luôn except → return False → mọi RAG verify rơi
    CONTRADICTED. Routing qua get_gateway() khiến judge đi qua OpenRouter
    API cùng chiến lược fallback với toàn hệ thống.
    """
    try:
        from scp.llm_gateway import get_gateway

        prompt = f"Question: {question}\nContext: {context}\nAI Answer: {ai_answer}\nEvaluate if the AI Answer correctly answers the Question based ONLY on the Context (if provided) or general knowledge. Output only PASS or FAIL."
        content, _provider = get_gateway().chat_sync(
            prompt,
            system_prompt="You are a factual judge. You MUST output exactly the word PASS or FAIL and nothing else.",
            task="judge",
        )
        if not content:
            logger.warning("LLM judge returned no content (provider=%s)", _provider)
            return False
        return "PASS" in content.strip().upper()
    except Exception as e:
        print(f"LLM Judge error: {e}")
        return False
