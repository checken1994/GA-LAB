from typing import Any
from scp.runtime.judge_parts.phases.context import JudgeContext
import time
from datetime import datetime
import os
import logging
logger = logging.getLogger(__name__)

class Phase1KbRetrievalMixin:
    def _phase1_kb_retrieval(self, ctx: JudgeContext) -> Any:
            #  PHASE 1: KNOWLEDGE RETRIEVAL — check KB before SLM
            # ============================================================
            ctx.v100_kb_hits = []
            with ctx._v100_timer.phase("knowledge"):
                if self.domain_knowledge_store:
                    try:
                        ctx.v100_kb_hits = self.domain_knowledge_store.search(ctx.question, domain="", limit=3)
                        if ctx.v100_kb_hits:
                            logger.debug(f" KB hit: {len(ctx.v100_kb_hits)} records for '{ctx.question[:50]}'")
                            # [V104.43 #BI] TẠI SAO: was only logging KB hits, never short-circuit.
                            # Comment "check KB before SLM" was misleading — KB was metadata only.
                            # Fix: if highest-tier hit with high confidence, use it as answer directly.
                            ctx._best_hit = ctx.v100_kb_hits[0]  # sorted by tier+conf+recency
                            ctx._hit_tier = getattr(ctx._best_hit, 'source_tier', 9)
                            ctx._hit_conf = getattr(ctx._best_hit, 'confidence', 0)
                            if ctx._hit_tier <= 2 and ctx._hit_conf >= 0.85:
                                # AXIOMATIC/AUTHORITATIVE tier + high conf → short-circuit
                                ctx.final_answer = getattr(ctx._best_hit, 'answer', '')
                                ctx.confidence = ctx._hit_conf
                                ctx.verdict_type = "PASS"
                                ctx.reasoning = f"KB short-circuit: tier={ctx._hit_tier} conf={ctx._hit_conf:.2f} (cached authoritative)"
                                logger.info(f"[V104.43 #BI] KB short-circuit: tier={ctx._hit_tier} conf={ctx._hit_conf:.2f}")
                    except Exception as e:
                        logger.debug(f" KB search error: {e}")
            
            #  Check 10s timeout after knowledge phase
            try:
                check_timeout(ctx._v100_timer.finish(), "knowledge")
            except QueryTimeoutError as e:
                logger.warning(f"Silent except: {e}")  # Don't crash — just log and continue
            
            # [V104.46 #BI] KB short-circuit was previously here — moved BELOW
            # Step 0a-0c security checks by FIX-CRIT-27 BUG 3 (was bypassing ALL
            # V98 security: MemoryPoisoningGuard, AttackPatternMemory,
            # UnifiedDetector, ThreatDetector — an attacker who poisoned the KB
            # once got permanent PASS bypass).
            # ============================================================
        
