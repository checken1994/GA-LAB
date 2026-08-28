"""
SCP - Redesigned TaskJudge
Replaces the bloated RealityJudge and Multi-SLM engine.
"""
from typing import Any, Optional
from scp.verifier import IndependentVerifier

class RealityJudge:
    """
    Unified Task Judge. Replaces all previous SLM layers.
    Delegates strictly to IndependentVerifier and TaskKernel.
    """
    def __init__(self, *args, **kwargs):
        self.verifier = IndependentVerifier()
        self.judged_count = 0
        self.fail_count = 0

    def judge(self, question: str, ai_answer: str = "", cycle_count: int = 0, **kwargs) -> dict[str, Any]:
        """Synchronous judge interface."""
        # Translate legacy inputs to verifier inputs
        postcondition = {"text_contains": ["*"]} if ai_answer else None
        obs = {"evidence_ref": ai_answer}
        
        result = self.verifier.verify(postcondition, obs)
        is_pass = (result.verdict == "VERIFIED")
        
        self.judged_count += 1
        if not is_pass:
            self.fail_count += 1

        return {
            "verdict": "PASS" if is_pass else "FAIL",
            "confidence": 1.0 if is_pass else 0.0,
            "reasoning": "Delegated to IndependentVerifier",
            "cycle_count": cycle_count,
            "failures": result.failures
        }

    async def judge_async(self, question: str, ai_answer: str = "", context: str = "", **kwargs) -> dict[str, Any]:
        return self.judge(question, ai_answer, **kwargs)

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
