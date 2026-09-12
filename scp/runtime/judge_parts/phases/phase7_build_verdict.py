from typing import Any
from scp.runtime.judge_parts.phases.context import JudgeContext
import time
from datetime import datetime
import os
import logging
logger = logging.getLogger(__name__)

class Phase7BuildVerdictMixin:
    def _phase7_build_verdict(self, ctx: JudgeContext) -> Any:
            # Step 9: Build verdict
            ctx.verdict = JudgeVerdict(
                question=ctx.question,
                slm_responses=ctx.slm_responses,
                final_answer=ctx.final_answer,
                confidence=ctx.confidence,
                verdict=ctx.verdict_type,
                reasoning=ctx.reasoning,
                evidence={
                    "primary_domain": ctx.primary_domain,
                    "consistency": ctx.is_consistent,
                    "slm_count": len(ctx.slm_responses),
                    "valid_slm_count": len(ctx.valid_responses),
                    **ctx._pre_verdict_evidence,  #  merge UnifiedDetector + ErrorStoreIndex evidence
                    **({"speculative_mode": ctx.verdict_evidence_spec} if ctx.verdict_evidence_spec is not None and ctx.verdict_type == "SPECULATIVE" else {}),
                },
                domain=ctx.primary_domain,
                cross_validation={
                    "answers": [ctx.r.get("answer", "") for ctx.r in ctx.valid_responses],
                    "consistency_score": self._consistency_score(ctx.valid_responses),
                },
                slm_scores=ctx.slm_scores,
                reality_check=ctx.reality_check,
                timestamp=ctx.ts,
                similar_errors=ctx.similar_errors,
            )
            
            # [V9.0-WHY-GATE] WHY Gate — PRIMARY CONTROL GATE for verdict
            # TẠI SAO: v8.0 WHY = advisory (adjust confidence ±0.1). v9.0 WHY = chốt
            # (block-capable). WHY Gate can downgrade PASS → UNKNOWN if WHY rejects.
            # Constitution HARD LOCK: WHY cannot override KILL (checked in gate()).
            try:
                from scp.meta.why_gate import get_why_gate
                ctx._why_gate = get_why_gate()
                if ctx.verdict.ctx.verdict == "PASS":
                    ctx._why_result = ctx._why_gate.gate(
                        action_type="verdict",
                        action_desc=f"Verdict PASS for question: {ctx.question[:100]}",
                        context=f"confidence={ctx.confidence}, sources={len(ctx.slm_responses)}, reasoning={ctx.reasoning[:200]}",
                        constitution_kill=False,
                    )
                    ctx.verdict.evidence["why_gate"] = ctx._why_result.to_dict()
                    if ctx._why_result.blocked:
                        # WHY rejected PASS → downgrade to UNKNOWN
                        logger.info(f"[V9.0-WHY-GATE] PASS blocked by WHY: {ctx._why_result.falsification_reason[:100]}")
                        ctx.verdict.ctx.verdict = "UNKNOWN"
                        ctx.verdict.ctx.reasoning += f" | [WHY-GATE BLOCKED] {ctx._why_result.falsification_reason[:100]}"
                        ctx.verdict.ctx.confidence = min(ctx.verdict.ctx.confidence, 0.4)
                    elif ctx._why_result.decision.name == "UPHOLD":
                        # WHY can't decide — flag but keep PASS
                        ctx.verdict.ctx.reasoning += f" | [WHY-GATE UPHOLD] {ctx._why_result.necessity_reason[:80]}"
            except Exception as _why_err:
                logger.debug(f"[V9.0-WHY-GATE] WHY Gate error (non-blocking): {_why_err}")
            
            #  Feedback loop: record outcome to PolicyApplier
            # để principles cập nhật success_rate
            # [V104.39 #A] Re-enabled feedback loop (was: if False)
            if ctx._enable_closed_loop and self.policy_applier and ctx.applied_principle_ids:
                try:
                    self.policy_applier.record_outcome(ctx.applied_principle_ids, ctx.verdict.ctx.verdict)
                except Exception as e:
                    logger.debug(f"PolicyApplier record_outcome error: {e}")
            
            #  Add adversary + prediction info to verdict evidence
            if ctx.adversary_result:
                ctx.verdict.evidence["adversary"] = {
                    "primary_value": ctx.adversary_result.ctx.primary_value,
                    "adversary_values": ctx.adversary_result.adversary_values,
                    "final_value": ctx.adversary_result.final_value,
                    "agreement_score": ctx.adversary_result.agreement_score,
                    "conflict_detected": ctx.adversary_result.conflict_detected,
                    "strategy": ctx.adversary_result.strategy,
                }
            if ctx.prediction_verdict:
                ctx.verdict.evidence["prediction"] = {
                    "predicted_verdict": ctx.prediction_verdict,
                    "skipped_api": ctx.prediction_skip_api,
                }
            
            # [V5.3-WIRE] Multi-LLM cross-check — runs AFTER Step 5.5 adversary verify.
            # TẠI SAO: adversary cross-validates sources; multi_llm_check cross-validates
            # LLM providers themselves (DNA SCP #20 — ảo giác đồng thuận). Two independent
            # layers: source-level (adversary) + model-level (multi-LLM).
            # Opt-in via SCP_MULTI_LLM_CHECK=1 (default OFF — adds 2 LLM API calls/question).
            # If providers disagree (speculative=True) → lower confidence by 0.1.
            # [Task 45-B] Multi-LLM check block extracted to _run_multi_llm_check()
            # to reduce judge() CC.
            self._run_multi_llm_check(ctx.verdict, ctx.question, ctx.ai_answer)
            
            # [V5.7-WHY] Change 3: WHY confidence adjustment (opt-in).
            # TẠI SAO: WHY engine currently only enriches evidence + flips verdict in
            # extreme cases (FAIL→FAIL, CONFLICT→CONFLICT — see lines ~2659 below).
            # But subtle WHY vs SLM disagreements don't influence confidence at all.
            # This change adds a fine-grained confidence adjustment BEFORE the existing
            # verdict-flip code runs (so we compare against the SLM's original verdict):
            #   - why_result.verdict == "FAIL"  + SLM says "PASS" → lower confidence by 0.2
            #   - why_result.verdict == "PASS"  + SLM says "PASS" → boost confidence by 0.1
            #   - why_result.verdict == "CONFLICT" + SLM says "PASS" → lower confidence by 0.15
            #   - Other combinations → no change
            # SAFETY: opt-in via SCP_WHY_CONFIDENCE_ADJUST=1 (default OFF — no behavior
            # change). DON'T override verdict (existing flip code at lines ~2659 handles
            # that). Wrap in try/except — adjustment failure MUST NOT break /ask.
            # NOTE: This runs BEFORE the existing flip code, so verdict.verdict still
            # reflects the SLM-led verdict at this point.
            # [Task 45-B] V5.7 WHY confidence adjustment extracted to
            # _apply_why_confidence_adjust() to reduce judge() CC.
            self._apply_why_confidence_adjust(ctx.verdict, ctx.why_plan, ctx.why_result)
            
            #  Add WHY Engine plan to verdict evidence
            # [Task 45-B] WHY-plan-to-verdict block extracted to _attach_why_to_verdict()
            # to reduce judge() CC. Returns possibly-updated confidence.
            ctx.confidence = self._attach_why_to_verdict(
                ctx.verdict, ctx.why_plan, ctx.why_result, ctx.confidence, ctx.question, ctx.ai_answer, ctx.primary_domain
            )
            
            # [SCP-DNA-FIX R9-5] Guard verdict_history mutation with
            # _verdict_history_lock — get_stats() (admin endpoint event-loop
            # thread) iterates concurrently. Without lock, CPython raises
            # RuntimeError: list changed size during iteration. Same bug class
            # as R8-6 (healing_history). Lock is defined in RealityJudge.__init__
            # (judge.py) — accessible here via mixin self.
            with self._verdict_history_lock:
                self.verdict_history.append(ctx.verdict)
                if len(self.verdict_history) > 100:
                    self.verdict_history = self.verdict_history[-100:]  # [FIX LEAK] Cap to 100
            
            #  Cognitive Engine — 5 layers analysis
            # [V104.47 #5] TẠI SAO: was `if self.cognitive and why_plan:` → cognitive
            # dead when why_plan=None (default before V104.46). Now closed-loop is ON
            # by default, but why_plan can still be None on error. Fix: run cognitive
            # even without why_plan — pass None, CognitiveEngine handles it (V104.42 #AY).
            # [Task 45-B] Cognitive Engine block extracted to _run_cognitive_engine()
            # to reduce judge() CC.
            self._run_cognitive_engine(
                ctx.verdict, ctx.why_plan, ctx.question, ctx.primary_domain, ctx.confidence, ctx.primary, ctx.slm_responses, ctx.reality_check
            )
            
            #  Cognitive Gate — cognitive layers AFFECT verdict
            # MetaFalsifier/CounterQuestion/ProofGraph/RecursiveWhy có thể downgrade verdict
            # [Task 45-B] Cognitive Gate block extracted to _apply_cognitive_gate()
            # to reduce judge() CC. Returns possibly-updated confidence.
            ctx.confidence = self._apply_cognitive_gate(
                ctx.verdict, ctx.why_plan, ctx.confidence, ctx.question, ctx.primary_domain, ctx.slm_responses
            )
            
            #  Save prediction for future verification (Predictive module activated)
            # Chỉ save cho real-time domains (weather/crypto/currency) — chúng thay đổi theo thời gian
            # → có thể verify lại sau 1h/1d/1w để xem prediction có đúng không
            if (self.predictor and ctx.verdict.ctx.verdict == "PASS"
                    and ctx.primary_domain in ("weather", "finance", "conversion")
                    and ctx.confidence > 0.5):
                try:
                    from datetime import datetime as _dt
                    from datetime import timedelta as _td
                    # Save prediction với check_date = 1 hour sau (verify temporal stability)
                    ctx.check_date = (_dt.now() + _td(hours=1)).strftime("%Y-%m-%d %H:%M")
                    ctx.real_value = ctx.verdict.ctx.reality_check.get("real_value")
                    ctx.source = ctx.verdict.ctx.reality_check.get("source", "")
                    ctx.pred_id = self.predictor.save_prediction(
                        question=ctx.question,
                        ai_answer=ctx.ai_answer,
                        domain=ctx.primary_domain,
                        check_date=ctx.check_date,
                        source=ctx.source,
                        entity=ctx.question[:50],
                        current_value=ctx.real_value,
                        confidence=ctx.confidence,
                    )
                    ctx.verdict.evidence["prediction_saved"] = {
                        "pred_id": ctx.pred_id,
                        "check_date": ctx.check_date,
                        "saved_value": str(ctx.real_value) if ctx.real_value is not None else None,
                    }
                except Exception as e:
                    logger.debug(f"Predictive save error: {e}")
            
            # [V31C] Log verdict to Calibration Engine
            if self.calibration:
                try:
                    self.calibration.log_verdict(
                        domain=ctx.primary_domain,
                        slm_name=ctx.primary.get("slm_name", "") if ctx.primary else "",
                        confidence=ctx.confidence,
                        actual_verdict=ctx.verdict.ctx.verdict,
                        question=ctx.question[:200],
                        cycle_id=ctx.cycle_count,
                    )
                    # Periodically recompute factors (every 50 cycles)
                    if ctx.cycle_count > 0 and ctx.cycle_count % 50 == 0:
                        try:
                            self.calibration.recompute_factors(min_samples=10)
                        except Exception as e:
                            logger.debug(f"Calibration recompute error: {e}")
                except Exception as e:
                    logger.debug(f"Calibration log error: {e}")
            
            # [V45→V68] Question Tracker — log every question as NEW / REPEAT / INTERNAL
            try:
                from scp.meta.question_tracker import get_question_tracker
                ctx.tracker = get_question_tracker()
                # [V68 FIX] Use explicit source if provided, otherwise auto-detect
                # Was (V64): src = "generator" if cycle_count > 0 else "external"
                #   → ALL questions from main loop got "generator" label, even real ones
                # Now (V68): caller passes source="real_fetcher" / "curiosity" / "external"
                #   → accurate labeling in question_events table
                if not ctx.source:
                    ctx.src = "generator" if ctx.cycle_count > 0 else "external"
                else:
                    ctx.src = ctx.source
                ctx._duration_ms = (time.perf_counter() - ctx._judge_start_perf) * 1000.0
                try:
                    ctx._slm_count = len(ctx.valid_responses)
                except NameError:
                    # silent-by-design: documented default — missing responses list logs a null slm_count
                    ctx._slm_count = None
                ctx.tracker.log(
                    question=ctx.question,
                    source=ctx.src,
                    domain=ctx.primary_domain,
                    verdict=ctx.verdict.ctx.verdict,
                    confidence=ctx.confidence,
                    cycle_id=ctx.cycle_count,
                    duration_ms=round(ctx._duration_ms, 1),
                    slm_count=ctx._slm_count,
                )
            except Exception as e:
                logger.debug(f"QuestionTracker log error: {e}")
            
            # [V64→V83] Save PASS results to knowledge table
            # [V78 FIX] extract real_val from SLM response or ai_answer
            # [V83 FIX] Don't save "Kiểm tra lại:" questions (curiosity re-asks)
            #   → was saving curiosity questions as knowledge, verified 60+ times
            # [V83 FIX] Don't save questions that are just numbers (Star Wars heights)
            #   → was saving "180", "190" as verified_value (garbage)
            if ctx.verdict.ctx.verdict == "PASS" and ctx.confidence > 0.5:
                #  Skip curiosity re-ask questions
                if ctx.question.lower().startswith("kiểm tra lại:"):
                    pass  # Don't save curiosity questions to knowledge
                #  Skip questions where ai_answer is just a number (likely SWAPI garbage)
                elif ctx.ai_answer and ctx.ai_answer.strip().isdigit() and len(ctx.ai_answer.strip()) <= 4:
                    pass  # Don't save bare numbers as knowledge
                else:
                 try:
                    ctx.real_val = ctx.verdict.ctx.reality_check.get("real_value") if ctx.verdict.ctx.reality_check else None
                    ctx.source = ctx.verdict.ctx.reality_check.get("source", "") if ctx.verdict.ctx.reality_check else ""
            
                    #  Fallback: extract from SLM responses if reality_check empty
                    if ctx.real_val is None and ctx.verdict.ctx.slm_responses:
                        for ctx.r in ctx.verdict.ctx.slm_responses:
                            ctx.ev = ctx.r.get("evidence", {})
                            if ctx.ev.get("value") is not None:
                                ctx.real_val = ctx.ev["value"]
                                ctx.source = ctx.ev.get("source", ctx.r.get("slm_name", "SLM"))
                                break
            
                    #  Fallback: use ai_answer as the value (it's verified by PASS)
                    if ctx.real_val is None and ctx.ai_answer:
                        ctx.real_val = ctx.ai_answer[:200]
                        ctx.source = ctx.source or "verified_ai_answer"
            
                    if ctx.real_val is not None and ctx.source:
                        # [V86 FIX] Was: entity = question[:100].lower().strip()
                        #   → stored entire question as entity (e.g., "tell me about the tv show: friends.")
                        # Now: extract actual entity name from question
                        import re as _re86
                        ctx.entity = None
                        # Pattern: "Tell me about X" / "Tell me about the TV show: X" / "Tell me about the book: X"
                        ctx.m = _re86.match(r'tell\s+me\s+about\s+(?:the\s+(?:tv\s+show|movie|book|star\s+wars\s+\w+)\s*[:\-]?\s*)?(.+?)\.?\s*$', ctx.question, _re86.I)
                        if ctx.m: ctx.entity = ctx.m.group(1).strip().lower()
                        # Pattern: "What does the Bible say in X?"
                        if not ctx.entity:
                            ctx.m = _re86.match(r'what\s+does\s+the\s+bible\s+say\s+in\s+(.+?)\??$', ctx.question, _re86.I)
                            if ctx.m: ctx.entity = f"bible:{ctx.m.group(1).strip().lower()}"
                        # Pattern: "What is the recipe for X?"
                        if not ctx.entity:
                            ctx.m = _re86.match(r'what\s+is\s+the\s+recipe\s+for\s+(.+?)\??$', ctx.question, _re86.I)
                            if ctx.m: ctx.entity = ctx.m.group(1).strip().lower()
                        # Pattern: "How do you make the cocktail X?"
                        if not ctx.entity:
                            ctx.m = _re86.match(r'how\s+do\s+you\s+make\s+the\s+cocktail\s+(.+?)\??$', ctx.question, _re86.I)
                            if ctx.m: ctx.entity = f"cocktail:{ctx.m.group(1).strip().lower()}"
                        # Pattern: "What is a public holiday in X?"
                        if not ctx.entity:
                            ctx.m = _re86.match(r'what\s+is\s+a\s+public\s+holiday\s+in\s+(\w+)\??$', ctx.question, _re86.I)
                            if ctx.m: ctx.entity = f"holiday:{ctx.m.group(1).strip().lower()}"
                        # Pattern: "What is the nutritional value of X?"
                        if not ctx.entity:
                            ctx.m = _re86.match(r'what\s+is\s+the\s+nutritional\s+value\s+of\s+(.+?)\??$', ctx.question, _re86.I)
                            if ctx.m: ctx.entity = f"nutrition:{ctx.m.group(1).strip().lower()}"
                        # Pattern: "What type of thing is X?"
                        if not ctx.entity:
                            ctx.m = _re86.match(r'what\s+type\s+of\s+thing\s+is\s+(.+?)\??$', ctx.question, _re86.I)
                            if ctx.m: ctx.entity = ctx.m.group(1).strip().lower()
                        # Pattern: "When was X born?"
                        if not ctx.entity:
                            ctx.m = _re86.match(r'when\s+was\s+(.+?)\s+born\??$', ctx.question, _re86.I)
                            if ctx.m: ctx.entity = f"person:{ctx.m.group(1).strip().lower()}"
                        # [V104.41 #AI] TẠI SAO: was `entity = question[:100]` → stores
                        # QUESTION as entity → KB contaminated (same bug as curiosity #G).
                        # Fix: skip KB write if no entity extracted — don't use question as entity.
                        if not ctx.entity:
                            # Skip knowledge write — can't store without proper entity
                            pass
                        else:
                            # [V104.42 #AH]  TẠI SAO: V104.42 #AH fix tried to
                            # check the watchlist before KB writes, but constructed
                            # `SourceWatchlist()` with NO args (constructor requires
                            # `store: ReputationStore`) → TypeError → except swallowed
                            # → blocked sources still wrote to KB. Fix: use the
                            # pre-constructed `self._source_watchlist` from __init__.
                            try:
                                ctx._watchlist = self._source_watchlist
                                # [SCP-DNA-FIX R6-6] Source: vulture (Category B dead safety control) + grep verify.
                                # TẠI SAO: SourceWatchlist.ingestion_decision() (source_watchlist.py:115)
                                # and check_source_before_ingestion() (L226) were NEVER called. The
                                # ingestion path only used is_blocked() — a simple boolean that catches
                                # PERMANENTLY-blocked sources (reputation < 0.1) but NOT suspect sources
                                # (require_verification=True) or effective_weight scaling. The tier-aware
                                # defense-in-depth gate ([ROOT-FIX-8] comment at L146) is dead in practice.
                                # Reality evidence: grep `ingestion_decision` / `check_source_before_ingestion`
                                # → 0 callers outside their own module (only __main__ test block).
                                # Fix (observability-first, non-breaking): call ingestion_decision and LOG
                                # the tier-aware verdict for operator visibility. The existing is_blocked()
                                # gate below still controls the write path (fail-safe). A future round can
                                # promote ingestion_decision to gate the write once the tier-lookup path is
                                # hardened. Non-fatal: if ingestion_decision raises, we only log at debug.
                                try:
                                    if ctx._watchlist is not None and hasattr(ctx._watchlist, "ingestion_decision"):
                                        ctx._ing = ctx._watchlist.ingestion_decision(ctx.source, tier=3)
                                        ctx._action = ctx._ing.get("action", "?")
                                        if ctx._action != "commit":
                                            logger.info(
                                                f" Ingestion decision for source={ctx.source}: "
                                                f"action={ctx._action} weight={ctx._ing.get('effective_weight')} "
                                                f"require_verification={ctx._ing.get('require_verification')} "
                                                f"reason={ctx._ing.get('reason', '')[:80]}"
                                            )
                                        ctx.verdict.evidence.setdefault("ingestion_decisions", []).append({
                                            "source": ctx.source, "action": ctx._action,
                                            "effective_weight": ctx._ing.get("effective_weight"),
                                            "require_verification": ctx._ing.get("require_verification"),
                                        })
                                except Exception as _ie:
                                    logger.debug(f" ingestion_decision logging failed: {_ie}")
                                if ctx._watchlist and ctx._watchlist.is_blocked(ctx.source):
                                    logger.warning(f"[V104.42 #AH] Knowledge write blocked by watchlist: source={ctx.source}")
                                    pass  # skip to except/else
                                else:
                                    raise _AllowedByWatchlist()  # proceed to INSERT
                            except _AllowedByWatchlist as e:
                                logger.warning(f"Silent except: {e}")  # source allowed (or watchlist unavailable — fail-open for availability)
                            except Exception as _wl_err:
                                logger.debug(f"[V104.42 #AH] Watchlist check error: {_wl_err}")
                                pass  # on error, allow (fail-open for availability)
            
                            try:
                                # [V79 FIX] INSERT OR REPLACE was resetting times_verified to 1
                                # because REPLACE deletes the row, then subquery returns 0.
                                # Now: try INSERT first, if conflict (UNIQUE constraint), UPDATE.
                                try:
                                    db_exec(
                                        "INSERT INTO knowledge (entity, attribute, value, value_type, confidence, source, timestamp, times_verified) "
                                        "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                                        (ctx.entity, "verified_value", str(ctx.real_val)[:500],
                                         'float' if isinstance(ctx.real_val, (int, float)) else 'str',
                                         ctx.confidence, ctx.source, datetime.now().isoformat())
                                    )
                                except Exception:
                                    # Row already exists → UPDATE times_verified + value
                                    # silent-by-design: documented upsert — INSERT failure means the row exists; the UPDATE path follows
                                    db_exec(
                                        "UPDATE knowledge SET value = ?, confidence = ?, source = ?, timestamp = ?, "
                                        "times_verified = times_verified + 1 "
                                        "WHERE entity = ? AND attribute = ?",
                                        (str(ctx.real_val)[:500], ctx.confidence, ctx.source,
                                         datetime.now().isoformat(), ctx.entity, "verified_value")
                                    )
                            except Exception as e:
                                logger.debug(f"Knowledge save error: {e}")
                 except Exception as e:
                    # [ROOT-FIX 5] Was `except Exception as e: pass` — swallowed knowledge-save
                    # errors silently → KB write failures invisible → "ảo giác đồng thuận"
                    # (system thinks it learned but didn't).
                    logger.warning(f"[judge] knowledge save outer block failed: {e}")
            
            #  ExperienceEngine — learn from every verdict
            #  Skip empty questions — was saving experiences with "" question
            if self.experience is not None and ctx.question and len(ctx.question.strip()) > 0:
                try:
                    ctx.real_val = ctx.verdict.ctx.reality_check.get("real_value") if ctx.verdict.ctx.reality_check else None
                    ctx.lesson = {
                        "question": ctx.question,
                        "ai_answer": ctx.ai_answer,
                        "real_value": str(ctx.real_val) if ctx.real_val is not None else None,
                        "error_type": ctx.primary_domain or "unknown",
                        "cause": (ctx.verdict.ctx.reasoning or "")[:200],
                        "timestamp": datetime.now().isoformat(),
                        "lesson_type": f"VERDICT_{ctx.verdict.ctx.verdict}",
                        "policy_action": f"verdict_{ctx.verdict.ctx.verdict.lower()}",
                        "policy_target": ctx.primary_domain or "unknown",
                        "policy_value": ctx.confidence,
                        "lesson_description": f"{ctx.verdict.ctx.verdict}: {ctx.question[:100]}",
                        "entity": ctx.primary_domain or "unknown",
                        "domain": ctx.primary_domain or "unknown",
                        "source": "reality_judge",
                        "verdict": ctx.verdict.ctx.verdict,
                    }
                    self.experience.learn([ctx.lesson])
                except Exception as e:
                    logger.debug(f"ExperienceEngine learn error: {e}")
            
            #  FalsificationEngine — translate verdict sang skeptical status
            # [Task 45-B] Falsification block extracted to _run_falsification() to reduce judge() CC.
            self._run_falsification(ctx.verdict, ctx.question, ctx.ai_answer)
            
            #  ErrorStore — record nếu verdict FAIL hoặc low confidence
            if self.error_store and (ctx.verdict.ctx.verdict in ("FAIL", "CONFLICT") or ctx.verdict.ctx.confidence < 0.5):
                try:
                    self.error_store.add(
                        question=ctx.question[:500] if ctx.question else "",
                        answer=ctx.verdict.ctx.final_answer[:500] if ctx.verdict.ctx.final_answer else "",
                        verdict=ctx.verdict.ctx.verdict,
                        domain=ctx.verdict.ctx.domain or "unknown",
                        error_type="low_confidence" if ctx.verdict.ctx.confidence < 0.5 else ctx.verdict.ctx.verdict.lower(),
                        details={
                            "confidence": ctx.verdict.ctx.confidence,
                            "reasoning": ctx.verdict.ctx.reasoning[:200] if ctx.verdict.ctx.reasoning else "",
                        },
                    )
                except Exception as e:
                    logger.debug(f" ErrorStore add error: {e}")
            
            #  Governance — apply UPHOLD/KILL/ESCALATE decision
            if self.governance:
                try:
                    # Build antibody_results from the actual SLM records. The
                    # adapter is a tested boundary; it never silently marks errors
                    # as passed and emits only canonical policy severities.
                    ctx.ab_results = _build_governance_antibody_results(ctx.verdict.ctx.slm_responses)
                    ctx.gov_decision = self.governance.decide(
                        ctx={"domain": ctx.verdict.ctx.domain, "session_id": ""},
                        verdict={
                            "confidence": ctx.verdict.ctx.confidence,
                            "antibody_results": ctx.ab_results,
                            "hallucination_detected": ctx.verdict.ctx.verdict == "FAIL",
                            "missing_evidence": ctx.verdict.ctx.verdict == "UNKNOWN",
                        },
                        council_confidence=ctx.verdict.ctx.confidence,
                    )
                    ctx.verdict.evidence["governance_decision"] = ctx.gov_decision.decision.value
                    ctx.verdict.evidence["governance_reason"] = ctx.gov_decision.reason
                    ctx.verdict.evidence["governance_principle_violations"] = ctx.gov_decision.principle_violations
            
                    # [V104.40 #Q] TẠI SAO: old KILL only changed PASS→FAIL but kept
                    # final_answer intact → client still received the killed content.
                    # Constitution: "abstain rather than fabricate". Fix: on KILL,
                    # clear final_answer (abstain) regardless of current verdict.
                    # Also handle ESCALATE: set verdict to UNKNOWN + flag for human review.
                    if ctx.gov_decision.decision.value == "KILL":
                        # KILL = abstain entirely — no answer to client
                        ctx.verdict.ctx.verdict = "FAIL"
                        ctx.verdict.ctx.final_answer = ""  # [V104.40 #Q] abstain — don't return killed content
                        ctx.verdict.ctx.reasoning += f" | Governance KILL: {ctx.gov_decision.reason} (answer withheld)"
                        ctx.verdict.evidence["governance_abstain"] = True
                        logger.info(f"[V104.40] Governance KILL abstain: {ctx.gov_decision.reason}")
                        # [V104.44 #CV] TẠI SAO: was no notification on KILL → operators
                        # not alerted to security events. Fix: notify on KILL/ESCALATE.
                        if self.notifications:
                            try:
                                self.notifications.notify(
                                    event_type="governance_kill",
                                    title="Governance KILL",
                                    message=f"Question: {ctx.question[:100]}\nReason: {ctx.gov_decision.reason}",
                                    severity="critical",
                                )
                            except Exception as e:
                                # [ROOT-FIX 5] Was `except Exception as e: pass` — swallowed
                                # notification dispatch errors silently → operators miss
                                # critical KILL alerts.
                                logger.warning(f"[judge] governance_kill notify failed: {e}")
                    elif ctx.gov_decision.decision.value == "ESCALATE":
                        # [V104.40 #Q] ESCALATE = human review required — don't auto-PASS
                        if ctx.verdict.ctx.verdict == "PASS":
                            ctx.verdict.ctx.verdict = "UNKNOWN"
                            ctx.verdict.ctx.reasoning += f" | Governance ESCALATE: {ctx.gov_decision.reason} (human review required)"
                            ctx.verdict.evidence["human_review_required"] = True
                            logger.info(f"[V104.40] Governance ESCALATE: {ctx.gov_decision.reason}")
                except Exception as e:
                    logger.debug(f" Governance decide error: {e}")
            
            # ============================================================
        
