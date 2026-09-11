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
import asyncio
import logging
import threading
from typing import Any

from scp.security.tier1_guard import check as tier1_check
from scp.runtime.judge_llm import _llm_judge
from scp.verifier import IndependentVerifier

logger = logging.getLogger("scp.judge")


def _run_crosscheck_sync(question: str, ai_answer: str, context: str) -> dict[str, Any]:
    """[A2] Chạy cross_verify (async) từ sync judge() — crosscheck phải chạy THẬT.

    Audit (M2): trước đây sync judge() gọi `cross_verify(...)` KHÔNG await →
    nhận coroutine → `cross["final"]` TypeError → except nuốt im lặng → mọi
    sync verdict thực chất chỉ qua single cascade. Crosscheck đã "sống lại".

    Caller sync judge() chạy trong worker thread (asyncio.to_thread) nên thường
    không có event loop → asyncio.run trực tiếp. Nếu vô tình gọi từ thread đang
    chạy loop, bridge qua worker thread riêng (loop riêng) để crosscheck vẫn
    chạy thật thay vì raise RuntimeError.
    """
    from scp.runtime.multi_llm_crosscheck import cross_verify

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(cross_verify(question, ai_answer, context))

    box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            box["result"] = asyncio.run(cross_verify(question, ai_answer, context))
        except BaseException as exc:  # bridge truyền lỗi nguyên trạng ra ngoài
            box["error"] = exc

    bridge = threading.Thread(target=_worker, daemon=True, name="scp-crosscheck-sync-bridge")
    bridge.start()
    bridge.join()
    if "error" in box:
        raise box["error"]
    return box["result"]


class RealityJudge:
    """
    Unified Task Judge. Delegates strictly to IndependentVerifier + Tier-1
    deterministic guard + tri-state LLM semantic cascade.
    """
    def __init__(self, *args, **kwargs):
        self.verifier = IndependentVerifier()
        self.judged_count = 0
        self.fail_count = 0


    @property
    def domain_experts(self):
        if not hasattr(self, '_experts'):
            self._experts = {}
            import importlib
            import inspect
            import os
            from scp.runtime.slm_base import BaseSLM
            experts_dir = os.path.join(os.path.dirname(__file__), 'experts')
            for filename in os.listdir(experts_dir):
                if filename.endswith('.py') and filename != '__init__.py':
                    module_name = f'scp.runtime.experts.{filename[:-3]}'
                    try:
                        module = importlib.import_module(module_name)
                        for name, obj in inspect.getmembers(module, inspect.isclass):
                            if issubclass(obj, BaseSLM) and obj != BaseSLM:
                                try:
                                    instance = obj()
                                    self._experts[instance.domain] = instance
                                except Exception:
                                    pass
                    except Exception:
                        pass
        return self._experts
    @property
    def falsification(self): return None
    @property
    def error_store(self): return None
    @property
    def governance(self): return None
    @property
    def counter_response(self): return None
    @property
    def canary_monitor(self): return None
    @property
    def attack_memory(self): return None
    @property
    def domain_knowledge_store(self): return None
    @property
    def h8_redteam(self): return None
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
        slm_responses_list = []
        if not tier1.passed:
            failures.extend(tier1.failures)
        elif is_structurally_pass and ai_answer:
            # 2.5. TIER-1.5: Dynamic API Expert Injection
            try:
                from scp.data_sources.domain_classifier import classify_top1
                domain = classify_top1(question)
                expert = self.domain_experts.get(domain)
                if expert:
                    resp = expert.predict(question)
                    if getattr(resp, "answer", None):
                        context += f"\n[SYSTEM EXPERT DATA] For {domain}: {resp.answer}"
                        slm_responses_list.append(resp.__dict__)
            except Exception as e:
                import logging
                logging.getLogger("scp.judge").debug(f"Expert injection failed: {e}")

        # 3. TIER-2 semantic cascade — chỉ chạy khi Tier-1 sạch.
        #    [MẢNH 5+43] Cross-vendor verification: 2 provider khác nhau đánh giá
        #    độc lập → giảm xác suất ảo giác đồng thuận (DNA #5).

            import os as _os
            if _os.environ.get("SCP_MULTI_LLM_CROSSCHECK", "1") == "1":
                try:
                    cross = _run_crosscheck_sync(question, ai_answer, context)
                    semantic = cross["final"]  # None nếu disagree/unavailable
                    if cross["consensus"] == "disagree":
                        failures.append("multi_llm_disagreement")
                except Exception as _cc_err:
                    # [A2] Crosscheck lỗi phải LOG RÕ trước khi fallback single
                    # cascade — không được nuốt im lặng nữa.
                    logger.warning(
                        "[M2/A2] multi-LLM crosscheck failed (%s: %s) — fallback to single judge cascade",
                        type(_cc_err).__name__,
                        _cc_err,
                    )
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
            "slm_responses": slm_responses_list,
                "evidence": {
                    "governance_decision": "ESCALATE",
                },
            }

        return {
            "verdict": "PASS" if is_pass else "FAIL",
            "confidence": 0.85 if is_pass else 0.0,
            "deterministic_confidence": 1.0 if is_structurally_pass else 0.0,
            "semantic_confidence": 0.85 if is_pass else 0.0,
            "cross_model_agreement": not escalated,
            "reasoning": "Delegated to IndependentVerifier and LLM Semantic Judge",
            "cycle_count": cycle_count,
            "failures": failures,
            "final_answer": ai_answer,
            "slm_responses": slm_responses_list,
            "evidence": {
                "governance_decision": "UPHOLD" if is_pass else "KILL"
            }
        }

    async def judge_async(self, question: str, ai_answer: str = "", cycle_count: int = 0, context: str = "", **kwargs) -> dict[str, Any]:
        """Asynchronous judge interface."""
        from scp.core.postcondition_schema import PostconditionSchema
        from scp.runtime.judge_llm import _llm_judge_async

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

        tier1 = tier1_check(question, ai_answer, context)
        slm_responses_list = []
        if not tier1.passed:
            failures.extend(tier1.failures)
        elif is_structurally_pass and ai_answer:
            try:
                from scp.data_sources.domain_classifier import classify_top1
                domain = classify_top1(question)
                expert = self.domain_experts.get(domain)
                if expert:
                    resp = expert.predict(question)
                    if getattr(resp, "answer", None):
                        context += f"\n[SYSTEM EXPERT DATA] For {domain}: {resp.answer}"
                        slm_responses_list.append(resp.__dict__)
            except Exception as e:
                import logging
                logging.getLogger("scp.judge").debug(f"Expert injection failed: {e}")

            import os as _os
            if _os.environ.get("SCP_MULTI_LLM_CROSSCHECK", "1") == "1":
                try:
                    from scp.runtime.multi_llm_crosscheck import cross_verify
                    cross = await cross_verify(question, ai_answer, context)
                    semantic = cross["final"]
                    if cross["consensus"] == "disagree":
                        failures.append("multi_llm_disagreement")
                except Exception as _cc_err:
                    semantic = await _llm_judge_async(question, ai_answer, context)
            else:
                semantic = await _llm_judge_async(question, ai_answer, context)
                
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
                "slm_responses": slm_responses_list,
                "evidence": {"governance_decision": "ESCALATE"},
            }

        return {
            "verdict": "PASS" if is_pass else "FAIL",
            "confidence": 0.85 if is_pass else 0.0,
            "deterministic_confidence": 1.0 if is_structurally_pass else 0.0,
            "semantic_confidence": 0.85 if is_pass else 0.0,
            "cross_model_agreement": not escalated,
            "reasoning": "Delegated to IndependentVerifier and LLM Semantic Judge",
            "cycle_count": cycle_count,
            "failures": failures,
            "final_answer": ai_answer,
            "slm_responses": slm_responses_list,
            "evidence": {"governance_decision": "UPHOLD" if is_pass else "KILL"}
        }

    async def judge_with_react_fallback(self, *args, **kwargs) -> dict[str, Any]:
        return await self.judge_async(*args, **kwargs)

    def get_stats(self) -> dict:
        return {"total_judged": self.judged_count, "total_failed": self.fail_count}

    def analyze_session_rogue(self, *args, **kwargs) -> dict | None:
        return None

    # Stubs for legacy interfaces so we don't break import sites
    async def run_threat_simulation(self, *args, **kwargs): pass
    async def run_threat_intel_crawl(self, *args, **kwargs): return []
    def get_v98_status(self): return {}
    def get_v100_status(self): return {}
    async def run_scheduled_crawl(self, *args, **kwargs): return {}
    async def schedule_v100_background_jobs(self): pass
