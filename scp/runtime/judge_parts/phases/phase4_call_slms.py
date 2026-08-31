from typing import Any
from scp.runtime.judge_parts.phases.context import JudgeContext
import time
from datetime import datetime
import os
import logging
logger = logging.getLogger(__name__)

class Phase4CallSlmsMixin:
    def _phase4_call_slms(self, ctx: JudgeContext) -> Any:
            # Step 2: Gọi SLMs
            # [V32.1] PARALLEL SLM execution — chạy tất cả SLMs song song
            # Speedup: 4 SLMs × 500ms sequential = 2s → // = 500ms (4x faster)
            ctx.slm_responses = []
            
            def _call_slm(domain: str) -> dict:
                """Call 1 SLM, return response dict."""
                slm = self.slms.get(ctx.domain)
                if slm:
                    try:
                        # [V5.7-WHY] Change 2: WHY pre-routing — pass sources_to_query as hint.
                        # TẠI SAO: WHY engine created a VerificationPlan early (before SLMs
                        # run, see line ~1381). The plan's sources_to_query lists which
                        # sources WHY thinks are authoritative for this question (e.g.,
                        # ["Wikipedia", "LocalDB", "REST Countries API"]). Setting this
                        # as an attribute on the SLM lets SLMs that know about it
                        # prioritize those sources first. SLMs that don't read the
                        # attribute simply ignore it (PASSIVE — no behavior change).
                        # SAFETY: opt-in via SCP_WHY_PRE_ROUTE=1 (default OFF). Wrap in
                        # try/except — hint setting MUST NOT break SLM call. SLM logic
                        # is NOT changed — hint is purely advisory.
                        try:
                            if os.environ.get("SCP_WHY_PRE_ROUTE", "0") == "1" and ctx.why_plan:
                                slm.why_sources_hint = list(ctx.why_plan.sources_to_query)
                                logger.debug(
                                    f"[V5.7-WHY] pre-route hint set on {ctx.domain} SLM: "
                                    f"{ctx.why_plan.sources_to_query}"
                                )
                            else:
                                # Clear any stale hint from previous call (defensive)
                                if hasattr(slm, "why_sources_hint"):
                                    try:
                                        del slm.why_sources_hint  # [FALSE-POS-FIX] B043: delattr with constant string == del attr
                                    except Exception as e:
                                        logger.warning(f"Silent except: {e}")
                        except Exception as _hint_err:
                            logger.debug(f"[V5.7-WHY] pre-route hint set failed (non-fatal): {_hint_err}")
            
                        resp = slm.predict(ctx.question)
                        return {
                            "domain": ctx.domain,
                            "answer": resp.answer,
                            "confidence": resp.ctx.confidence,
                            "reasoning": resp.ctx.reasoning,
                            "evidence": resp.evidence,
                            "slm_name": resp.slm_name,
                            "processing_time": resp.processing_time,
                        }
                    except Exception as e:
                        return {
                            "domain": ctx.domain,
                            "error": str(e),
                            "confidence": 0.0,
                        }
                else:
                    # Domain has no SLM — use V13 RealityEngine directly
                    try:
                        ctx.v13_result = self.v13.process(ctx.question, ctx.ai_answer)
                        ctx.real_value = ctx.v13_result.ctx.real_value
                        ctx.source = ctx.v13_result.ctx.source or "v13"
                        if ctx.real_value is not None:
                            return {
                                "domain": ctx.domain,
                                "answer": f"= {ctx.real_value}",
                                "confidence": 0.85,
                                "reasoning": f"V13 RealityEngine: {ctx.source}",
                                "evidence": {"source": ctx.source, "value": ctx.real_value},
                                "slm_name": "V13Reality",
                                "processing_time": 0.0,
                            }
                    except Exception as e:
                        # [ROOT-FIX 5] Was `except Exception as e: pass` — swallowed V13
                        # RealityEngine errors silently → falls through to "no SLM" return.
                        logger.warning(f"[judge] V13Reality fallback failed: {e}")
                    return {"domain": ctx.domain, "error": "no SLM", "confidence": 0.0}
            
            if len(ctx.domains) == 1:
                #  Multi-SLM consensus: always add a second opinion
                # Was: only call 1 SLM → no cross-verification → "no ground truth"
                # Now: if only 1 domain routed, also call "universal" or "general" as 2nd opinion
                ctx.primary_domain = ctx.domains[0]
                # Don't add duplicate if primary IS universal/general
                if ctx.primary_domain not in ("universal", "general"):
                    ctx.domains.append("universal")
                ctx.slm_responses.append(_call_slm(ctx.domains[0]))
                if len(ctx.domains) > 1:
                    ctx.slm_responses.append(_call_slm(ctx.domains[1]))
            else:
                # [V32.1] Multiple domains — run in parallel
                from concurrent.futures import ThreadPoolExecutor, as_completed
                with ThreadPoolExecutor(max_workers=min(4, len(ctx.domains))) as ctx.executor:
                    ctx.future_to_domain = {ctx.executor.submit(_call_slm, d): d for d in ctx.domains}
                    for ctx.future in as_completed(ctx.future_to_domain, timeout=30):
                        try:
                            ctx.result = ctx.future.ctx.result(timeout=15)
                            ctx.slm_responses.append(ctx.result)
                        except Exception as e:
                            ctx.domain = ctx.future_to_domain[ctx.future]
                            ctx.slm_responses.append({
                                "domain": ctx.domain,
                                "error": str(e),
                                "confidence": 0.0,
                            })
            
            if not ctx.slm_responses:
                #  SLM không có answer → gọi LLM (Ollama/OpenRouter)
                if self.llm_client:
                    try:
                        import asyncio as _a
                        # Build context from KB hits
                        ctx.llm_context = ""
                        if ctx.v100_kb_hits:
                            ctx.llm_context = "\n".join(f"- {h.answer[:200]}" for h in ctx.v100_kb_hits[:3])
            
                        # [V104.19 #2 FIX] LLM fallback: always run via ThreadPoolExecutor
                        try:
                            import concurrent.futures as _cf
                            ctx._llm_pool = _cf.ThreadPoolExecutor(max_workers=1)
                            ctx.llm_answer, ctx.llm_model = ctx._llm_pool.submit(
                                _a.run,
                                self.llm_client.chat(ctx.question, context=ctx.llm_context, task="judge")
                            ).ctx.result(timeout=10)  # [V104.19 #3] was 30s, reduce to 10s
                            ctx._llm_pool.shutdown(wait=False)
                        except RuntimeError:
                            # [FIX-CRIT-27 BUG 2] was AFTER except Exception (unreachable — RuntimeError is subclass of Exception). Reorder: specific first.
                            ctx.llm_answer, ctx.llm_model = _a.run(
                                self.llm_client.chat(ctx.question, context=ctx.llm_context, task="judge")
                            )
                        except Exception as e:
                            ctx.llm_answer, ctx.llm_model = "", f"llm_error: {e}"
            
                        if ctx.llm_answer and "không khả dụng" not in ctx.llm_answer:
                            # LLM returned answer → use as final_answer, but with LOW confidence (needs verification)
                            return JudgeVerdict(
                                question=ctx.question, slm_responses=[],
                                final_answer=ctx.llm_answer[:2000],
                                confidence=0.3,  # LOW — LLM answer chưa verify
                                verdict="UNKNOWN",  # Still UNKNOWN — LLM answer needs verification
                                reasoning=f"SLM không có answer → LLM ({ctx.llm_model}) trả lời — chưa verify, confidence thấp",
                                evidence={"scope": "llm_fallback", "llm_model": ctx.llm_model},
                                domain=(ctx.domains[0] if ctx.domains else "unknown"),
                                cross_validation={}, slm_scores={}, timestamp=ctx.ts,
                            )
                    except Exception as e:
                        logger.debug(f" LLM fallback error: {e}")
            
                return JudgeVerdict(
                    question=ctx.question, slm_responses=[], final_answer="[SCP] Tôi không có đủ thông tin để trả lời câu hỏi này. Không có SLM nào có dữ liệu liên quan đến lĩnh vực này.",
                    confidence=0.0, verdict="UNKNOWN", reasoning="Không có SLM nào response — ngoài phạm vi kiến thức hiện có",
                    evidence={"scope": "out_of_scope"}, domain=(ctx.domains[0] if ctx.domains else "unknown"), cross_validation={}, slm_scores={},
                    timestamp=ctx.ts,
                )
            
            # Step 3: Cross-check SLMs
            # [V90 FIX] Filter out garbage SLM answers (single digit, 1-2 char nonsense)
            ctx.valid_responses = []
            for ctx.r in ctx.slm_responses:
                if "error" in ctx.r or not ctx.r.get("answer"):
                    continue
                ctx.ans = str(ctx.r["answer"]).strip()
                ctx.r_domain = ctx.r.get("domain", "")
                # Skip 1-2 char answers from non-math domains (likely garbage)
                if len(ctx.ans) <= 2 and ctx.r_domain not in ("math", "conversion", "reality"):
                    logger.debug(f"Filtering garbage SLM answer: '{ctx.ans}' from {ctx.r_domain}")
                    continue
                ctx.valid_responses.append(ctx.r)
            
            if not ctx.valid_responses:
                # All answers were garbage — fall back to original
                ctx.valid_responses = [ctx.r for ctx.r in ctx.slm_responses if "error" not in ctx.r and ctx.r.get("answer")]
            
            ctx.is_consistent = self._check_consistency(ctx.valid_responses)
            
            #  Step 3.5: ConflictResolver — nếu có nhiều SLM responses với values khác nhau
            # → dùng ConflictResolver để pick winner
            if len(ctx.valid_responses) >= 2:
                try:
                    from scp.core.conflict_resolver import resolve_value
                    # Get initial confidence from best response
                    ctx.confidence = max((ctx.r.get("confidence", 0) for ctx.r in ctx.valid_responses), default=0)
                    # Extract values from each SLM response
                    ctx.values_for_resolution = []
                    # [SCP-DNA-FIX R7-6] Propagate effective_weight into consensus voting.
                    # TẠI SAO: R6-6 called ingestion_decision() and LOGGED the action +
                    # effective_weight, but the weight was NEVER applied to the actual
                    # voting — suspect sources (effective_weight=0.5) still voted at
                    # full weight in resolve_value. Now we attach the effective_weight
                    # to each value dict AND filter out blocked sources (weight=0.0 → no vote).
                    # Reality evidence: vulture GONE (ingestion_decision called) but
                    # semantic intent scanner flags weight not propagated.
                    ctx._watchlist_for_vote = getattr(self, "_source_watchlist", None)
                    ctx._blocked_in_vote: list[str] = []
                    for ctx.r in ctx.valid_responses:
                        ctx.val = ctx.r.get("evidence", {}).get("value")
                        if ctx.val is None:
                            continue
                        ctx._src = ctx.r.get("evidence", {}).get("source", ctx.r.get("slm_name", "?"))
                        ctx._ew: float = 1.0  # default full weight (fail-open)
                        if ctx._watchlist_for_vote is not None and hasattr(ctx._watchlist_for_vote, "ingestion_decision"):
                            try:
                                ctx._ing = ctx._watchlist_for_vote.ingestion_decision(ctx._src, tier=3)
                                ctx._action = ctx._ing.get("action", "commit")
                                if ctx._action == "block":
                                    ctx._blocked_in_vote.append(ctx._src)
                                    continue  # blocked sources don't vote at all
                                ctx._ew = float(ctx._ing.get("effective_weight", 1.0) or 1.0)
                            except Exception as e:
                                logger.debug(f"[judgecore_mixin.py:770] silenced: {e}")
                        ctx.values_for_resolution.append({
                            "value": ctx.val,
                            "source": ctx._src,
                            "effective_weight": ctx._ew,  #  used by conflict_resolver
                        })
                    if ctx._blocked_in_vote:
                        logger.info(
                            f" Skipped {len(ctx._blocked_in_vote)} blocked source(s) in "
                            f"consensus voting: {ctx._blocked_in_vote[:3]}"
                        )
                        ctx.verdict.evidence.setdefault("consensus_blocked_sources", ctx._blocked_in_vote[:10])
                    if len(ctx.values_for_resolution) >= 2:
                        ctx.conflict_result = resolve_value(ctx.values_for_resolution, strategy="weighted_avg")
                        # [SCP-DNA-FIX R6-8] Source: vulture (Category B dead safety control) + grep verify.
                        # TẠI SAO: conflict_resolver.log_conflict() was NEVER called. It logs SLM-
                        # response value conflicts to knowledge_summaries.conflict_count +
                        # value_distribution — the ONLY operator-visible signal for "this entity has
                        # conflicting sources and needs more verification." Without it, the conflict
                        # resolver detects conflicts and adjusts confidence, but operators have ZERO
                        # visibility into WHICH entities conflict. Dashboard conflict stats always 0.
                        # Reality evidence: grep `log_conflict` → 0 callers (only the def).
                        # Fix: call log_conflict after resolve_value. Entity from SLM evidence (falls
                        # back to question text — log_conflict UPDATE is a no-op if no matching
                        # knowledge_summaries row, so this is safe + best-effort).
                        try:
                            from scp.core.conflict_resolver import log_conflict as _log_conflict
                            ctx._entity = ctx.valid_responses[0].get("evidence", {}).get("entity") or ctx.question[:60]
                            _log_conflict(ctx._entity, "value", ctx.values_for_resolution, ctx.conflict_result)
                        except Exception as _le:
                            logger.debug(f" log_conflict failed: {_le}")
                        # [V91 FIX] Actually USE the conflict resolution result!
                        if ctx.conflict_result.conflict_detected:
                            # Sources disagree → reduce confidence proportional to disagreement
                            ctx.agreement = getattr(ctx.conflict_result, 'agreement_score', 0.5)
                            if ctx.agreement < 0.5:
                                # Strong disagreement → mark as CONFLICT, not PASS
                                ctx.confidence = max(0.2, ctx.confidence * ctx.agreement)
                                logger.info(f"[CONFLICT] Sources disagree (agreement={ctx.agreement:.2f}): "
                                           f"{[(v['source'], v['value']) for v in ctx.values_for_resolution]}")
                            else:
                                # Mild disagreement → use resolved value, reduce confidence
                                ctx.resolved_val = getattr(ctx.conflict_result, 'final_value', None)
                                if ctx.resolved_val is not None:
                                    # Update primary answer with resolved value
                                    for ctx.r in ctx.valid_responses:
                                        if ctx.r.get("evidence", {}).get("source") == ctx.conflict_result.ctx.source:
                                            ctx.r["answer"] = f"= {ctx.resolved_val}"
                                            ctx.r["evidence"]["value"] = ctx.resolved_val
                                            break
                                    ctx.confidence = ctx.confidence * (0.7 + 0.3 * ctx.agreement)
                        else:
                            # All sources agree → boost confidence
                            ctx.confidence = min(0.97, ctx.confidence + 0.05)
            
                        # [SCP-DNA-FIX R6-4] Source: vulture (Category B dead safety control) + grep verify.
                        # TẠI SAO: SourceReputationStore.get_reputation() (source_reputation.py:467)
                        # was NEVER called. record_outcome() IS wired (line ~2336) — reputation
                        # data IS accumulated (correct/incorrect counts per source) — but NEVER READ.
                        # Sources that consistently provide wrong answers continue to be weighted
                        # equally with reliable sources in consensus voting. A malicious or
                        # chronically-wrong source can swing verdicts at full weight.
                        # Reality evidence: grep `get_reputation` → 0 callers (only def + comment).
                        # Fix: after conflict resolution, look up each contributing source's
                        # reputation and scale confidence by the WORST source's reputation
                        # (conservative — one unreliable source drags down the whole verdict).
                        # Non-fatal: if reputation store unavailable, skip (fail-open).
                        try:
                            ctx._rep_store = getattr(getattr(self, "_source_watchlist", None), "store", None)
                            if ctx._rep_store is not None and hasattr(ctx._rep_store, "get_reputation"):
                                ctx._domain = (ctx.domains[0] if ctx.domains else "unknown")
                                # [SCP-DNA-FIX R7-4] Cold-start: source with < N outcomes
                                # is treated as neutral (rep=1.0) in the worst-source
                                # scaling. TẠI SAO: a brand-new source's `get_reputation`
                                # returns 0.5 (neutral), but `0.3 + 0.7 * 0.5 = 0.65`
                                # drags the entire verdict confidence to 0.65 even when
                                # 4/5 sources are reliable. Cold-start gives new sources
                                # a chance to build reputation before being penalized.
                                # Reality evidence: hypothesis random source sets →
                                # anomalous low confidence when any source is new.
                                ctx._cold_start_count = 0
                                ctx._mature_reps: list[float] = []
                                for ctx._v in ctx.values_for_resolution:
                                    ctx._src = ctx._v.get("source", "")
                                    ctx._outcomes = 0
                                    if hasattr(ctx._rep_store, "get_outcome_count"):
                                        ctx._outcomes = ctx._rep_store.get_outcome_count(ctx._src, ctx._domain)
                                    ctx._threshold = getattr(ctx._rep_store, "COLD_START_THRESHOLD", 10)
                                    if ctx._outcomes < ctx._threshold:
                                        ctx._cold_start_count += 1
                                    else:
                                        ctx._rep = ctx._rep_store.get_reputation(ctx._src, ctx._domain)
                                        if ctx._rep is not None:
                                            ctx._mature_reps.append(ctx._rep)
                                # If ALL sources are cold-start → don't scale (no signal).
                                # If SOME sources are mature → scale by worst MATURE rep only.
                                if ctx._mature_reps:
                                    ctx._worst_rep = min(ctx._mature_reps)
                                else:
                                    ctx._worst_rep = 1.0  # all cold-start → neutral, no drag
                                #  Track cold-start metric for observability.
                                if ctx._cold_start_count > 0:
                                    ctx.verdict.evidence.setdefault("cold_start_sources", ctx._cold_start_count)
                                    logger.debug(
                                        f" {ctx._cold_start_count}/{len(ctx.values_for_resolution)} "
                                        f"sources in cold-start (<{getattr(ctx._rep_store, 'COLD_START_THRESHOLD', 10)} "
                                        f"outcomes) — skipped from worst-rep scaling"
                                    )
                                # Scale: reputation 1.0 → no change; 0.5 → halve; 0.0 → floor at 0.1
                                if ctx._worst_rep < 1.0:
                                    ctx.confidence = max(0.1, ctx.confidence * (0.3 + 0.7 * ctx._worst_rep))
                                    if ctx._worst_rep < 0.4:
                                        logger.info(
                                            f" Low-reputation source (rep={ctx._worst_rep:.2f}) "
                                            f"dragged confidence to {ctx.confidence:.2f}"
                                        )
                        except Exception as _re:
                            logger.debug(f" reputation scaling failed: {_re}")
                except Exception as e:
                    logger.debug(f"ConflictResolver error: {e}")
            
            # Step 4: Tính scores
            ctx.slm_scores = {}
            for ctx.r in ctx.valid_responses:
                ctx.slm_scores[ctx.r.get("domain", "unknown")] = {
                    "score": ctx.r.get("confidence", 0),
                    "answer": ctx.r.get("answer", ""),
                }
            
            # Step 5: Chọn primary response
            # [V104.47 #1] TẠI SAO: was pure argmax(confidence) → SLM tự tin thái quá
            # luôn thắng dù sai. Fix: consensus-aware selection — if 2+ SLMs agree
            # on same answer, boost that answer's effective confidence.
            if ctx.valid_responses:
                # Group by answer similarity (word overlap ≥ 0.6 = "agree")
                from difflib import SequenceMatcher
                ctx._groups = []  # [{answer, conf, count, members}]
                for ctx.r in ctx.valid_responses:
                    ctx._r_ans = (ctx.r.get("answer") or "").strip().lower()
                    ctx._matched = False
                    for ctx._g in ctx._groups:
                        ctx._g_ans = ctx._g["answer"]
                        if ctx._r_ans and ctx._g_ans:
                            ctx._sim = SequenceMatcher(None, ctx._r_ans, ctx._g_ans).ratio()
                            if ctx._sim >= 0.6:
                                ctx._g["count"] += 1
                                ctx._g["members"].append(ctx.r)
                                ctx._matched = True
                                break
                    if not ctx._matched:
                        ctx._groups.append({"answer": ctx._r_ans, "conf": ctx.r.get("confidence", 0), "count": 1, "members": [ctx.r]})
            
                # Pick group with highest consensus: count * avg_conf
                ctx._best_group = max(ctx._groups, key=lambda g: g["count"] * sum(ctx.m.get("confidence", 0) for ctx.m in g["members"]) / max(len(g["members"]), 1))
                # If consensus group has 2+ members, use it; else fall back to argmax
                if ctx._best_group["count"] >= 2:
                    ctx.primary = max(ctx._best_group["members"], key=lambda x: x.get("confidence", 0))
                    ctx._consensus_boost = 0.05 * (ctx._best_group["count"] - 1)  # +0.05 per agreeing SLM
                    ctx.confidence_boost = ctx._consensus_boost
                else:
                    ctx.primary = max(ctx.valid_responses, key=lambda x: x.get("confidence", 0))
                    ctx.confidence_boost = 0
            else:
                ctx.primary = None
                ctx.confidence_boost = 0
            # [FIX 2026-07-09] Was: hardcoded "unknown" when no SLM returned a useful
            # answer (primary=None) — this DISCARDED the correctly-routed domain from
            # Step 1 (self._route_question), causing the dashboard to show domain="unknown"
            # for ~87% of live queries even when routing worked fine (e.g. "cocktail" -> food,
            # "capital city" -> geography). Now falls back to the routed domain instead of
            # discarding it. Does NOT change verdict/confidence logic — reporting fix only.
            ctx._routed_fallback_domain = ctx.domains[0] if ctx.domains else "unknown"
            ctx.primary_domain = ctx.primary.get("domain", ctx._routed_fallback_domain) if ctx.primary else ctx._routed_fallback_domain
            ctx.final_answer = ctx.primary.get("answer", "") if ctx.primary else ""
            #  TẠI SAO: `confidence_boost` was computed above (consensus
            # bonus: +0.05 per agreeing SLM) but NEVER applied — line 1831 overwrote
            # `confidence = primary.get("confidence", 0)` without adding the boost.
            # The consensus bonus was dead code. Fix: apply it here, capped at 0.95.
            # [AUDIT-3 FIX] Add minimum per-SLM confidence gate: don't boost if the
            # individual SLMs are weak (< 0.5). TẠI SAO: without a gate, 5 weak SLMs
            # at 0.35 each → +0.20 → 0.55 → PASS. This is "ảo giác đồng thuận" —
            # many weak sources agreeing doesn't make them right (Invariant #2:
            # SLM ≠ reality). Gate: only boost if ALL agreeing SLMs have conf >= 0.5.
            ctx.confidence = ctx.primary.get("confidence", 0) if ctx.primary else 0
            try:
                if 'confidence_boost' in dir() and ctx.confidence_boost:
                    # [AUDIT-3] Check that all SLMs in the consensus group have
                    # individual confidence >= 0.5 before applying the boost.
                    ctx._all_strong = True
                    if '_best_group' in dir() and ctx._best_group:
                        for ctx._member in ctx._best_group.get("members", []):
                            if ctx._member.get("confidence", 0) < 0.5:
                                ctx._all_strong = False
                                break
                    if ctx._all_strong:
                        ctx.confidence = min(0.95, ctx.confidence + ctx.confidence_boost)
                    else:
                        logger.debug("[AUDIT-3] consensus boost skipped — some SLMs < 0.5 conf")
            except Exception as e:
                logger.warning(f"Silent except: {e}")  # confidence_boost may be undefined in edge paths — safe to skip
            
            # [V31C] Apply calibration factor — auto-tune confidence from history
            if self.calibration and ctx.primary_domain:
                try:
                    ctx.confidence = self.calibration.apply_calibration(ctx.confidence, ctx.primary_domain)
                    if os.environ.get('SCP_DEBUG_CONF'):
                        import sys as _sys
                        print(f'  [DBG] After calibration: {ctx.confidence} (factor applied)', file=_sys.stderr)
                except Exception as e:
                    logger.debug(f"Calibration apply error: {e}")
            
            # [V93.6] Apply CONFIDENCE_TUNING lessons from ExperienceEngine
            # (recurring low-confidence sources/domains flagged for extra scrutiny)
            if ctx.primary_domain:
                try:
                    ctx.exp_pol = self._get_exp_policies()
                    ctx.conf_adj = ctx.exp_pol.get("confidence_adjustments", {})
                    if ctx.primary_domain in ctx.conf_adj:
                        ctx.confidence = ctx.confidence * ctx.conf_adj[ctx.primary_domain]
                except Exception as e:
                    logger.debug(f"[V93.6] confidence_adjustment apply error: {e}")
            
            # ============================================================
            # [ROOT-FIX 43-A / Fix 1] Trust deterministic SLMs when conf >= 0.95
            # WHY: MathSLM uses AST evaluator (not LLM) — its answer IS reality.
            # Requiring DataSource verification for "2+2=4" is wasteful + returns UNKNOWN.
            # DNA SCP #1: Reality > Model — deterministic evaluator IS reality.
            # Also covers ConversionSLM (deterministic unit math), StatisticsSLM
            # (deterministic aggregation), LogicSLM (deterministic truth tables).
            # When SLM is one of these AND conf >= 0.95, skip WHY/adversary/reality
            # checks (they cannot improve on a deterministic answer) and return PASS.
            # SAFETY: V98 security checks (Step 0a-0c) already ran at lines 268-358
            # before SLM predict — so attacks are still blocked before this short-circuit.
            # ============================================================
            ctx.DETERMINISTIC_SLMS = ("MathSLM", "ConversionSLM", "StatisticsSLM", "LogicSLM")
            if ctx.primary and ctx.confidence >= 0.95:
                ctx._slm_name = str(ctx.primary.get("slm_name", "") or ctx.primary.get("source", "") or "")
                if any(_d in ctx._slm_name for _d in ctx.DETERMINISTIC_SLMS):
                    # [P0-2 FIX R16] Deterministic SLM confidence is necessary but NOT sufficient.
                    # BEFORE: conf>=0.95 → return PASS immediately (no verification).
                    #         Q11-FP-3: a bug in MathSLM/ConversionSLM/StatisticsSLM/LogicSLM
                    #         goes unchecked — could return PASS/conf=0.95 on wrong answer.
                    # AFTER:  run lightweight _reality_check_deterministic() to independently
                    #         verify the SLM's answer. Only PASS if reality check confirms.
                    #         If reality check fails → downgrade to UNKNOWN, fall through to
                    #         normal verdict path (adversary, WHY, etc.).
                    ctx._reality_ok = True
                    ctx._reality_msg = "skipped (no checker implemented)"
                    try:
                        ctx._reality_ok, ctx._reality_msg = self._reality_check_deterministic(
                            ctx._slm_name, ctx.question, ctx.final_answer, ctx.primary
                        )
                    except Exception as _rc_err:
                        logger.warning(
                            f"[P0-2] reality_check_deterministic crashed for '{ctx._slm_name}': {_rc_err}"
                        )
                        ctx._reality_ok = False  # fail-closed on crash
                        ctx._reality_msg = f"checker crashed: {_rc_err}"
            
                    if ctx._reality_ok:
                        logger.info(
                            f"[ROOT-FIX 43-A R16] Deterministic SLM '{ctx._slm_name}' "
                            f"(conf={ctx.confidence:.2f}) PASSED reality check: {ctx._reality_msg}"
                        )
                        return JudgeVerdict(
                            question=ctx.question,
                            slm_responses=ctx.slm_responses,
                            final_answer=ctx.final_answer,
                            confidence=ctx.confidence,
                            verdict="PASS",
                            reasoning=(
                                f"Deterministic SLM ({ctx._slm_name}) conf={ctx.confidence:.2f} + "
                                f"reality check PASSED: {ctx._reality_msg} "
                                f"(DNA SCP #1: Reality > Model — verified, not just claimed)"
                            ),
                            evidence={
                                "primary_domain": ctx.primary_domain,
                                "deterministic_slm": True,
                                "slm_name": ctx._slm_name,
                                "skip_why_verification": True,
                                "root_fix": "43-A/Fix1 + R16/P0-2 (reality check added)",
                                "reality_check_passed": True,
                                "reality_check_msg": ctx._reality_msg,
                            },
                            domain=ctx.primary_domain,
                            cross_validation={
                                "answers": [ctx.r.get("answer", "") for ctx.r in ctx.valid_responses],
                                "consistency_score": self._consistency_score(ctx.valid_responses),
                            },
                            slm_scores=ctx.slm_scores,
                            reality_check={
                                "is_correct": True,
                                "reason": f"Deterministic SLM ({ctx._slm_name}) + reality check passed: {ctx._reality_msg}",
                                "source": ctx._slm_name,
                                "verified_by": "r16_reality_check",
                            },
                            timestamp=ctx.ts,
                            similar_errors=[],
                        )
                    else:
                        # Reality check FAILED — don't PASS, downgrade confidence, fall through
                        logger.warning(
                            f"[P0-2 R16] Deterministic SLM '{ctx._slm_name}' claimed conf={ctx.confidence:.2f} "
                            f"but reality check FAILED: {ctx._reality_msg} — downgrading to UNKNOWN"
                        )
                        ctx.confidence = min(ctx.confidence, 0.4)
                        # Fall through to normal verdict path (adversary, WHY, etc.)
            
            #  Step 5.5: Adversary verify — cross-validate với source khác
            # Chỉ chạy nếu SLM primary có real value và không skip API
            # [V29.2] Mở rộng cho history/biology/reality/geography (Wikipedia adversary)
            #  Skip adversary khi confidence đã rất cao (>0.92) — tiết kiệm 100-300ms
            ctx.adversary_result = None
            # [V104.40 #K-skip] TẠI SAO: V91 skipped adversary when confidence >= 0.92.
            # This is BACKWARDS — overconfident SLM is exactly when skeptical cross-check
            # is most needed (No-Hallucination principle). Fix: remove the 0.92 bypass.
            # Adversary runs for ALL domains regardless of confidence.
            if (self.adversary and ctx.primary and not ctx.prediction_skip_api):
                try:
                    ctx.primary_value = ctx.primary.get("evidence", {}).get("value")
                    ctx.primary_source = ctx.primary.get("evidence", {}).get("source", "")
                    # Extract entity từ question
                    ctx.entity = ctx.primary.get("evidence", {}).get("entity", "")
                    if ctx.primary_value is not None and ctx.primary_source:
                        ctx.adv = self.adversary.verify(
                            ctx.primary_value, ctx.primary_source,
                            ctx.primary_domain, ctx.question, ctx.entity or ""
                        )
                        if ctx.adv.adversary_values:  # Only use if adversary actually ran
                            ctx.adversary_result = ctx.adv
                            # [V86 FIX] Was: confidence = adv.final_confidence
                            #   → adversary returns 0.3 when it can't fully verify
                            #   → overrides SLM's 0.85 → verdict becomes PARTIAL instead of PASS
                            # Now: adversary can only BOOST confidence (if it agrees)
                            #   or REDUCE only if it finds a CONFLICT (different value)
                            #   If adversary can't verify (no conflict, no agreement) → keep SLM confidence
                            if ctx.adv.conflict_detected and ctx.adv.agreement_score < 0.85:
                                # [V104.40 #K]  TẠI SAO: was `if verdict_type == "PASS":
                                # verdict_type = "CONFLICT"` — but verdict_type is None here (Step 5.5
                                # runs BEFORE Step 6 sets verdict_type) → NameError → swallowed by
                                # except → adversary conflict signal never reached the verdict state
                                # machine. Fix: record as a flag; apply AFTER Step 6 finalizes
                                # verdict_type (before JudgeVerdict construction at ~line 2251).
                                # Constitution: "reality outranks model opinion" — adversary found
                                # DIFFERENT value from independent source → must be CONFLICT, not PASS.
                                ctx.confidence = max(0.3, ctx.confidence - 0.2)
                                ctx._adversary_conflict = True
                                ctx._adversary_conflict_reason = f". Adversary conflict: agreement={ctx.adv.agreement_score:.2f} (source says different value)"
                            elif ctx.adv.agreement_score >= 0.85:
                                # Adversary AGREES → boost confidence
                                ctx.confidence = min(0.95, ctx.confidence + 0.05)
                            # else: adversary couldn't verify → keep SLM confidence (don't change)
                        else:
                            # [V48 FIX] Adversary didn't run — but result still has useful confidence
                            # Trước V48: ignore adversary result entirely → keep SLM confidence (good)
                            # V48: if adversary final_confidence is HIGHER → boost; if LOWER → keep SLM
                            # Don't reduce confidence just because adversary couldn't run
                            if os.environ.get('SCP_DEBUG_CONF'):
                                import sys as _sys
                                print(f'  [DBG] Adversary no_values, final_conf={ctx.adv.final_confidence}', file=_sys.stderr)
                            #  Only update confidence if adversary is MORE confident (cross-checked)
                            # Otherwise preserve SLM confidence
                            if ctx.adv.final_confidence > ctx.confidence:
                                ctx.confidence = ctx.adv.final_confidence
                except Exception as e:
                    logger.debug(f"Adversary verify error: {e}")
            
            # [V88 FIX] Initialize reality_check early — used in Step 6 consensus check before Step 7 defines it
            ctx.reality_check = {"is_correct": None, "reason": "Not yet checked"}
            # Step 6: Quyết định verdict
            # Use adjusted_threshold from PolicyApplier
            ctx.effective_threshold = ctx.adjusted_threshold
            # [FIX v27] Check if AI answer matches SLM answer
            # [V48-V49] tolerance-based + scientific notation + string comparison
            # [V51 FIX] Multiple critical bug fixes:
            #   - Math: extract ONLY the result number (after '='), not all numbers
            #   - Reality: tightened tolerance for scientific notation (was too loose)
            #   - Geography: full-string comparison, not just last word (was "city"=="city")
            #   - Unknown: empty AI answer → UNKNOWN, not PARTIAL
            if ctx.is_consistent and ctx.confidence > ctx.effective_threshold:
                # SLM says answer is X, but did AI say X?
                ctx.slm_answer = ctx.final_answer
                if ctx.ai_answer and ctx.slm_answer:
                    #  FIRST: Try value extraction for question-type-aware comparison
                    # Was (V51-V72): only numeric comparison + text overlap
                    #   → "calories=52" (AI) vs "Apple family Rosaceae calories=52 sugar=10.3g..."
                    #     → SLM picks wrong number (0.3) → FAIL (wrong!)
                    # Now (V73): extract comparable value (year/number/type/quote) BEFORE numeric path
                    ctx.ai_extracted = self._extract_value(ctx.question, ctx.ai_answer)
                    ctx.slm_extracted = self._extract_value(ctx.question, ctx.slm_answer)
                    if ctx.ai_extracted and ctx.slm_extracted:
                        # Direct value match
                        if ctx.ai_extracted.lower() == ctx.slm_extracted.lower():
                            ctx.verdict_type = "PASS"
                            ctx.reasoning = f"Value match: '{ctx.ai_extracted[:50]}' == '{ctx.slm_extracted[:50]}'"
                        elif ctx.ai_extracted.lower() in ctx.slm_extracted.lower() or ctx.slm_extracted.lower() in ctx.ai_extracted.lower():
                            # Substring match (one is part of the other)
                            ctx.verdict_type = "PASS"
                            ctx.reasoning = f"Value substring match: '{ctx.ai_extracted[:50]}' ⊆ '{ctx.slm_extracted[:50]}'"
                        else:
                            # No value match — fall through to numeric/string comparison
                            ctx.verdict_type = None  # will be set by next section
                    else:
                        ctx.verdict_type = None  # fall through
            
                    # If value extraction didn't give a clear answer, use legacy comparison
                    if ctx.verdict_type is None:
                        #  Special handling for math: extract ONLY result (after '=')
                        import re
                        # If SLM answer has '=', extract only the part after '='
                        ctx.slm_result_part = ctx.slm_answer
                        ctx.ai_result_part = ctx.ai_answer
                        if '=' in ctx.slm_answer:
                            ctx.slm_result_part = ctx.slm_answer.split('=')[-1].strip()
                        if '=' in ctx.ai_answer:
                            ctx.ai_result_part = ctx.ai_answer.split('=')[-1].strip()
            
                        ctx.num_pattern = r'-?\d+\.?\d*(?:[eE][+-]?\d+)?'
                        ctx.slm_nums = re.findall(ctx.num_pattern, ctx.slm_result_part)
                        ctx.ai_nums = re.findall(ctx.num_pattern, ctx.ai_result_part)
            
                        if ctx.slm_nums and ctx.ai_nums:
                            #  For math, take the FIRST (and usually only) number from result
                            # For multi-number answers (astronomy), find closest
                            ctx.ai_val = float(ctx.ai_nums[0])  #  was [-1], should be [0] for result
                            ctx.best_slm_val = None
                            ctx.best_diff = float('inf')
                            for ctx.sn in ctx.slm_nums:
                                try:
                                    ctx.sv = float(ctx.sn)
                                    ctx.diff = abs(ctx.sv - ctx.ai_val)
                                    if ctx.diff < ctx.best_diff:
                                        ctx.best_diff = ctx.diff
                                        ctx.best_slm_val = ctx.sv
                                except ValueError:
                                    continue
                            if ctx.best_slm_val is None:
                                ctx.best_slm_val = float(ctx.slm_nums[0])
                            ctx.slm_val = ctx.best_slm_val
            
                            # [V51 FIX] Improved tolerance for scientific notation
                            # [V52 FIX] Use much smaller floor (1e-300) instead of 1e-10
                            # Trước V52: max(abs_max, 1e-300) → for 6.626e-34, floor=1e-10 → rel_diff≈0 → PASS (wrong!)
                            # V52: max(abs_max, 1e-300) → rel_diff correctly = 0.5 for planck perturbed case
                            ctx.abs_diff = abs(ctx.slm_val - ctx.ai_val)
                            ctx.abs_max = max(abs(ctx.slm_val), abs(ctx.ai_val))
                            ctx.rel_diff = ctx.abs_diff / max(ctx.abs_max, 1e-300)
            
                            #  Tighter tolerance:
                            # - For |val| >= 1: 0.5% relative tolerance
                            # - For 0 < |val| < 1: 1% relative tolerance (was 0.5%, too loose for tiny numbers)
                            # - For scientific notation (val very small/large): ALWAYS use relative
                            # - Absolute tolerance 0.01 only for very small numbers near 0
                            if ctx.abs_max >= 1:
                                ctx.tolerance = ctx.abs_max * 0.005  # 0.5% relative
                            elif ctx.abs_max >= 0.01:
                                ctx.tolerance = ctx.abs_max * 0.01  # 1% relative for small numbers
                            else:
                                ctx.tolerance = ctx.abs_max * 0.02  # 2% relative for very small
            
                            #  For very large/small (scientific notation), use stricter relative check
                            ctx.is_sci = ctx.abs_max > 1e6 or (ctx.abs_max > 0 and ctx.abs_max < 1e-3)
                            if ctx.is_sci:
                                # Scientific notation: 1% relative tolerance
                                if ctx.rel_diff > 0.01:
                                    ctx.verdict_type = "FAIL"
                                    ctx.reasoning = f"SLM tính {ctx.slm_val:.6g}, AI nói {ctx.ai_val:.6g} (chênh {ctx.rel_diff*100:.2f}%)"
                                else:
                                    ctx.verdict_type = "PASS"
                                    ctx.reasoning = "Các SLM đồng thuận, đạt ngưỡng tin cậy"
                            elif ctx.abs_diff > ctx.tolerance and ctx.rel_diff > 0.005:
                                ctx.verdict_type = "FAIL"
                                ctx.reasoning = f"SLM tính {ctx.slm_val}, AI nói {ctx.ai_val} (chênh {ctx.abs_diff:.4f})"
                            else:
                                ctx.verdict_type = "PASS"
                                ctx.reasoning = "Các SLM đồng thuận, đạt ngưỡng tin cậy"
                        else:
                            # [V51 FIX] No numbers — FULL string comparison, not just last word
                            # Trước V51: chỉ compare last word → "Mexico City" vs "Nowhere City" → "city"=="city" → PASS (wrong!)
                            # V51: require full answer string match (or substring)
                            ctx.slm_str = ctx.slm_answer.strip().lower().rstrip('.?!,;:').replace('.', '')  #  strip periods
                            ctx.ai_str = ctx.ai_answer.strip().lower().rstrip('.?!,;:').replace('.', '')  #  strip periods
            
                            #  Strip common prefixes like "thủ đô của X là" to compare only the answer
                            ctx.answer_prefixes = [
                                r'^thủ đô của \w+ là\s+',
                                r'^capital of \w+ is\s+',
                                r'^=\s*',
                            ]
                            for ctx.pat in ctx.answer_prefixes:
                                ctx.slm_str = re.sub(ctx.pat, '', ctx.slm_str).strip()
                                ctx.ai_str = re.sub(ctx.pat, '', ctx.ai_str).strip()
            
                            #  Value extraction — extract comparable values BEFORE compare
                            # Was: compare raw text "SLM says '5.6834e+26 (loại: gas giant)' vs AI 'planet'"
                            #   → overlap 0% → FAIL (wrong!)
                            # Now: extract specific value (year, number, type) → compare values
                            ctx.ai_value = self._extract_value(ctx.question, ctx.ai_str)
                            ctx.slm_value = self._extract_value(ctx.question, ctx.slm_str)
                            if ctx.ai_value and ctx.slm_value:
                                # Use extracted values for comparison
                                ctx.ai_compare = ctx.ai_value
                                ctx.slm_compare = ctx.slm_value
                            else:
                                # Fallback to raw answer
                                ctx.ai_compare = ctx.ai_str
                                ctx.slm_compare = ctx.slm_str
            
                            #  Direct value match — if extracted values match exactly, PASS
                            if ctx.ai_value and ctx.slm_value and ctx.ai_value.lower() == ctx.slm_value.lower():
                                ctx.verdict_type = "PASS"
                                ctx.reasoning = f"Value match: '{ctx.ai_value}' == '{ctx.slm_value}'"
                            elif not ctx.ai_compare or not ctx.slm_compare:
                                #  Empty answer → FAIL (was PASS)
                                ctx.verdict_type = "FAIL"
                                ctx.reasoning = "Empty answer from SLM or AI"
                            elif ctx.ai_str in ctx.slm_str or ctx.slm_str in ctx.ai_str:
                                # Check that the match is substantial (not just "city" matching "city")
                                ctx.match_len = min(len(ctx.ai_str), len(ctx.slm_str))
                                if ctx.match_len >= 3:  #  require at least 3 chars match
                                    ctx.verdict_type = "PASS"
                                    ctx.reasoning = "Các SLM đồng thuận (string match), đạt ngưỡng tin cậy"
                                else:
                                    ctx.verdict_type = "FAIL"
                                    ctx.reasoning = f"String match too short: '{ctx.ai_str}' vs '{ctx.slm_str}'"
                            else:
                                # [V51.1 FIX] Fuzzy match: remove stopwords then re-compare
                                # VD: "dời đô thăng long" vs "dời đô ra thăng long" → remove "ra" → match
                                ctx.stopwords = [' ra ', ' của ', ' là ', ' và ', ' được ', ' tại ', ' ở ',
                                            ' bằng ', ' có ', ' cho ', ' từ ', ' vào ', ' lên ', ' xuống ']
                                ctx.slm_clean = ctx.slm_str
                                ctx.ai_clean = ctx.ai_str
                                for ctx.sw in ctx.stopwords:
                                    ctx.slm_clean = ctx.slm_clean.replace(ctx.sw, ' ')
                                    ctx.ai_clean = ctx.ai_clean.replace(ctx.sw, ' ')
                                # Collapse multiple spaces
                                ctx.slm_clean = ' '.join(ctx.slm_clean.split())
                                ctx.ai_clean = ' '.join(ctx.ai_clean.split())
            
                                if ctx.ai_clean in ctx.slm_clean or ctx.slm_clean in ctx.ai_clean:
                                    ctx.match_len = min(len(ctx.ai_clean), len(ctx.slm_clean))
                                    if ctx.match_len >= 3:
                                        ctx.verdict_type = "PASS"
                                        ctx.reasoning = "Các SLM đồng thuận (fuzzy string match), đạt ngưỡng tin cậy"
                                    else:
                                        ctx.verdict_type = "FAIL"
                                        ctx.reasoning = f"Fuzzy match too short: '{ctx.ai_clean}' vs '{ctx.slm_clean}'"
                                else:
                                    # [V51.2] Word overlap check — if ≥60% of AI words appear in SLM
                                    ctx.ai_words = set(ctx.ai_clean.split())
                                    ctx.slm_words = set(ctx.slm_clean.split())
                                    if ctx.ai_words and ctx.slm_words:
                                        ctx.overlap = len(ctx.ai_words & ctx.slm_words) / len(ctx.ai_words)
                                        if ctx.overlap >= 0.6:
                                            ctx.verdict_type = "PASS"
                                            ctx.reasoning = f"Các SLM đồng thuận (word overlap {ctx.overlap*100:.0f}%), đạt ngưỡng tin cậy"
                                        else:
                                            ctx.verdict_type = "FAIL"
                                            ctx.reasoning = f"SLM says '{ctx.slm_str[:30]}', AI says '{ctx.ai_str[:30]}' (overlap {ctx.overlap*100:.0f}%)"
                                    else:
                                        ctx.verdict_type = "FAIL"
                                        ctx.reasoning = f"SLM says '{ctx.slm_str[:30]}', AI says '{ctx.ai_str[:30]}' (string mismatch)"
                else:
                    #  No AI answer or no SLM answer
                    # [V104.40 #M] TẠI SAO: V90 LEARN let SLM self-confirm (is_correct=True,
                    # verdict=PASS) when no AI answer — VIOLATES Evidence-First / No-Hallucination.
                    # SLM output became "real_value" with source="slm_self" → knowledge contaminated
                    # with unverified model output. Fix: require external source for PASS.
                    if not ctx.ai_answer:
                        if ctx.confidence >= 0.65 and ctx.final_answer:
                            # SLM has confident answer but NO external verification
                            # → verdict UNKNOWN (not PASS), don't contaminate KB
                            ctx.verdict_type = "UNKNOWN"
                            ctx.reasoning = f"SLM self-answered (conf={ctx.confidence:.2f}) but no external source — cannot verify (Evidence-First)"
                        else:
                            ctx.verdict_type = "UNKNOWN"
                            ctx.reasoning = "No AI answer to verify"
                    elif not ctx.final_answer:
                        ctx.verdict_type = "UNKNOWN"
                        ctx.reasoning = "SLM has no answer"
                    else:
                        ctx.verdict_type = "PASS"
                        ctx.reasoning = "Các SLM đồng thuận, đạt ngưỡng tin cậy"
            elif ctx.is_consistent:
                # [V51 FIX] If confidence is 0 (no useful SLM response), UNKNOWN not PARTIAL
                if ctx.confidence < 0.05:
                    ctx.verdict_type = "UNKNOWN"
                    ctx.reasoning = "SLM returned no useful answer (confidence ~0)"
                    # [V105 Phase 9.5] Speculative Mode — thay vì KILL, trả về suy đoán có cảnh báo
                    # SCP vẫn thỏa mãn "Không ảo giác" vì đã cảnh báo rõ đây là suy đoán
                    if not ctx.final_answer:
                        ctx.final_answer = (
                            "[SCP] Tôi không có đủ dữ liệu để trả lời câu hỏi này. Đây là ngoài phạm vi kiến thức hiện tại của tôi."
                        )
                    # Check if question is creative/hypothetical (not attack) → Speculative Mode
                    ctx._speculative_keywords = [
                        "hãy tạo ra", "hãy xây dựng", "hãy đề xuất", "hãy tưởng tượng",
                        "ý tưởng mới", "hoàn toàn mới", "đột phá", "giả định",
                        "mô hình", "học thuyết", "dự đoán", "suy đoán",
                        "create", "imagine", "propose", "hypothetical",
                        "nếu", "what if", "giả sử",
                    ]
                    ctx._is_speculative = any(kw in ctx.question.lower() for kw in ctx._speculative_keywords)
                    ctx._is_attack = ctx.v98_guard_verdict and ctx.v98_guard_verdict.is_poisoned
            
                    if ctx._is_speculative and not ctx._is_attack:
                        # === SPECULATIVE MODE ===
                        # Không KILL — trả về suy đoán với cảnh báo đỏ
                        ctx.verdict_type = "SPECULATIVE"
                        ctx.reasoning = (
                            "Phase 9.5 Speculative Mode: Câu hỏi mang tính sáng tạo/giả định, "
                            "không phải tấn công. SCP không có ground truth để verify, "
                            "nhưng không kìm hãm sáng tạo — trả về với cảnh báo."
                        )
                        # Build speculative response with assumptions
                        ctx._spec_assumptions = []
                        if "đạo đức" in ctx.question.lower() or "ethic" in ctx.question.lower():
                            ctx._spec_assumptions = [
                                "Giả định 1: Các nguyên tắc đạo đức cơ bản (không giết người, trung thực, công bằng) là phổ quát",
                                "Giả định 2: Hệ thống AI có khả năng đánh giá hậu quả trong thời gian thực",
                                "Giả định 3: Có thể lượng hóa được 'lợi ích' và 'nghĩa vụ' trên cùng một thang đo",
                                "Giả định 4: Quyết định đạo đức có thể được biểu diễn dưới dạng thuật toán",
                            ]
                        elif "lịch sử" in ctx.question.lower() or "khảo cổ" in ctx.question.lower() or "văn minh" in ctx.question.lower():
                            ctx._spec_assumptions = [
                                "Giả định 1: Các dữ liệu khảo cổ hiện tại phản ánh đúng thực tế lịch sử",
                                "Giả định 2: Sự sụp đổ của nền văn minh có thể được giải thích bằng một nguyên nhân chính",
                                "Giả định 3: Hệ thống chữ viết chưa giải mã có cấu trúc nhất quán có thể suy luận",
                                "Giả định 4: Các mô hình xã hội học hiện đại có thể áp dụng cho xã hội cổ đại",
                            ]
                        elif "khoa học" in ctx.question.lower() or "vật lý" in ctx.question.lower() or "vũ trụ" in ctx.question.lower():
                            ctx._spec_assumptions = [
                                "Giả định 1: Các định luật vật lý hiện tại (nhiệt động, lượng tử, tương đối) là đúng",
                                "Giả định 2: Ý tưởng mới không mâu thuẫn với dữ liệu thực nghiệm đã biết",
                                "Giả định 3: Có thể kiểm tra ý tưởng bằng thí nghiệm trong tương lai",
                                "Giả định 4: Toán học là ngôn ngữ phù hợp để mô tả vũ trụ",
                            ]
                        else:
                            ctx._spec_assumptions = [
                                f"Giả định 1: Câu hỏi '{ctx.question[:60]}...' có thể được suy luận từ kiến thức hiện có",
                                "Giả định 2: Các giả định logic có thể được xây dựng từ các nguyên lý đã biết",
                                "Giả định 3: Kết quả suy đoán có thể được kiểm chứng trong tương lai",
                            ]
            
                        ctx._spec_response = (
                            "[SPECULATIVE - ZERO EVIDENCE]\n"
                            "⚠️ CẢNH BÁO: Phản hồi dưới đây là SUY ĐOÁN, không có bằng chứng thực nghiệm.\n"
                            "SCP không có ground truth để verify. Không nên sử dụng làm cơ sở quyết định quan trọng.\n\n"
                            "Câu hỏi của bạn yêu cầu sáng tạo/giả định — ngoài phạm vi verify của SCP.\n\n"
                            "Các giả định logic được đưa ra:\n"
                        )
                        for ctx.i, ctx.assumption in enumerate(ctx._spec_assumptions, 1):
                            ctx._spec_response += f"  {ctx.i}. {ctx.assumption}\n"
                        ctx._spec_response += (
                            "\nNếu các giả định trên đúng, thì một hướng tiếp cận có thể là:\n"
                            "  → Phân tích câu hỏi từ góc nhìn multi-disciplinary\n"
                            "  → Xây dựng framework logic dựa trên các giả định\n"
                            "  → Kiểm tra tính nhất quán nội bộ\n"
                            "  → Đề xuất phương pháp kiểm chứng trong tương lai\n\n"
                            "⚠️ SCP KHÔNG xác nhận tính đúng đắn của bất kỳ phần nào trong phản hồi này.\n"
                            "Đây là Speculative Mode — con người quyết định."
                        )
                        ctx.final_answer = ctx._spec_response
                        ctx.confidence = 0.0  # vẫn 0 — không tự lừa
                        # Ghi vào evidence
                        ctx.verdict_evidence_spec = {
                            "speculative_mode": True,
                            "assumptions": ctx._spec_assumptions,
                            "warning": "ZERO EVIDENCE — suy đoán không có ground truth",
                            "human_decision_required": True,
                        }
                else:
                    #  Check if we have enough evidence
                    # If only 1 SLM responded AND no reality_check → INSUFFICIENT_EVIDENCE
                    # SCP should not PASS/FAIL without cross-verification
                    ctx.num_slm_answers = len([ctx.r for ctx.r in ctx.valid_responses if ctx.r.get("answer")])
                    ctx.has_reality_check = bool(ctx.reality_check and ctx.reality_check.get("real_value") is not None)
            
                    if ctx.num_slm_answers < 2 and not ctx.has_reality_check and ctx.confidence < 0.6:
                        # Only 1 source, no reality check, low confidence → insufficient evidence
                        ctx.verdict_type = "UNKNOWN"
                        ctx.reasoning = f"Không đủ bằng chứng (chỉ {ctx.num_slm_answers} nguồn, conf={ctx.confidence:.2f})"
                    else:
                        ctx.verdict_type = "PARTIAL"
                        ctx.reasoning = f"Các SLM đồng thuận nhưng độ tin cậy thấp ({ctx.num_slm_answers} nguồn, conf={ctx.confidence:.2f})"
            else:
                # [V88 FIX] Was: always CONFLICT when SLMs disagree with each other
                # But: if AI answer matches ANY SLM → PASS/FAIL based on that match
                # SLM-SLM disagreement is normal (different sources, different formats)
                # What matters is: does AI answer match the BEST SLM?
                # Check: does AI answer appear in any SLM answer?
                ctx.ai_lower = (ctx.ai_answer or "").strip().lower()
                ctx.matched_slm = None
                if ctx.ai_lower:
                    for ctx.r in ctx.valid_responses:
                        ctx.slm_ans = (ctx.r.get("answer") or "").strip().lower()
                        if ctx.ai_lower in ctx.slm_ans or ctx.slm_ans in ctx.ai_lower:
                            ctx.matched_slm = ctx.r
                            break
                        # Also check word overlap
                        ctx.ai_words = set(ctx.ai_lower.split())
                        ctx.slm_words = set(ctx.slm_ans.split())
                        if ctx.ai_words and ctx.slm_words:
                            ctx.overlap = len(ctx.ai_words & ctx.slm_words) / max(len(ctx.ai_words), 1)
                            if ctx.overlap >= 0.6:
                                ctx.matched_slm = ctx.r
                                break
            
                # Deterministic equivalence for arithmetic answers: a verbose model answer
                # such as '2 + 2 = 4' must match a verifier answer such as '4'.
                # This does not override the primary/non-primary safety rule below.
                if ctx.matched_slm is None:
                    try:
                        import re as _answer_match_re
                        ctx._math_like = bool(_answer_match_re.search(
                            r'(?i)(?:calculate|compute|arithmetic|tinh|tinh toan|phep tinh)|[-+*/]\s*\d|\d\s*[-+*/=]\s*\d',
                            str(ctx.question or ''),
                        ))
                        if ctx._math_like and (ctx.ai_answer or ctx.final_answer):
                            def _nums(_text):
                                return _answer_match_re.findall(
                                    r'(?<![A-Za-z_])[-+]?\d+(?:[.,]\d+)?',
                                    str(_text or ''),
                                )
                            ctx._comparison_answer = ctx.ai_answer or ctx.final_answer
                            ctx._ai_nums = _nums(ctx._comparison_answer)
                            ctx._ai_last = ctx._ai_nums[-1].replace(',', '.') if ctx._ai_nums else None
                            if ctx._ai_last is not None:
                                from decimal import Decimal as _AnswerDecimal
                                for ctx._candidate in ctx.valid_responses:
                                    ctx._candidate_nums = _nums(ctx._candidate.get('answer', ''))
                                    if not ctx._candidate_nums:
                                        continue
                                    ctx._candidate_last = ctx._candidate_nums[-1].replace(',', '.')
                                    if _AnswerDecimal(ctx._ai_last) == _AnswerDecimal(ctx._candidate_last):
                                        ctx.matched_slm = ctx._candidate
                                        break
                    except (ValueError, TypeError, ArithmeticError):
                        ctx.matched_slm = None
            
                if ctx.matched_slm:
                    # [V104.42 #O] TẠI SAO: was `verdict_type = "PASS"` when AI matched ANY 1 SLM
                    # → multi-SLM conflict erased if AI happened to match one (even low-conf secondary).
                    # Fix: only PASS if matched SLM is the PRIMARY (highest confidence) or majority.
                    ctx._primary_slm = max(ctx.valid_responses, key=lambda r: ctx.r.get("confidence", 0)) if ctx.valid_responses else None
                    ctx._is_primary = (ctx.matched_slm == ctx._primary_slm)
                    if ctx._is_primary:
                        ctx.verdict_type = "PASS"
                        ctx.confidence = ctx.matched_slm.get("confidence", ctx.confidence)
                        ctx.reasoning = f"Các SLM có mâu thuẫn nhưng AI match PRIMARY SLM[{ctx.matched_slm.get('domain', '?')}]"
                    else:
                        # [V104.42 #O] AI matched a non-primary SLM → keep CONFLICT
                        ctx.verdict_type = "CONFLICT"
                        ctx.confidence = min(ctx.confidence, ctx.matched_slm.get("confidence", 0.5))
                        ctx.reasoning = f"Các SLM mâu thuẫn, AI match non-primary SLM[{ctx.matched_slm.get('domain', '?')}] (not enough for PASS)"
                else:
                    ctx.verdict_type = "CONFLICT"
                    ctx.reasoning = "Các SLM có mâu thuẫn và AI không match bất kỳ SLM nào"
                # Resolve: lấy confidence cao nhất
                ctx.final_answer = ctx.primary.get("answer", "") if ctx.primary else ""
            
        
