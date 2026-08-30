"""
SCP - Redesigned TaskJudge
Replaces the bloated RealityJudge and Multi-SLM engine.

[2026-08-29 Cổng D] Two-tier verification:
  Tier 1 (deterministic, ~1ms): tier1_guard — cấu trúc sai bị chém NGAY,
    không tốn một token LLM. LLM không bao giờ là Single Point of Truth
    cho các lỗi máy đọc được.
  Tier 2 (semantic): chỉ câu hỏi ngữ nghĩa mới xuống LLM, và LLM trả về
    TRI-STATE — None (không quyết định được / hai model bất đồng) →
    UNKNOWN + ESCALATE cho người, thay vì KILL oan (fail-closed đúng nghĩa).
"""
from typing import Any

from scp.security.tier1_guard import check as tier1_check
from scp.runtime.judge_llm import _llm_judge
from scp.verifier import IndependentVerifier


class RealityJudge:
    """
    Unified Task Judge. Delegates strictly to IndependentVerifier + Tier-1
    deterministic guard + tri-state LLM semantic cascade.
    """
    def __init__(self, *args, **kwargs):
        self.verifier = IndependentVerifier()
        self.judged_count = 0
        self.fail_count = 0

    def judge(self, question: str, ai_answer: str = "", cycle_count: int = 0, context: str = "", **kwargs) -> dict[str, Any]:
        """Synchronous judge interface."""
        from scp.core.postcondition_schema import PostconditionSchema

        # 1. Base structural validation (is there an answer?)
        if ai_answer:
            postcondition = PostconditionSchema.for_text_answer(ai_answer, evidence_required=False).to_dict()
        else:
            postcondition = PostconditionSchema.no_conditions().to_dict()

        obs = {"evidence_ref": ai_answer, "text": ai_answer}
        result = self.verifier.verify(postcondition, obs)
        is_structurally_pass = (result.verdict == "VERIFIED")

        is_pass = False
        escalated = False
        failures = list(result.failures)

        # 2. TIER-1 deterministic guard — chém trước, không tốn LLM.
        tier1 = tier1_check(question, ai_answer, context)
        if not tier1.passed:
            failures.extend(tier1.failures)

        # 3. TIER-2 semantic cascade — chỉ chạy khi Tier-1 sạch.
        #    [MẢNH 5+43] Cross-vendor verification: 2 provider khác nhau đánh giá
        #    độc lập → giảm xác suất ảo giác đồng thuận (DNA #5).
        elif is_structurally_pass and ai_answer:
            import os as _os
            if _os.environ.get("SCP_MULTI_LLM_CROSSCHECK", "1") == "1":
                try:
                    from scp.runtime.multi_llm_crosscheck import cross_verify
                    cross = cross_verify(question, ai_answer, context)
                    semantic = cross["final"]  # None nếu disagree/unavailable
                    if cross["consensus"] == "disagree":
                        failures.append("multi_llm_disagreement")
                except Exception as _cc_err:
                    # crosscheck fail → fallback về single cascade
                    semantic = _llm_judge(question, ai_answer, context)
            else:
                semantic = _llm_judge(question, ai_answer, context)
            if semantic is None:
                escalated = True
            elif semantic == "PASS" or semantic is True:
                is_pass = True
            else:
                failures.append("semantic_judge_fail")

        self.judged_count += 1
        if not is_pass and not escalated:
            self.fail_count += 1

        if escalated:
            return {
                "verdict": "UNKNOWN",
                "confidence": 0.0,
                "reasoning": "Semantic judge unavailable or model disagreement — escalated to human",
                "cycle_count": cycle_count,
                "failures": failures + ["semantic_judge_unavailable"],
                "final_answer": ai_answer,
                "evidence": {
                    "governance_decision": "ESCALATE",
                },
            }

        return {
            "verdict": "PASS" if is_pass else "FAIL",
            "confidence": 1.0 if is_pass else 0.0,
            "reasoning": "Delegated to IndependentVerifier and LLM Semantic Judge",
            "cycle_count": cycle_count,
            "failures": failures,
            "final_answer": ai_answer,
            "evidence": {
                "governance_decision": "UPHOLD" if is_pass else "KILL"
            }
        }

    async def judge_async(self, question: str, ai_answer: str = "", context: str = "", **kwargs) -> dict[str, Any]:
        return self.judge(question, ai_answer, context=context, **kwargs)

    async def judge_with_react_fallback(self, *args, **kwargs) -> dict[str, Any]:
        return self.judge(*args, **kwargs)

    def get_stats(self) -> dict:
        return {"total_judged": self.judged_count, "total_failed": self.fail_count}

    def analyze_session_rogue(self, *args, **kwargs) -> dict:
        return {"rogue_score": 0.0}

    # Stubs for legacy interfaces so we don't break import sites
    async def run_threat_simulation(self, *args, **kwargs): pass
    async def run_threat_intel_crawl(self, *args, **kwargs): return []
    def get_v98_status(self): return {}
    def get_v100_status(self): return {}
    async def run_scheduled_crawl(self, *args, **kwargs): return {}
    async def schedule_v100_background_jobs(self): pass
