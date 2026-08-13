# [P2-15] Pending fix for ai_patterns.py — queued for HUMAN review.
# SCP could not auto-parse the LLM fix into a safe patch.
# Original file: C:\Users\check\Downloads\scp\scp\ai_patterns.py
# Suggested fix from LLM:
# <<<<<<< SEARCH
# @classmethod
# def augment_prompt(cls, question: str, answer: str) -> tuple[str, str]:
#     """[R19-FIX-5] DEPRECATED — 0 callers (vulture confirmed).
#     Kept for backward compat. Use RealityJudge._llm_verify_reality_check instead.
#     """
#     user_prompt = (f"Câu hỏi: {question[:500]}\n{f"Câu trả lời cần kiểm tra: {answer[:500]}\n\n{f"Hãy phân tích từng bước và kết luận."}"
# return cls.COT_SYSTEM_PROMPT, user_prompt
# >>>>>>> REPLACE
# <<<<<<< SEARCH
# @classmethod
# def verify_with_voting(cls, llm_client, question: str, answer: str, system_prompt: str, n_samples: int | None = None) -> dict:
#     """[R19-FIX-5] DEPRECATED — 0 callers (vulture confirmed).
#     Superseded by RealityJudge multi-SLM consensus (R8+). Kept for backward compat.
#     """
#     return {}
# >>>>>>> REPLACE
