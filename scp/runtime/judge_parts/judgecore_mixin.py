from scp.runtime.judge_parts.phases.context import JudgeContext
from scp.runtime.judge_parts.phases.phase0_setup import Phase0SetupMixin
from scp.runtime.judge_parts.phases.phase1_kb_retrieval import Phase1KbRetrievalMixin
from scp.runtime.judge_parts.phases.phase2_input_detection import Phase2InputDetectionMixin
from scp.runtime.judge_parts.phases.phase3_route import Phase3RouteMixin
from scp.runtime.judge_parts.phases.phase4_call_slms import Phase4CallSlmsMixin
from scp.runtime.judge_parts.phases.phase6_reality_check import Phase6RealityCheckMixin
from scp.runtime.judge_parts.phases.phase7_build_verdict import Phase7BuildVerdictMixin
from scp.runtime.judge_parts.phases.phase8_counter_response import Phase8CounterResponseMixin
from scp.runtime.judge_parts.phases.phase9_claim_extraction import Phase9ClaimExtractionMixin

""" JudgeVerdict, _AllowedByWatchlist
SCP V90 — Reality Judge Module
Cross-check SLMs, verify with reality, produce final verdicts.
Extracted from engine.py for modularity.

[G4-FIX P0-12] REALITY-CHECK ON THE "10-PHASE PIPELINE" CLAIM:
The project doc (SCP_FULL_CONTEXT_FOR_AI.md §2.2) claims judge.judge() is a
"10-phase pipeline" (Phase 1 DoS → 2 Multimodal → 3 Chatbot → 4 SmartClassifier
→ 5 SLM → 6 KB → 7 Reality → 8 Consistency → 9 Governance → 10 Antibody →
11 API boundary). That claim is FICTION. The ACTUAL judge() method (this file,
L74-2305, 2232 LOC, CC≈300) is a single god method with ~27 distinct phases
whose inline numbering is contradictory (PHASE 1 / STEP 0 / Step 1 / Step 2 /
Step 5.5 / Step 6 / Step 7 / Step 9 / STEP 9-again / PHASE 6 / PHASE 6.5 /
PHASE 10 / PHASE 11 — see judge() docstring for the full table).

`scp/runtime/judge_parts/judge_phases.py` defines only 6 phases and is NOT
wired into THIS method. It runs in SHADOW MODE from judge.py:927 (the async
wrapper `judge_async`) for comparison logging only — never sets the production
verdict. See that file's docstring for its honest status.

Full split of judge() into 10 phase modules = 21-day refactor, DEFERRED
(worklog Task G4-C). This file documents reality instead of pretending.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from scp.core.db_manager import (
    db_exec,
)
from scp.core.evidence_filter import filter_slm_responses
from scp.meta.severity import Severity
from scp.runtime.judge_parts.types import JudgeVerdict, _AllowedByWatchlist

# [Task 19-C] TYPE_CHECKING import — RealityJudge is the parent class that
# mixes in JudgeCoreMixin. Referencing it directly (self._extract_value)
# creates a circular import at runtime. TYPE_CHECKING block makes the name
# available to static analyzers (ruff/mypy) without runtime cost.
if TYPE_CHECKING:
    pass

from scp.meta.scp_meta import SCPMeta as _SCPMeta  # [Gà §10] — wired into judge()

logger = logging.getLogger("scp.judge")


# [V5.3-WIRE] multi_llm_check integration — opt-in via SCP_MULTI_LLM_CHECK=1 env var.
# TẠI SAO: DNA SCP #20 "ảo giác đồng thuận" — 100 AI cùng kết luận chưa chắc 100
# nguồn độc lập. Cross-check giữa 2-3 LLM providers (OpenRouter + Groq) để phát
# hiện disagreement. Default OFF để không tăng latency khi không cần.
# Lazy singleton — chỉ instantiate khi env var ON.
_MULTI_LLM_CHECKER_SINGLETON = None
_MULTI_LLM_CHECKER_LOCK = __import__("threading").Lock()


def _get_multi_llm_checker():
    """Lazy singleton for MultiLLMChecker. Returns None if env var OFF."""
    global _MULTI_LLM_CHECKER_SINGLETON
    if os.environ.get("SCP_MULTI_LLM_CHECK", "0") != "1":
        return None
    if _MULTI_LLM_CHECKER_SINGLETON is None:
        with _MULTI_LLM_CHECKER_LOCK:
            if _MULTI_LLM_CHECKER_SINGLETON is None:
                try:
                    from scp.meta.multi_llm_check import MultiLLMChecker
                    _MULTI_LLM_CHECKER_SINGLETON = MultiLLMChecker()
                    logger.info("[V5.3-WIRE] MultiLLMChecker initialized — adversary answers will be cross-checked")
                except Exception as e:
                    logger.warning(f"[V5.3-WIRE] MultiLLMChecker init failed: {e} — multi-LLM check disabled")
                    _MULTI_LLM_CHECKER_SINGLETON = False
    return _MULTI_LLM_CHECKER_SINGLETON if _MULTI_LLM_CHECKER_SINGLETON is not False else None


# [V104.42 #AH] Internal signal — source passed watchlist check, proceed to INSERT

def _build_governance_antibody_results(slm_responses: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Translate SLM response records into Governance's canonical format.

    Provider records use ``error`` as a transport/status field, whereas
    Governance consumes policy severities. The adapter must therefore emit a
    canonical ``Severity`` value and keep failures as ``passed=False``.
    """
    results: list[dict[str, Any]] = []
    for response in slm_responses or []:
        has_error = "error" in response
        confidence = response.get("confidence", 0.0)
        results.append({
            "passed": has_error is False and confidence >= 0.5,
            "severity": Severity.MEDIUM.value if has_error else (
                Severity.WARNING.value if confidence < 0.5 else Severity.INFO.value
            ),
            "antibody": response.get("antibody_name", response.get("slm_name", "unknown")),
            "details": response.get("details", response.get("error", response.get("reasoning", ""))),
        })
    return results


# ============================================================
# JUDGE VERDICT
# ============================================================
@dataclass

# ============================================================
# REALITY JUDGE — Cross-check SLMs + Verify với Reality
# ============================================================


class JudgeCoreMixin(Phase0SetupMixin, Phase1KbRetrievalMixin, Phase2InputDetectionMixin, Phase3RouteMixin, Phase4CallSlmsMixin, Phase6RealityCheckMixin, Phase7BuildVerdictMixin, Phase8CounterResponseMixin, Phase9ClaimExtractionMixin):
    """Mixin for RealityJudge — provides judge."""
    def judge(self, question: str, ai_answer: str = "", cycle_count: int = 0,
              source: str = "", v98_context: dict[str, Any] | None = None,
              domain_override: str | None = None):
        ctx = JudgeContext(
            question=question,
            ai_answer=ai_answer,
            cycle_count=cycle_count,
            source=source,
            v98_context=v98_context,
            domain_override=domain_override
        )
        res = self._phase0_setup(ctx)
        if res is not None:
            return res
        res = self._phase1_kb_retrieval(ctx)
        if res is not None:
            return res
        res = self._phase2_input_detection(ctx)
        if res is not None:
            return res
        res = self._phase3_route(ctx)
        if res is not None:
            return res
        res = self._phase4_call_slms(ctx)
        if res is not None:
            return res
        res = self._phase6_reality_check(ctx)
        if res is not None:
            return res
        res = self._phase7_build_verdict(ctx)
        if res is not None:
            return res
        res = self._phase8_counter_response(ctx)
        if res is not None:
            return res
        res = self._phase9_claim_extraction(ctx)
        if res is not None:
            return res
        return ctx.verdict
