from typing import Any
from scp.runtime.judge_parts.phases.context import JudgeContext
import time
from datetime import datetime
import os
import logging
logger = logging.getLogger(__name__)

class Phase2InputDetectionMixin:
    def _phase2_input_detection(self, ctx: JudgeContext) -> Any:
            #  STEP 0: INPUT DETECTION — chạy TRƯỚC khi route SLMs
            # ============================================================
            ctx.v98_threat_signal = None
            ctx.v98_classification = None
            ctx.v98_guard_verdict = None
            ctx.v98_attack_match = None
            ctx.v98_early_fail = False
            
            # 0a. MemoryPoisoningGuard — check question for poisoning
            if self.memory_guard:
                try:
                    ctx.session_id = (ctx.v98_context or {}).get("session_id", f"cycle_{ctx.cycle_count}")
                    ctx.v98_guard_verdict = self.memory_guard.check(ctx.session_id, ctx.question)
                    if ctx.v98_guard_verdict.is_poisoned:
                        logger.warning(f" MemoryPoisoningGuard: risk={ctx.v98_guard_verdict.risk_score} patterns={ctx.v98_guard_verdict.detected_patterns}")
                        if ctx.v98_guard_verdict.recommendation == "clear":
                            # Severe poisoning → early FAIL
                            ctx.v98_early_fail = True
                except Exception as e:
                    logger.debug(f" MemoryPoisoningGuard error: {e}")
            
            # 0b. AttackPatternMemory — check against known attack rules
            if self.attack_memory:
                try:
                    ctx.v98_attack_match = self.attack_memory.check_against_rules(ctx.question)
                    if ctx.v98_attack_match.get("matched"):
                        logger.info(f" AttackPatternMemory match: rule={ctx.v98_attack_match.get('rule_id')}")
                        # [V104.18 #1 FIX] Promoted rule match → early FAIL (was: log only)
                        if ctx.v98_attack_match.get("promoted", False):
                            ctx.v98_early_fail = True
                except Exception as e:
                    logger.debug(f" AttackPatternMemory error: {e}")
            
            # [V104.43 #CB] [P0-4/P1-6 FIX] TẠI SAO: UnifiedPatternDetector was
            # initialized but never called on hot path → unified patterns dead.
            # V104.43 fix called detect() but had 3 bugs:
            #   (1) `_unified_result.get("matched")` — but UnifiedThreatAssessment is a
            #       @dataclass, not a dict → AttributeError → swallowed by except.
            #       Correct attr: `is_attack`. Other attrs: `matched_patterns`, `severity`.
            #   (2) `verdict.evidence[...]` — verdict not created yet (created ~line 2251).
            #       Fix: store in `_pre_verdict_evidence`, merge after verdict creation.
            #   (3) `any(p.get("severity") == "critical" for p in matched_patterns)` —
            #       matched_patterns is List[str] (rule names), not List[dict]. The
            #       severity lives on the assessment itself: `_unified_result.severity`.
            if self.unified_detector:
                try:
                    ctx._unified_result = self.unified_detector.detect(ctx.question, ctx.ai_answer or "")
                    if ctx._unified_result and getattr(ctx._unified_result, "is_attack", False):
                        logger.info(f"[V104.43 #CB] UnifiedDetector match: severity={ctx._unified_result.severity} patterns={ctx._unified_result.matched_patterns}")
                        ctx._pre_verdict_evidence["v102_unified_detection"] = ctx._unified_result.to_dict() if hasattr(ctx._unified_result, "to_dict") else {"is_attack": True, "severity": ctx._unified_result.severity, "matched_patterns": ctx._unified_result.matched_patterns}
                        # If CRITICAL unified pattern → early FAIL
                        if getattr(ctx._unified_result, "severity", "none") == "critical":
                            ctx.v98_early_fail = True
            
                        # [Task 40-B / OPT-13] Wire CWEExploitStore — look up CWE for detected patterns.
                        # TẠI SAO: CWEExploitStore created (knowledge/cwe_exploit_store.py) but
                        # 0 callers → dead code (DNA #6 violated). When UnifiedDetector flags an
                        # attack, map the matched pattern to a CWE so the verdict carries concrete
                        # mitigation guidance + antibody hints. ADDITIVE: ImportError/Exception is
                        # non-fatal; original UnifiedDetector flow untouched.
                        # [OPT-42] Extracted to _map_cwe_for_attack() to reduce judge() CC.
                        self._map_cwe_for_attack(ctx._unified_result, ctx._pre_verdict_evidence)
                except Exception as e:
                    logger.debug(f"[V104.43 #CB] UnifiedDetector error: {e}")
            
            # 0c. ThreatDetector + AttackClassifierEngine — chỉ chạy nếu có v98_context (IP/headers)
            if ctx.v98_context and self.threat_detector and self.attack_classifier:
                try:
                    # [V104.19 #2 FIX] ThreatDetector: always run via ThreadPoolExecutor
                    try:
                        import concurrent.futures as _cf
                        ctx._td_pool = _cf.ThreadPoolExecutor(max_workers=1)
                        ctx.v98_threat_signal = ctx._td_pool.submit(
                            asyncio.run,  # [FIX-CRIT-27 BUG 1] was _asyncio.run (NameError — _asyncio never imported at module scope) → ThreatDetector dead
                            self.threat_detector.analyze(
                                ip=ctx.v98_context.get("ip", "127.0.0.1"),
                                headers=ctx.v98_context.get("headers", {}),
                                body=ctx.question,
                                endpoint=ctx.v98_context.get("endpoint", "/ask"),
                                session_id=ctx.v98_context.get("session_id", ""),
                            )
                        ).ctx.result(timeout=10)
                        ctx.v98_classification = self.attack_classifier.classify(ctx.v98_threat_signal)
                        ctx._td_pool.shutdown(wait=False)
                    except Exception as e:
                        logger.debug(f" ThreatDetector error: {e}")
            
                    if ctx.v98_classification and ctx.v98_classification.severity == "critical":
                        logger.warning(f" Critical threat: actor={ctx.v98_classification.actor} attack={ctx.v98_classification.ctx.attack_type}")
                        ctx.v98_early_fail = True
                except Exception as e:
                    logger.debug(f" ThreatDetector error: {e}")
            
            # Early FAIL nếu memory poisoning severe HOẶC critical threat detected
            if ctx.v98_early_fail:
                ctx.verdict = JudgeVerdict(
                    question=ctx.question,
                    slm_responses=[],
                    final_answer="[BLOCKED BY V98 SECURITY] Memory poisoning or critical threat detected.",
                    confidence=0.0,
                    verdict="FAIL",
                    reasoning=f"V98 early block: guard={ctx.v98_guard_verdict.recommendation if ctx.v98_guard_verdict else 'none'}, "
                             f"threat={ctx.v98_classification.severity if ctx.v98_classification else 'none'}, "
                             f"attack_match={ctx.v98_attack_match.get('matched', False) if ctx.v98_attack_match else False}",
                    evidence={
                        "v98_guard": ctx.v98_guard_verdict.to_dict() if ctx.v98_guard_verdict else None,
                        "v98_threat": ctx.v98_threat_signal.to_dict() if ctx.v98_threat_signal else None,
                        "v98_classification": ctx.v98_classification.to_dict() if ctx.v98_classification else None,
                        "v98_attack_match": ctx.v98_attack_match,
                        "early_fail": True,
                    },
                    domain="security",
                    timestamp=ctx.ts,
                )
                return ctx.verdict
            
            # [V104.52] Predictive Defense — run AttackPredictor when threat detected
            # TẠI SAO: V98 detects current threats, but predictor forecasts FUTURE attacks.
            # If predictor confidence > 0.7 + threat_type critical → trigger escalation.
            # This is the "30-min warning" mechanism — SCP predicts attack, alerts human,
            # if timeout → default defensive playbook executes.
            if self.attack_predictor and ctx.v98_classification and ctx.v98_classification.severity in ("medium", "high", "critical"):
                try:
                    # Build signals from V98 context + threat data
                    ctx.predictor_signals = {
                        "request_rate_anomaly": min(1.0, getattr(ctx.v98_threat_signal, 'confidence', 0.5) if ctx.v98_threat_signal else 0.3),
                        "geo_distribution_anomaly": 0.4 if (ctx.v98_threat_signal and ctx.v98_threat_signal.asn_intel and not ctx.v98_threat_signal.asn_intel.get("is_residential", True)) else 0.2,
                        "user_agent_pattern_shift": 0.3,
                        "payload_pattern_emergence": 0.6 if (ctx.v98_attack_match and ctx.v98_attack_match.get("matched")) else 0.2,
                        "historical_attack_pattern_match": 0.5 if ctx.v98_attack_match else 0.1,
                        "time_of_day_pattern": 0.3,
                        "threat_intel_correlation": 0.7 if ctx.v98_classification.severity in ("high", "critical") else 0.3,
                        "political_event_correlation": 0.1,
                    }
                    ctx.forecast = self.attack_predictor.predict_cyber_attack(ctx.predictor_signals)
                    ctx._pre_verdict_evidence["v10452_attack_forecast"] = {
                        "threat_type": ctx.forecast.threat_type,
                        "probability": ctx.forecast.probability,
                        "confidence": ctx.forecast.ctx.confidence,
                        "timeframe_min": ctx.forecast.timeframe_min,
                        "recommended_actions": ctx.forecast.recommended_actions,
                        "why": ctx.forecast.why_explanation[:200],
                    }
                    # If high confidence + critical → trigger escalation
                    if (ctx.forecast.ctx.confidence > 0.5 and ctx.forecast.probability > 0.5
                            and self.escalation_manager):
                        ctx._threat = {
                            "id": f"predict_{int(time.time())}",
                            "type": ctx.forecast.threat_type,
                            "severity": ctx.v98_classification.severity,
                            "prediction_confidence": ctx.forecast.ctx.confidence,
                            "description": ctx.forecast.why_explanation[:200],
                        }
                        self.escalation_manager.on_threat_detected(ctx._threat)
                        ctx._pre_verdict_evidence["v10452_escalation_triggered"] = True
                        logger.warning(f"[V104.52] Predictive escalation: {ctx.forecast.threat_type} conf={ctx.forecast.ctx.confidence:.2f}")
                except Exception as e:
                    logger.debug(f"[V104.52] Predictor error: {e}")
            
            # [FIX-CRIT-27 BUG 3] KB short-circuit MOVED here (was above Step 0a-0c,
            # bypassing ALL V98 security). Now security checks have already run —
            # if v98_early_fail was True, we returned above. Otherwise, the KB
            # short-circuit is safe to apply (authoritative cached answer for a
            # question that PASSED all security checks).
            # Note: verdict_type/final_answer/confidence may be unset if KB didn't hit —
            # use getattr-style safe checks.
            ctx._kb_sc_verdict = ctx.verdict_type
            ctx._kb_sc_answer = ctx.final_answer
            ctx._kb_sc_conf = ctx.confidence
            if ctx._kb_sc_verdict == "PASS" and ctx._kb_sc_answer and ctx._kb_sc_conf >= 0.85 and ctx.v100_kb_hits:
                ctx._best_hit = ctx.v100_kb_hits[0]
                ctx._hit_tier = getattr(ctx._best_hit, 'source_tier', 9)
                if ctx._hit_tier <= 2:
                    logger.info(f"[V104.46 #BI] KB short-circuit early return (post-security): tier={ctx._hit_tier}")
                    ctx.verdict = JudgeVerdict(
                        question=ctx.question,
                        final_answer=ctx.final_answer,
                        confidence=ctx.confidence,
                        verdict=ctx.verdict_type,
                        domain="general",
                        reasoning=ctx.reasoning,
                        evidence={"v100_kb_short_circuit": True, "source_tier": ctx._hit_tier},
                        timestamp=ctx.ts,
                    )
                    return ctx.verdict
            
            # [V104.44 #BX] [P0-4/P1-6 FIX] ErrorStoreIndex.search_similar — check if
            # this question is similar to past FAILs. TẠI SAO: V104.44 fix had 4 bugs:
            #   (1) Event-loop logic INVERTED: `run_until_complete(...) if is_running()`
            #       — but run_until_complete RAISES RuntimeError when loop is running.
            #       The condition should be: if NOT running → run_until_complete;
            #       if running → use sync fallback. Was backwards.
            #   (2) `verdict.evidence[...]` — verdict not created yet. Fix: store in
            #       `_pre_verdict_evidence`, merge after verdict creation.
            #   (3) `adjusted_threshold` computed here was OVERWRITTEN at line ~1453
            #       (`adjusted_threshold = self.confidence_threshold`) and ~1464
            #       (domain tolerance). Fix: store as `_es_index_threshold_boost` and
            #       apply AFTER those resets.
            #   (4) `search_similar(question, limit=3)` kwarg — ErrorStoreIndex uses
            #       `top_k` (FIX-D added `limit` alias, so this now works).
            if self.error_store_index:
                try:
                    ctx._similar = None
                    # Prefer sync path — avoids event-loop entanglement entirely.
                    if hasattr(self.error_store_index, '_search_sync'):
                        ctx._similar = self.error_store_index._search_sync(ctx.question, limit=3)
                    else:
                        import asyncio as _a
                        try:
                            ctx._loop = _a.get_event_loop()
                            if ctx._loop.is_running():
                                # Cannot run_until_complete inside a running loop —
                                # schedule in a thread to avoid blocking + RuntimeError.
                                import asyncio as _a2
                                ctx._similar = _a2.run_coroutine_threadsafe(
                                    self.error_store_index.search_similar(ctx.question, top_k=3),
                                    ctx._loop
                                ).ctx.result(timeout=2.0)
                            else:
                                ctx._similar = ctx._loop.run_until_complete(
                                    self.error_store_index.search_similar(ctx.question, top_k=3)
                                )
                        except Exception:
                            # silent-by-design: best-effort similar-errors probe — None disables the v104 evidence block below
                            ctx._similar = None
                    if ctx._similar:
                        ctx._pre_verdict_evidence["v104_similar_errors"] = [
                            {"question": (s.get("question", "") if isinstance(s, dict) else getattr(s, "question", ""))[:100],
                             "verdict": s.get("verdict", "") if isinstance(s, dict) else getattr(s, "verdict", "")}
                            for s in ctx._similar[:3]
                        ]
                        # If similar past errors were FAIL → raise confidence threshold
                        ctx._fail_count = sum(1 for s in ctx._similar
                                          if (s.get("verdict", "") if isinstance(s, dict) else getattr(s, "verdict", "")) == "FAIL")
                        if ctx._fail_count >= 2:
                            ctx._es_index_threshold_boost = 0.1  # applied after domain-tolerance reset
                            logger.info(f"[V104.44 #BX] Similar errors: {ctx._fail_count} FAILs → threshold boost +{ctx._es_index_threshold_boost}")
                except Exception as e:
                    logger.debug(f"[V104.44 #BX] ErrorStoreIndex search error: {e}")
            
        
