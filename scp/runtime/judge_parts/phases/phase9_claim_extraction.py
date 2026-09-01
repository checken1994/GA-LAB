from typing import Any
from scp.runtime.judge_parts.phases.context import JudgeContext
import time
from datetime import datetime
import os
import logging
logger = logging.getLogger(__name__)

class Phase9ClaimExtractionMixin:
    def _phase9_claim_extraction(self, ctx: JudgeContext) -> Any:
            #  PHASE 6: CLAIM EXTRACTION + ANTIBODIES + VERIFICATION
            # ============================================================
            with ctx._v100_timer.phase("extraction"):
                #  DomainAntibodySystem — chạy 38 antibodies với domain filter
                # [Task 45-B] Antibody block extracted to _run_antibodies() to reduce judge() CC.
                # [G5-FIX] Pass ai_answer so closure words in the AI's ORIGINAL claim
                # are detected (not just verdict.final_answer which is SCP's response).
                self._run_antibodies(ctx.verdict, ctx.question, ctx.ai_answer)
            
                if self.claim_extractor and ctx.verdict.ctx.final_answer:
                    try:
                        ctx.v100_claims = self.claim_extractor.extract(ctx.verdict.ctx.final_answer, ctx.question)
                        if self.claim_verifier and ctx.v100_claims:
                            #  Build ground truth from KB hits + SLM evidence.
                            # BEFORE: only KB hits → ground_truth empty for new questions
                            #         → all claims "verified=None" → PASS (false confidence).
                            # AFTER:  SLM evidence (value, source, unit) normalized into
                            #         ground_truth. Claims verified against REAL evidence.
                            # DNA #4 (Evidence-First) + #26 (Reality > Model).
                            ctx._filtered_slm_responses, ctx._evidence_filter_report = filter_slm_responses(
                                ctx.question, ctx.slm_responses or []
                            )
                            if ctx._evidence_filter_report.get("droppedCount"):
                                ctx.slm_responses = ctx._filtered_slm_responses
                                ctx.verdict.ctx.slm_responses = ctx._filtered_slm_responses
                            ctx.verdict.evidence["evidence_consistency"] = ctx._evidence_filter_report
                            ctx.ground_truth = {}
                            # 1. KB hits (existing)
                            for ctx.hit in ctx.v100_kb_hits:
                                ctx.ground_truth[ctx.hit.ctx.source] = ctx.hit.answer
                            # 2. SLM responses — extract evidence from each SLM
                            #  BEFORE: SLM evidence DISCARDED. ClaimVerifier
                            #   only had KB hits. If no KB hit → claims unverified → PASS.
                            #   AFTER: SLM evidence flows into ground_truth.
                            for ctx._slm_resp in (ctx.slm_responses or []):
                                if "error" in ctx._slm_resp or not ctx._slm_resp.get("answer"):
                                    continue
                                ctx._slm_name = (
                                    ctx._slm_resp.get("slm_name")
                                    or ctx._slm_resp.get("source")
                                    or ctx._slm_resp.get("domain", "unknown")
                                )
                                ctx._slm_evidence = ctx._slm_resp.get("evidence") or {}
                                # If SLM has structured evidence (value + source), add
                                if isinstance(ctx._slm_evidence, dict):
                                    if ctx._slm_evidence.get("value") is not None:
                                        ctx.ground_truth[f"{ctx._slm_name}_value"] = ctx._slm_evidence["value"]
                                        if ctx._slm_evidence.get("unit"):
                                            ctx.ground_truth[f"{ctx._slm_name}_unit"] = ctx._slm_evidence["unit"]
                                    if ctx._slm_evidence.get("source"):
                                        ctx.ground_truth[f"{ctx._slm_name}_source"] = ctx._slm_evidence["source"]
                                # [Fix 4-b-002 / DNA #2, #5, #22, #26] DO NOT add the SLM's
                                # full answer text as a ground_truth key. Reason: ClaimExtractor
                                # extracts claims FROM THIS SAME final_answer text, and
                                # _verify_entity does substring matching against
                                # ground_truth.values() — so the SLM would verify its own
                                # claim against its own paraphrased answer (self-verification,
                                # DNA #5 ảo giác đồng thuận). R17-FIX-2 UPHOLD-when-unverified
                                # then never fires because verified=True on most entity claims.
                                # Structured evidence ({value},{unit},{source}) above is the
                                # ONLY legitimate ground-truth contribution from an SLM.
                                # Removed line: ground_truth[_slm_name] = _slm_resp.get("answer", "")
                            ctx.v100_claims = self.claim_verifier.verify(ctx.v100_claims, ctx.ground_truth)
                            ctx.v100_claim_summary = self.claim_verifier.summarize(ctx.v100_claims)
                            ctx.verdict.evidence["v100_claims"] = ctx.v100_claim_summary
            
                            #  Governance based on claim verification status.
                            # BEFORE: only ×0.5 if claims REFUTED. If claims UNVERIFIED
                            #   (verified=None) → NO action → PASS stays PASS (false confidence).
                            # AFTER: UPHOLD (UNKNOWN) if >50% claims unverified.
                            # DNA #22 (PASS ≠ TRUE): "can't verify" ≠ "verified".
                            ctx._refuted = ctx.v100_claim_summary.get("refuted", 0)
                            ctx._verified = ctx.v100_claim_summary.get("verified", 0)
                            ctx._unverified = ctx.v100_claim_summary.get("unverified", 0)
                            ctx._total = ctx._verified + ctx._unverified + ctx._refuted
            
                            if ctx._refuted > 0:
                                # Claims REFUTED — confidence ×0.5 (existing behavior)
                                ctx.verdict.ctx.confidence *= 0.5
                                ctx.verdict.ctx.reasoning += f" |  {ctx._refuted} claims refuted"
            
                            if ctx._total > 0 and ctx._unverified / ctx._total > 0.5 and not (ctx._math_verdict == "PASS" and ctx.verdict.ctx.verdict == "PASS"):
                                # >50% claims UNVERIFIED — UPHOLD (can't confirm answer)
                                logger.warning(
                                    f" {ctx._unverified}/{ctx._total} claims unverified — "
                                    f"UPHOLD verdict from {ctx.verdict.ctx.verdict} to UNKNOWN"
                                )
                                if ctx.verdict.ctx.verdict == "PASS":
                                    ctx.verdict.ctx.verdict = "UNKNOWN"
                                    ctx.verdict.ctx.confidence = min(ctx.verdict.ctx.confidence, 0.4)
                                    ctx.verdict.ctx.reasoning += (
                                        f" | [R17] UPHOLD: {ctx._unverified}/{ctx._total} claims unverified"
                                    )
                    except Exception as e:
                        logger.debug(f" Claim extraction error: {e}")
            
            # ============================================================
            #  PHASE 6.5: LOGICAL AUDITOR — kiểm tra lỗi logic sâu
            # ============================================================
            with ctx._v100_timer.phase("falsification"):  # reuse falsification phase
                if self.logical_auditor and self.logical_auditor.should_audit(ctx.verdict.ctx.verdict, ctx.verdict.ctx.final_answer):
                    # [V104.18 #4 FIX] Use ThreadPoolExecutor (was: pass when loop running)
                    try:
                        import asyncio as _a
                        import concurrent.futures as _cf
                        ctx._pool = _cf.ThreadPoolExecutor(max_workers=1)
                        ctx.audit_result = ctx._pool.submit(
                            _a.run,
                            self.logical_auditor.audit(
                                text_to_audit=ctx.verdict.ctx.final_answer,
                                context=f"Question: {ctx.question[:200]}",
                            )
                        ).ctx.result(timeout=30)
                        self._apply_logical_audit(ctx.verdict, ctx.audit_result)
                        ctx._pool.shutdown(wait=False)
                    except Exception as e:
                        logger.debug(f" LogicalAuditor error: {e}")
            
            #  SelfQuestioningEngine — SCP tự hỏi "Tại Sao?"
            if self.self_questioning and ctx.verdict.ctx.verdict in ("PASS", "FAIL", "SPECULATIVE"):
                try:
                    ctx.sq_result = self.self_questioning.ctx.question(
                        question=ctx.question,
                        answer=ctx.verdict.ctx.final_answer,
                        verdict=ctx.verdict.ctx.verdict,
                        confidence=ctx.verdict.ctx.confidence,
                        reasoning=ctx.verdict.ctx.reasoning,
                        slm_responses=ctx.verdict.ctx.slm_responses,
                        evidence=ctx.verdict.evidence,
                        domain=ctx.verdict.ctx.domain,
                    )
                    ctx.verdict.evidence["v106_self_questioning"] = ctx.sq_result.to_dict()
                    if ctx.sq_result.verdict_challenged:
                        ctx.verdict.ctx.confidence = ctx.sq_result.revised_confidence
                        ctx.verdict.ctx.reasoning += f" | [V106 SelfQuestion] {ctx.sq_result.self_critique[:100]}"
                except Exception as e:
                    logger.debug(f" SelfQuestioning error: {e}")
            
            # ============================================================
            #  PHASE 10: LEARNING — KB save on PASS + H8 bypass analysis
            # ============================================================
            with ctx._v100_timer.phase("learning"):
                # [V100 FIX] Save PASS to KnowledgeStore (V63 bug: 0 knowledge saved)
                if self.domain_knowledge_store and ctx.verdict.ctx.verdict == "PASS" and ctx.verdict.ctx.final_answer:
                    try:
                        self.domain_knowledge_store.store(
                            question=ctx.question[:500],
                            answer=ctx.verdict.ctx.final_answer[:500],
                            domain=ctx.verdict.ctx.domain or "general",
                            source="scp_learned",
                            source_url="",
                            confidence=ctx.verdict.ctx.confidence,
                            collected_by="on_demand",
                            verified_by=["scp_pipeline"],
                        )
                    except Exception as e:
                        logger.debug(f" KB save error: {e}")
            
                #  Record normal question for H8 FP testing
                if self.h8_redteam and ctx.verdict.ctx.verdict == "PASS":
                    try:
                        self.h8_redteam.record_normal_question(ctx.question[:200])
                    except Exception as e:
                        # [ROOT-FIX 5] Was `except Exception as e: pass` — swallowed H8 FP
                        # recording errors silently → false-positive baseline never grows.
                        logger.warning(f"[judge] h8_redteam.record_normal_question failed: {e}")
            
                #  H8 RedTeamBridge — bypass detection + analysis chiều 2
                if self.h8_redteam:
                    try:
                        ctx.h8_record = self.h8_redteam.record_bypass(
                            question=ctx.question,
                            answer=ctx.verdict.ctx.final_answer,
                            verdict=ctx.verdict.ctx.verdict,
                            classification=ctx.v98_classification.to_dict() if ctx.v98_classification else {"actor": "human", "confidence": 0.5},
                            source=ctx.source or "unknown",
                            attacker_ip=(ctx.v98_context or {}).get("ip", "internal"),
                        )
                        if ctx.h8_record:
                            ctx.verdict.evidence["v100_bypass_detected"] = True
                            ctx.verdict.evidence["v100_bypass_id"] = ctx.h8_record.bypass_id
                            ctx.verdict.evidence["v100_canary_token"] = ctx.h8_record.canary_token
                    except Exception as e:
                        logger.debug(f" H8 error: {e}")
            
            # ============================================================
            #  PHASE 11: OUTPUT — phase timings + KB hits in evidence
            # ============================================================
            with ctx._v100_timer.phase("output"):
                ctx.v100_timings = ctx._v100_timer.finish()
                ctx.verdict.evidence["v100_phase_timings"] = ctx.v100_timings.to_dict()
                ctx.verdict.evidence["v100_kb_hits"] = len(ctx.v100_kb_hits)
                if ctx.v100_kb_hits:
                    ctx.verdict.evidence["v100_kb_top_hit"] = {
                        "question": ctx.v100_kb_hits[0].ctx.question[:100],
                        "answer": ctx.v100_kb_hits[0].answer[:100],
                        "source": ctx.v100_kb_hits[0].ctx.source,
                        "tier": ctx.v100_kb_hits[0].source_tier,
                        "confidence": ctx.v100_kb_hits[0].ctx.confidence,
                    }
            
            # [V104.45 #BV] TẠI SAO: healing was only in SCPV14.process (not on /ask).
            # Fix: run healing monitor + heal after verdict, before return.
            # [V104.45 #BW] TẠI SAO: old healing success_rate measured SQL DELETE success,
            # not whether verdict improved. Fix: record verdict before+after healing.
            if self.healing_engine and ctx.verdict.ctx.verdict in ("FAIL", "CONFLICT", "UNKNOWN"):
                try:
                    ctx._system_state = {
                        "verdict": ctx.verdict.ctx.verdict,
                        "confidence": ctx.verdict.ctx.confidence,
                        "domain": ctx.verdict.ctx.domain or "general",
                        "question": ctx.question[:200],
                    }
                    ctx._issues = self.healing_engine.monitor(ctx._system_state)
                    if ctx._issues and ctx._issues.get("issues"):
                        for ctx._issue in ctx._issues["issues"][:3]:  # limit to 3 issues per request
                            try:
                                ctx._heal_result = self.healing_engine.heal(ctx._issue)
                                # [SCP-DNA-FIX R5-6] TẠI SAO: was reading strategy
                                # from `_issue` — but healing_v14.monitor() NEVER
                                # sets a `strategy` key on issues (it only sets
                                # `type`, `severity`, `details`, `source`,
                                # `timestamp`). The actual strategy NAME is set by
                                # healing_v14.heal() — it returns
                                # `{"success": ..., "strategy": strategy.name, ...}`
                                # when a strategy is found, OR
                                # `{"success": False, "message": "No strategy found", ...}`
                                # (no `strategy` key) when none matched.
                                # REALITY EVIDENCE (PowerShell.txt 5169 lines, 43 min):
                                # 1108/1108 healing logs said `strategy=unknown`
                                # even though strategies ARE being applied (e.g.
                                # scale_resource, reduce_error, retry_slm,
                                # switch_domain, reality_fallback, cache_refresh).
                                # Fix: read `strategy` from `_heal_result` (the
                                # actual healer's response), not from `_issue`.
                                # Use "NO_STRATEGY" sentinel to match healing_v14's
                                # internal naming when no strategy matched the issue.
                                ctx._strategy = (ctx._heal_result.get("strategy", "NO_STRATEGY")
                                             if ctx._heal_result else "NO_STRATEGY")
                                ctx._success = ctx._heal_result.get("success", False) if ctx._heal_result else False
            
                                # [V104.47 #10]  TẠI SAO: V104.45 measured
                                # verdict_improved as "issue type was confidence-related" —
                                # still a proxy. V104.47 #10 added a real re-check (re-run
                                # primary SLM, compare confidence) BUT gated it on issue
                                # types `("low_confidence", "unknown_verdict")` — which the
                                # healing engine NEVER emits. monitor() actually emits:
                                #   slm_confidence_low, all_slm_fail, high_latency,
                                #   high_error_rate, slm_error, stale_data
                                # → the re-check was DEAD (never ran) → verdict_improved
                                # always False → strategy success_rate stayed a SQL-execution
                                # proxy (bug BW not fixed). Fix: match the REAL issue types
                                # that warrant a confidence re-check.
                                ctx._verdict_improved = False
                                ctx._RECHECK_ISSUE_TYPES = (
                                    "slm_confidence_low",  # confidence < 0.3
                                    "all_slm_fail",        # UNKNOWN + conf < 0.2
                                    "slm_error",           # SLM returned error → retry may help
                                    "stale_data",          # CONFLICT → cache clear + re-run may help
                                )
                                if ctx._success and ctx._issue.get("type") in ctx._RECHECK_ISSUE_TYPES:
                                    try:
                                        # Lightweight re-check: re-run primary SLM only (not full judge)
                                        ctx._heal_slm_name = ctx.primary.get("slm_name", "") if ctx.primary else ""
                                        ctx._heal_domain = ctx.verdict.ctx.domain or "general"
                                        if ctx._heal_slm_name and ctx._heal_slm_name in self.slms:
                                            ctx._re_slm = self.slms[ctx._heal_slm_name]
                                            ctx._re_result = ctx._re_slm.predict(ctx.question)
                                            ctx._new_conf = ctx._re_result.ctx.confidence if hasattr(ctx._re_result, 'confidence') else 0
                                            if ctx._new_conf > ctx.confidence:
                                                ctx._verdict_improved = True
                                                logger.info(f"[V104.47 #10] Healing improved: {ctx.confidence:.2f} → {ctx._new_conf:.2f}")
                                    except Exception as e:
                                        logger.warning(f"Silent except: {e}")  # re-check failed, keep _verdict_improved = False
                                ctx._heal_result["verdict_improved"] = ctx._verdict_improved
            
                                ctx.verdict.evidence.setdefault("healing_actions", []).append({
                                    "strategy": ctx._strategy,
                                    "success": ctx._success,
                                    "verdict_improved": ctx._verdict_improved,
                                })
                                logger.info(f"[V104.45 #BV] Healing: strategy={ctx._strategy} success={ctx._success} improved={ctx._verdict_improved}")
                            except Exception as _he:
                                logger.debug(f"[V104.45 #BV] Healing strategy error: {_he}")
                except Exception as e:
                    logger.debug(f"[V104.45 #BV] Healing monitor error: {e}")
            
            # [V5.8-OPT] Wire source_reputation.record_outcome — TẠI SAO:
            # scp_reputation.sqlite had 0 rows because the reputation system
            # existed (ReputationStore class, schema, SourceWatchlist wrapper)
            # but NOTHING was calling it on every verdict. The only callers were
            # on_fact_invalidated (Healing Cascade) and on_fact_committed
            # (KB ingestion) — both rare events. So reputation stayed empty.
            #
            # Fix: after verdict is finalized (post-healing, post-governance),
            # call record_outcome() for every source that contributed evidence.
            # was_correct = True iff verdict == "PASS" (matches task spec:
            # "True if verdict PASS, False if FAIL/KILL").
            #
            # This populates source_domain_reputation table ADDITIVELY —
            # does NOT touch existing source_reputation table or break any
            # current caller. Best-effort: any failure is logged + swallowed
            # (MUST NOT break /ask over a reputation write).
            try:
                ctx._rep_store = None
                # Reuse existing ReputationStore if SourceWatchlist was initialized
                if self._source_watchlist is not None:
                    ctx._rep_store = getattr(self._source_watchlist, "store", None)
                if ctx._rep_store is None:
                    # Fallback: construct a fresh store (opens its own sqlite conn)
                    from scp.knowledge.source_reputation import ReputationStore as _RS
                    ctx._rep_store = _RS()
            
                ctx._v58_was_correct = (ctx.verdict.ctx.verdict == "PASS")
                ctx._v58_domain = ctx.verdict.ctx.domain or "general"
                ctx._v58_sources_seen: set = set()
            
                # Collect sources from SLM responses (each may carry evidence.source)
                for ctx._r in (ctx.verdict.ctx.slm_responses or []):
                    try:
                        ctx._ev = ctx._r.get("evidence") or {}
                        ctx._src = ctx._ev.get("source") or ctx._r.get("slm_name")
                        if ctx._src and isinstance(ctx._src, str) and ctx._src not in ctx._v58_sources_seen:
                            ctx._v58_sources_seen.add(ctx._src)
                            try:
                                ctx._rep_store.record_outcome(ctx._src, ctx._v58_domain, ctx._v58_was_correct)
                            except Exception as _re:
                                logger.debug(f"[V5.8-OPT] record_outcome failed for SLM source={ctx._src!r}: {_re}")
                    except Exception:  # noqa: S112
                        continue  # defensive — bad SLM response shouldn't break reputation
            
                # Also record reality_check source if present (v13.db, REST Countries, etc.)
                try:
                    ctx._rc = (ctx.verdict.evidence or {}).get("reality_check")
                    if isinstance(ctx._rc, dict):
                        ctx._rc_src = ctx._rc.get("source")
                        if ctx._rc_src and isinstance(ctx._rc_src, str) and ctx._rc_src not in ctx._v58_sources_seen:
                            ctx._v58_sources_seen.add(ctx._rc_src)
                            try:
                                ctx._rep_store.record_outcome(ctx._rc_src, ctx._v58_domain, ctx._v58_was_correct)
                            except Exception as _re:
                                logger.debug(f"[V5.8-OPT] record_outcome failed for reality source={ctx._rc_src!r}: {_re}")
                except Exception as e:
                    logger.warning(f"Silent except: {e}")
            
                # Stash forensic trace in verdict.evidence (small, useful for debugging)
                if ctx._v58_sources_seen:
                    try:
                        ctx.verdict.evidence["v58_source_reputation_recorded"] = {
                            "sources": sorted(ctx._v58_sources_seen),
                            "domain": ctx._v58_domain,
                            "was_correct": ctx._v58_was_correct,
                            "verdict": ctx.verdict.ctx.verdict,
                        }
                    except Exception as e:
                        logger.warning(f"Silent except: {e}")  # verdict.evidence might be immutable in some test paths
            except Exception as e:
                logger.debug(f"[V5.8-OPT] source_reputation wire failed (non-fatal): {e}")
            
            
            # [Gà §10] SCP-META hội đồng phản biện — 3 systems vote
            try:
                ctx._meta = _SCPMeta()
                ctx._meta_review = ctx._meta.review(ctx.question, ctx.verdict.ctx.verdict)
                if ctx._meta_review.council_decision.value == "SKIP":
                    ctx.verdict.ctx.verdict = "UNKNOWN"
                    ctx.verdict.ctx.reasoning += ". META: SKIP"
                elif ctx._meta_review.council_decision.value == "DEFER_HUMAN":
                    ctx.verdict.ctx.verdict = "UNKNOWN"
                    ctx.verdict.ctx.reasoning += ". META: DEFER_HUMAN"
            except Exception as _meta_err:
                import logging as _logging
                _logging.getLogger("scp.judge").debug(f"SCPMeta review failed: {_meta_err}")
            
            return ctx.verdict
        
