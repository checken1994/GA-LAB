from typing import Any
from scp.runtime.judge_parts.phases.context import JudgeContext
import time
from datetime import datetime
import os
import logging
logger = logging.getLogger(__name__)

class Phase6RealityCheckMixin:
    def _phase6_reality_check(self, ctx: JudgeContext) -> Any:
            # Step 7: Reality check (verify với V13 engine)
            # [OPT] Skip V13 reality check if SLM already has answer with real_value
            # [V90 LEARN] When no AI answer but SLM has answer → set reality_check for learning
            ctx._best_slm_answer = ""
            if ctx.valid_responses:
                ctx._best = max(ctx.valid_responses, key=lambda r: ctx.r.get("confidence", 0))
                ctx._best_slm_answer = ctx._best.get("answer", "")
            if not ctx.ai_answer and ctx._best_slm_answer and ctx.confidence >= 0.65:
                # [V104.40 #M] TẠI SAO: was is_correct=True, source="slm_self" → SLM
                # self-confirmed as reality → knowledge contamination. Fix: is_correct=None
                # (cannot verify without external source), source="slm_self_unverified".
                ctx.reality_check = {"is_correct": None, "real_value": None, "reason": "SLM self-answered but no external source — cannot verify (Evidence-First)", "source": "slm_self_unverified"}
            else:
                ctx.reality_check = {"is_correct": None, "reason": "No AI answer to verify"}
            ctx.slm_has_real_value = any(ctx.r.get("evidence", {}).get("value") is not None for ctx.r in ctx.valid_responses)
            if ctx.ai_answer and not ctx.slm_has_real_value:
                # Only call V13 if SLMs didn't provide real_value (avoid double API call)
                ctx.v13_result = self.v13.process(ctx.question, ctx.ai_answer)
                ctx.reality_check = {
                    "is_correct": ctx.v13_result.final_verdict == "PASS",
                    "verdict": ctx.v13_result.final_verdict,
                    "reason": ctx.v13_result.final_reason[:200],
                    "real_value": ctx.v13_result.ctx.real_value,
                    "source": ctx.v13_result.ctx.source,
                    "verdict_detail": ctx.v13_result.verdict_detail,
                }
                if ctx.v13_result.final_verdict == "FAIL":
                    ctx.verdict_type = "FAIL"
                    ctx.reasoning += f". Reality check: {ctx.v13_result.final_reason[:100]}"
            
                # [FIX v26] BYPASS V13: Nếu V13 trả về UNKNOWN → dùng DirectAPIVerifier
                if ctx.v13_result.final_verdict == "UNKNOWN" and ctx.ai_answer:
                    try:
                        # self.v13 = SCPV13, self.v13.v13 = SelfHealingEngine
                        # direct_verifier is on SCPV13 (self.v13)
                        if hasattr(self.v13, 'direct_verifier') and self.v13.direct_verifier:
                            ctx.direct_result = self.v13.direct_verifier.verify(ctx.question, ctx.ai_answer, ctx.primary_domain)
                            if ctx.direct_result["verdict"] != "UNKNOWN":
                                ctx.reality_check = {
                                    "is_correct": ctx.direct_result["verdict"] == "PASS",
                                    "verdict": ctx.direct_result["verdict"],
                                    "reason": ctx.direct_result["reason"][:200],
                                    "real_value": ctx.direct_result["real_value"],
                                    "source": ctx.direct_result["source"],
                                    "verdict_detail": "",
                                }
                                if ctx.direct_result["verdict"] == "FAIL":
                                    ctx.verdict_type = "FAIL"
                                    ctx.reasoning += f". Direct verify: {ctx.direct_result['reason'][:100]}"
                                elif ctx.direct_result["verdict"] == "PASS":
                                    if ctx.verdict_type in ("UNKNOWN", "PARTIAL"):
                                        ctx.verdict_type = "PASS"
                                        ctx.reasoning += f". Direct verify PASS: {ctx.direct_result['reason'][:100]}"
                    except Exception as e:
                        logger.warning(f"Direct verify failed: {e}")
            elif ctx.slm_has_real_value:
                # SLM already has real_value — use it directly, skip V13
                ctx.best_resp = max(ctx.valid_responses, key=lambda x: x.get("confidence", 0))
                ctx.real_val = ctx.best_resp.get("evidence", {}).get("value")
                ctx.src = ctx.best_resp.get("evidence", {}).get("source", "slm")
                ctx.reality_check = {
                    "is_correct": None,
                    "verdict": "PASS" if ctx.verdict_type == "PASS" else "FAIL",
                    "reason": f"SLM {ctx.best_resp.get('slm_name','?')} provided value",
                    "real_value": ctx.real_val,
                    "source": ctx.src,
                    "verdict_detail": "",
                }
            
            # [V90 OPT] Skip similar_errors — DB query per question, low value
            ctx.similar_errors = []
            
            #  Apply adversary conflict flag NOW — after Step 6 finalized
            # verdict_type, before building JudgeVerdict. TẠI SAO: V104.40 #K tried to
            # set CONFLICT at Step 5.5 (line ~1854) but verdict_type was None then.
            # Now verdict_type is set (PASS/FAIL/UNKNOWN/PARTIAL/SPECULATIVE/CONFLICT).
            # Constitution: "reality outranks model opinion" — if adversary found a
            # DIFFERENT value from an independent source, PASS must become CONFLICT.
            # FAIL/UNKNOWN/etc. are left unchanged (adversary conflict doesn't upgrade them).
            if ctx._adversary_conflict and ctx.verdict_type == "PASS":
                ctx.verdict_type = "CONFLICT"
                ctx.reasoning += ctx._adversary_conflict_reason
            
            # Clamp confidence to [0, 1] — was missing, could go negative or >1 in edge cases.
            if ctx.confidence is not None:
                ctx.confidence = max(0.0, min(1.0, ctx.confidence))
            
            # [AI-PATTERNS] Tree of Thoughts — explore multiple reasoning paths
            # TẠI SAO: khi verdict_type = UNKNOWN (Reality check + V13 + DirectAPIVerifier
            # đều không chốt được), Self-Consistency re-sample cùng prompt sẽ không giúp
            # gì nếu chính prompt bị hiểu sai. Tree of Thoughts explore 3 reasoning
            # framings KHÁC NHAU (semantic / factual / counterfactual) → nếu ≥2/3 branches
            # đồng thuận CORRECT, upgrade UNKNOWN → PASS. Industry: Yao et al. 2023.
            # [Task 19-C] wire ToT vào judge.py reality-check section.
            try:
                if ctx.verdict_type == "UNKNOWN" and self.llm_client is not None and ctx.ai_answer:
                    from scp.ai_patterns import TreeOfThoughts
                    ctx.tot_result = TreeOfThoughts.explore_paths(
                        self.llm_client, ctx.question, ctx.ai_answer
                    )
                    if ctx.tot_result.get("verdict") == "CORRECT":
                        ctx.verdict_type = "PASS"
                        ctx.confidence = max(ctx.confidence, ctx.tot_result.get("confidence", 0.5))
                        ctx.reasoning += (
                            f". ToT upgrade UNKNOWN→PASS "
                            f"(agreement={ctx.tot_result.get('agreement', 0):.2f}, "
                            f"branches={ctx.tot_result.get('branches_used', 0)})"
                        )
                        logger.info(
                            f"[ToT] upgrade UNKNOWN→PASS for q='{ctx.question[:60]}' "
                            f"(branches={ctx.tot_result.get('branches_used')}, "
                            f"agreement={ctx.tot_result.get('agreement'):.2f})"
                        )
            except Exception as e:
                logger.debug(f"ToT explore failed: {e}")
            
            ctx._math_verdict = None
            # Independent deterministic math verification. This only acts when
            # the existing safe evaluator can parse and verify the expression.
            # Security, WHY and Governance still run after this point.
            try:
                from scp.core.math_evaluator import verify_math as _verify_math
                ctx._math_verdict, ctx._math_value, ctx._math_reason = _verify_math(
                    ctx.question or '', ctx.ai_answer or ctx.final_answer or ''
                )
                if ctx._math_verdict == 'PASS':
                    ctx.verdict_type = 'PASS'
                    ctx.confidence = max(ctx.confidence, 0.99)
                    ctx.reasoning = f'Deterministic math verify PASS: {ctx._math_reason}'
                elif ctx._math_verdict == 'FAIL':
                    ctx.verdict_type = 'FAIL'
                    ctx.confidence = max(ctx.confidence, 0.99)
                    ctx.reasoning = f'Deterministic math verify FAIL: {ctx._math_reason}'
            except Exception as _math_err:
                logger.debug(f'Deterministic math verification unavailable: {_math_err}')
            
        
