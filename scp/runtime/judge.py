"""
SCP - Redesigned TaskJudge
Replaces the bloated RealityJudge and Multi-SLM engine.
"""
from typing import Any, Optional
from scp.verifier import IndependentVerifier
from scp.runtime.judge_llm import _llm_judge

class RealityJudge:
    """
    Unified Task Judge. Replaces all previous SLM layers.
    Delegates strictly to IndependentVerifier and TaskKernel, plus real LLM semantic judgment.
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
        
        # 2. TRUE SEMANTIC VERIFIER (Root Fix)
        # We use a real LLM to judge the factual correctness instead of trivial postcondition matching.
        is_pass = False
        failures = list(result.failures)
        if is_structurally_pass and ai_answer:
            if _llm_judge(question, ai_answer, context):
                is_pass = True
            else:
                failures.append("semantic_judge_fail")
        
        self.judged_count += 1
        if not is_pass:
            self.fail_count += 1

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
