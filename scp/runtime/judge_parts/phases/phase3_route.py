from typing import Any
from scp.runtime.judge_parts.phases.context import JudgeContext
import time
from datetime import datetime
import os
import logging
logger = logging.getLogger(__name__)

class Phase3RouteMixin:
    def _phase3_route(self, ctx: JudgeContext) -> Any:
            # Step 1: Route -> SLMs
            ctx.domains = self._route_question(ctx.question, domain_override=ctx.domain_override)
            
            # [V90 OPT] Skip PolicyApplier — minor effect, high overhead
            ctx.applied_principle_ids: list[int] = []
            ctx.adjusted_threshold = self.confidence_threshold
            
            # [V93.6] Apply DOMAIN_BIAS lessons from ExperienceEngine (lightweight, cheap TTL read)
            # Was: experiences learned lessons but never applied (3343 lessons, 0 applied)
            if ctx.domains:
                try:
                    ctx.exp_pol = self._get_exp_policies()
                    ctx.tolerances = ctx.exp_pol.get("domain_tolerances", {})
                    ctx.primary_dom = ctx.domains[0]
                    if ctx.primary_dom in ctx.tolerances:
                        # Higher tolerance -> lower the bar for PASS (domain known to be noisy/hard)
                        ctx.adjusted_threshold = min(0.9, self.confidence_threshold * ctx.tolerances[ctx.primary_dom])
                except Exception as e:
                    logger.debug(f"[V93.6] domain_tolerance apply error: {e}")
            
            # [V104.39 #A] TẠI SAO: V90 OPT disabled closed-loop via `if False`.
            # Re-enabled via env var SCP_ENABLE_CLOSED_LOOP=1 (opt-in).
            # Without this, PolicyApplier (lessons → threshold) is dead → no self-correction.
            # _enable_closed_loop defined at top of judge() (line ~1227) — shared by all.
            if ctx._enable_closed_loop and self.policy_applier and ctx.domains:
                try:
                    ctx.primary_dom = ctx.domains[0]
                    ctx.adjustment = self.policy_applier.get_adjustment(
                        ctx.question, ctx.primary_dom, base_threshold=self.confidence_threshold
                    )
                    ctx.adjusted_threshold = ctx.adjustment["confidence_threshold"]
                    ctx.adjustment.get("prefer_sources", [])
                    ctx.adjustment.get("avoid_sources", [])
                    ctx.applied_principle_ids = ctx.adjustment.get("applied_principle_ids", [])
                except Exception as e:
                    logger.debug(f"PolicyApplier error: {e}")
            
            #  Apply ErrorStoreIndex similar-FAIL threshold boost AFTER
            # domain-tolerance + PolicyApplier resets. TẠI SAO: V104.44 #BX computed
            # `adjusted_threshold = max(0.65, self.confidence_threshold + 0.1)` but it
            # was immediately overwritten by lines 1509 (self.confidence_threshold) and
            # 1520/1534 (domain tolerance + PolicyApplier). Storing as a separate boost
            # and applying here ensures it actually takes effect.
            if ctx._es_index_threshold_boost > 0:
                ctx.adjusted_threshold = min(0.95, ctx.adjusted_threshold + ctx._es_index_threshold_boost)
            
            # [V90 OPT] Skip VerdictPredictor — minor effect, high overhead
            ctx.prediction_skip_api = False
            ctx.prediction_verdict = None
            # [V104.39 #A] Re-enabled VerdictPredictor (was: if False)
            if ctx._enable_closed_loop and self.predictor and ctx.domains:
                try:
                    ctx.pred = self.predictor.predict(ctx.question, ctx.domains[0], ctx.ai_answer)
                    ctx.prediction_verdict = ctx.pred.ctx.verdict
                    if ctx.pred.skip_api and ctx.pred.ctx.confidence > 0.85:
                        ctx.prediction_skip_api = True
                except Exception as e:
                    logger.debug(f"VerdictPredictor error: {e}")
            
        
