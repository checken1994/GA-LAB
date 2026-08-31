# Auto-extracted from judgecore_mixin.py
import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from scp.core.db_manager import db_exec
from scp.core.evidence_filter import filter_slm_responses
from scp.meta.severity import Severity
from scp.runtime.judge_parts.types import JudgeVerdict, _AllowedByWatchlist
from scp.meta.scp_meta import SCPMeta as _SCPMeta

@dataclass
class JudgeCoreMixin:
    """Mixin for RealityJudge — provides judge."""

    def judge(self, question: str, ai_answer: str='', cycle_count: int=0, source: str='', v98_context: dict[str, Any] | None=None, domain_override: str | None=None) -> JudgeVerdict:
        """Process a question through the reality-checking pipeline.

        [G4-FIX P0-12] ACTUAL phases in this method (audited by Task G4-C).
        The doc's "10-phase pipeline" claim (SCP_FULL_CONTEXT_FOR_AI.md §2.2)
        is FICTION. judge_phases.py defines 6 phases but is NOT wired into
        THIS method — it runs only in SHADOW MODE from judge.py:927 (the
        async wrapper) for comparison logging. THIS method is the actual
        production verdict path. CC≈300 (god method — needs refactor,
        deferred; full split = 21 days).

        Line ranges below refer to THIS file (judgecore_mixin.py).

        | #  | Lines      | LOC  | What it actually does                                                              |
        |----|------------|------|------------------------------------------------------------------------------------|
        | 0a | L178-226   |  49  | Setup: timer, perf counter, _enable_closed_loop, pre-verdict evidence dict; run WHY engine (`_run_why_engine`); KnowledgeArbiter conflict check (`_check_knowledge_conflicts`) |
        | 1  | L227-263   |  37  | V100 PHASE 1 — KB retrieval via `domain_knowledge_store.search` (returns hits; short-circuit deferred to step 4) |
        | 2  | L264-379   | 116  | V98 STEP 0 — Input detection: MemoryPoisoningGuard, AttackPatternMemory, UnifiedPatternDetector (with CWE mapping via `_map_cwe_for_attack`), ThreatDetector + AttackClassifierEngine. Early FAIL return if critical threat / severe poisoning. |
        | 3  | L380-422   |  43  | V104.52 — Predictive Defense: AttackPredictor forecasts future attacks; if high confidence + critical → trigger escalation_manager |
        | 4  | L423-449   |  27  | KB short-circuit (post-security): if KB tier ≤2 + conf ≥0.85 AND passed V98 security → early return PASS. (Moved here by FIX-CRIT-27 BUG 3 — was previously above Step 0, bypassing all security.) |
        | 5  | L450-502   |  53  | V104.44 — ErrorStoreIndex.search_similar: if 2+ past FAILs match this question → boost threshold +0.1 (applied later at step 6) |
        | 6  | L503-561   |  59  | Step 1 — Route (`_route_question`); apply domain tolerance (ExperienceEngine) + PolicyApplier adjustment + VerdictPredictor skip_api decision |
        | 7  | L562-714   | 153  | Step 2 — Call SLMs (parallel via ThreadPoolExecutor, max 4 workers); V88 multi-SLM consensus; LLM (Ollama/OpenRouter) fallback if no SLM returned an answer |
        | 8  | L715-880   | 166  | Steps 3-5 — Filter garbage SLM answers; `_check_consistency`; ConflictResolver (resolve_value); consensus-aware primary SLM selection; calibration; confidence_adjustments |
        | 9  | L881-928   |  48  | ROOT-FIX 43-A — Deterministic SLM short-circuit: MathSLM/ConversionSLM/StatisticsSLM/LogicSLM with conf≥0.95 → return PASS without WHY/adversary/reality verification |
        | 10 | L929-989   |  61  | Step 5.5 — Adversary verify (Wikipedia cross-check); conflict → reduce confidence + flag `_adversary_conflict`; agreement → boost +0.05 |
        | 11 | L990-1349  | 360  | Step 6 — Verdict DECISION: PASS / FAIL / UNKNOWN / PARTIAL / CONFLICT / SPECULATIVE via numeric tolerance / scientific notation / full-string / fuzzy / word-overlap comparison. Includes V105 Phase 9.5 Speculative Mode for creative/hypothetical questions. |
        | 12 | L1350-1465 | 116  | Step 7 — Reality check: V13 RealityEngine + DirectAPIVerifier fallback (FIX v26) + Tree of Thoughts upgrade UNKNOWN→PASS. Also applies `_adversary_conflict` flag (PASS→CONFLICT) and clamps confidence to [0,1]. |
        | 13 | L1466-1492 |  27  | Step 9 — Build JudgeVerdict dataclass (merges `_pre_verdict_evidence` from steps 2, 5, 3) |
        | 14 | L1493-1519 |  27  | V9.0-WHY-GATE — Primary control gate; can downgrade PASS→UNKNOWN if WHY rejects (constitution HARD LOCK: WHY cannot override KILL) |
        | 15 | L1520-1653 | 134  | Post-verdict feedback: PolicyApplier.record_outcome; Multi-LLM cross-check (`_run_multi_llm_check`); WHY confidence adjustment; Cognitive Engine (`_run_cognitive_engine`) + Cognitive Gate (`_apply_cognitive_gate`); save prediction (V35); Calibration log |
        | 16 | L1654-1684 |  31  | V45→V68 — Question Tracker (log every question as NEW / REPEAT / INTERNAL) |
        | 17 | L1685-1808 | 124  | V64→V83 — Save PASS results to knowledge table (`INSERT OR REPLACE`); skip curiosity re-asks and pure-number questions |
        | 18 | L1809-1834 |  26  | V65 — ExperienceEngine.learn from every verdict |
        | 19 | L1835-1855 |  21  | V97 — FalsificationEngine (`_run_falsification`) + ErrorStore.add for FAIL/CONFLICT/low-conf |
        | 20 | L1856-1921 |  66  | V97 — Governance.decide (UPHOLD/KILL/ESCALATE); KILL → clear final_answer (abstain) + notify; ESCALATE → UNKNOWN + flag for human review |
        | 21 | L1922-2091 | 170  | V98 STEP 9 — Counter Response: AttackPolicyEngine.decide → CounterResponseEngine.execute (poison_response, canary); AttackPatternMemory.record_bypass; bypass → downgrade PASS→FAIL + clear answer + notify |
        | 22 | L2092-2117 |  26  | V100 PHASE 6 — Claim extraction + DomainAntibodySystem (38 antibodies, `_run_antibodies`) + claim verification; refuted claim → confidence ×0.5 |
        | 23 | L2118-2138 |  21  | V107 PHASE 6.5 — Logical Auditor (deep logic check via ThreadPoolExecutor, 30s timeout) |
        | 24 | L2139-2159 |  21  | V106 — SelfQuestioningEngine ("Tại sao tôi ra verdict này?") for PASS/FAIL/SPECULATIVE |
        | 25 | L2160-2206 |  47  | V100 PHASE 10 — Learning: save PASS to KnowledgeStore; H8 RedTeamBridge.record_normal_question + record_bypass (false-positive baseline + bypass detection) |
        | 26 | L2207-2287 |  81  | V100 PHASE 11 — Output: phase timings into evidence; V104.45 healing monitor + strategies |
        | 27 | L2288-2375 |  88  | V5.8 — source_reputation.record_outcome (per contributing source) + SCPMeta council review (3 systems vote; SKIP/DEFER_HUMAN → UNKNOWN) + `return verdict` |

        Total: 28 distinct phases/steps across L178-2375 (2198 LOC of method body
        after this 84-line docstring). Phase numbering in inline comments is
        CONTRADICTORY: code says "PHASE 1" at L227 (KB), "STEP 0" at L264 (security,
        AFTER Phase 1), "Step 1" at L503 (routing), "Step 2" at L562 (SLMs),
        "Step 5.5" at L929 (adversary), "Step 6" at L990 (verdict), "Step 7" at
        L1350 (reality), "Step 9" at L1466 (verdict construction), "STEP 9" again
        at L1922 (counter response — same number as verdict construction!),
        "PHASE 6" at L2092 (antibodies — after Step 9 counter response),
        "PHASE 6.5" at L2118, "PHASE 10" at L2160, "PHASE 11" at L2207. Phases
        7-9 of the doc's "10-phase pipeline" do not map to any single contiguous
        code block — they are interleaved across the 28 actual steps.

        V29 / V98 / V100 flow (preserved from earlier docstring, kept for context):
            1. Route → domains
            2.  PolicyApplier: adjust threshold + prefer sources based on principles
            3. SLM predict
            4.  Adversary verify: cross-validate với source khác
            5. Reality check (DirectAPIVerifier)
            6.  VerdictPredictor: skip API nếu prediction confidence cao
            7.  PolicyApplier.record_outcome: feedback loop
            8. Build verdict

        V98 additions (preserved):
            0a.  MemoryPoisoningGuard — check question for poisoning patterns
            0b.  AttackPatternMemory — check against known attack rules
            0c.  ThreatDetector + AttackClassifierEngine — if v98_context has IP/headers
            9a.  AttackPolicyEngine — decide counter phase
            9b.  CounterResponseEngine — execute counter
            9c.  CanaryTokenMonitor — generate canary if Phase 2+
            9d.  AttackPatternMemory.record_bypass — if bypass detected

        Args:
            question: Câu hỏi
            ai_answer: Câu trả lời của AI (nếu có, để verify)
            cycle_count: Số cycle hiện tại từ SCPV14
            source:  Nguồn câu hỏi — "real_fetcher" / "curiosity" / "external" / "generator"
            v98_context:  Optional context dict with IP, headers, session_id for security modules
                         {"ip": str, "headers": dict, "session_id": str, "body": str}

        Returns: JudgeVerdict
        """
        ts = datetime.now().isoformat()
        _judge_start_perf = time.perf_counter()
        from scp.runtime.timing_and_restart import PhaseTimer, QueryTimeoutError, check_timeout
        _v100_timer = PhaseTimer()
        _enable_closed_loop = os.environ.get('SCP_ENABLE_CLOSED_LOOP', '1') == '1'
        verdict = None
        verdict_type = None
        final_answer = ''
        confidence = 0.0
        verdict_evidence_spec = None
        reasoning = ''
        _pre_verdict_evidence: dict[str, Any] = {}
        _adversary_conflict = False
        _adversary_conflict_reason = ''
        _es_index_threshold_boost = 0.0
        why_plan, why_result = self._run_why_engine(question, ai_answer, _enable_closed_loop)
        self._check_knowledge_conflicts(why_result, why_plan, question, _pre_verdict_evidence)
        v100_kb_hits = []
        with _v100_timer.phase('knowledge'):
            if self.domain_knowledge_store:
                try:
                    v100_kb_hits = self.domain_knowledge_store.search(question, domain='', limit=3)
                    if v100_kb_hits:
                        logger.debug(f" KB hit: {len(v100_kb_hits)} records for '{question[:50]}'")
                        _best_hit = v100_kb_hits[0]
                        _hit_tier = getattr(_best_hit, 'source_tier', 9)
                        _hit_conf = getattr(_best_hit, 'confidence', 0)
                        if _hit_tier <= 2 and _hit_conf >= 0.85:
                            final_answer = getattr(_best_hit, 'answer', '')
                            confidence = _hit_conf
                            verdict_type = 'PASS'
                            reasoning = f'KB short-circuit: tier={_hit_tier} conf={_hit_conf:.2f} (cached authoritative)'
                            logger.info(f'[V104.43 #BI] KB short-circuit: tier={_hit_tier} conf={_hit_conf:.2f}')
                except Exception as e:
                    logger.debug(f' KB search error: {e}')
        try:
            check_timeout(_v100_timer.finish(), 'knowledge')
        except QueryTimeoutError as e:
            logger.warning(f'Silent except: {e}')
        v98_threat_signal = None
        v98_classification = None
        v98_guard_verdict = None
        v98_attack_match = None
        v98_early_fail = False
        if self.memory_guard:
            try:
                session_id = (v98_context or {}).get('session_id', f'cycle_{cycle_count}')
                v98_guard_verdict = self.memory_guard.check(session_id, question)
                if v98_guard_verdict.is_poisoned:
                    logger.warning(f' MemoryPoisoningGuard: risk={v98_guard_verdict.risk_score} patterns={v98_guard_verdict.detected_patterns}')
                    if v98_guard_verdict.recommendation == 'clear':
                        v98_early_fail = True
            except Exception as e:
                logger.debug(f' MemoryPoisoningGuard error: {e}')
        if self.attack_memory:
            try:
                v98_attack_match = self.attack_memory.check_against_rules(question)
                if v98_attack_match.get('matched'):
                    logger.info(f" AttackPatternMemory match: rule={v98_attack_match.get('rule_id')}")
                    if v98_attack_match.get('promoted', False):
                        v98_early_fail = True
            except Exception as e:
                logger.debug(f' AttackPatternMemory error: {e}')
        if self.unified_detector:
            try:
                _unified_result = self.unified_detector.detect(question, ai_answer or '')
                if _unified_result and getattr(_unified_result, 'is_attack', False):
                    logger.info(f'[V104.43 #CB] UnifiedDetector match: severity={_unified_result.severity} patterns={_unified_result.matched_patterns}')
                    _pre_verdict_evidence['v102_unified_detection'] = _unified_result.to_dict() if hasattr(_unified_result, 'to_dict') else {'is_attack': True, 'severity': _unified_result.severity, 'matched_patterns': _unified_result.matched_patterns}
                    if getattr(_unified_result, 'severity', 'none') == 'critical':
                        v98_early_fail = True
                    self._map_cwe_for_attack(_unified_result, _pre_verdict_evidence)
            except Exception as e:
                logger.debug(f'[V104.43 #CB] UnifiedDetector error: {e}')
        if v98_context and self.threat_detector and self.attack_classifier:
            try:
                try:
                    import concurrent.futures as _cf
                    _td_pool = _cf.ThreadPoolExecutor(max_workers=1)
                    v98_threat_signal = _td_pool.submit(asyncio.run, self.threat_detector.analyze(ip=v98_context.get('ip', '127.0.0.1'), headers=v98_context.get('headers', {}), body=question, endpoint=v98_context.get('endpoint', '/ask'), session_id=v98_context.get('session_id', ''))).result(timeout=10)
                    v98_classification = self.attack_classifier.classify(v98_threat_signal)
                    _td_pool.shutdown(wait=False)
                except Exception as e:
                    logger.debug(f' ThreatDetector error: {e}')
                if v98_classification and v98_classification.severity == 'critical':
                    logger.warning(f' Critical threat: actor={v98_classification.actor} attack={v98_classification.attack_type}')
                    v98_early_fail = True
            except Exception as e:
                logger.debug(f' ThreatDetector error: {e}')
        if v98_early_fail:
            verdict = JudgeVerdict(question=question, slm_responses=[], final_answer='[BLOCKED BY V98 SECURITY] Memory poisoning or critical threat detected.', confidence=0.0, verdict='FAIL', reasoning=f"V98 early block: guard={(v98_guard_verdict.recommendation if v98_guard_verdict else 'none')}, threat={(v98_classification.severity if v98_classification else 'none')}, attack_match={(v98_attack_match.get('matched', False) if v98_attack_match else False)}", evidence={'v98_guard': v98_guard_verdict.to_dict() if v98_guard_verdict else None, 'v98_threat': v98_threat_signal.to_dict() if v98_threat_signal else None, 'v98_classification': v98_classification.to_dict() if v98_classification else None, 'v98_attack_match': v98_attack_match, 'early_fail': True}, domain='security', timestamp=ts)
            return verdict
        if self.attack_predictor and v98_classification and (v98_classification.severity in ('medium', 'high', 'critical')):
            try:
                predictor_signals = {'request_rate_anomaly': min(1.0, getattr(v98_threat_signal, 'confidence', 0.5) if v98_threat_signal else 0.3), 'geo_distribution_anomaly': 0.4 if v98_threat_signal and v98_threat_signal.asn_intel and (not v98_threat_signal.asn_intel.get('is_residential', True)) else 0.2, 'user_agent_pattern_shift': 0.3, 'payload_pattern_emergence': 0.6 if v98_attack_match and v98_attack_match.get('matched') else 0.2, 'historical_attack_pattern_match': 0.5 if v98_attack_match else 0.1, 'time_of_day_pattern': 0.3, 'threat_intel_correlation': 0.7 if v98_classification.severity in ('high', 'critical') else 0.3, 'political_event_correlation': 0.1}
                forecast = self.attack_predictor.predict_cyber_attack(predictor_signals)
                _pre_verdict_evidence['v10452_attack_forecast'] = {'threat_type': forecast.threat_type, 'probability': forecast.probability, 'confidence': forecast.confidence, 'timeframe_min': forecast.timeframe_min, 'recommended_actions': forecast.recommended_actions, 'why': forecast.why_explanation[:200]}
                if forecast.confidence > 0.5 and forecast.probability > 0.5 and self.escalation_manager:
                    _threat = {'id': f'predict_{int(time.time())}', 'type': forecast.threat_type, 'severity': v98_classification.severity, 'prediction_confidence': forecast.confidence, 'description': forecast.why_explanation[:200]}
                    self.escalation_manager.on_threat_detected(_threat)
                    _pre_verdict_evidence['v10452_escalation_triggered'] = True
                    logger.warning(f'[V104.52] Predictive escalation: {forecast.threat_type} conf={forecast.confidence:.2f}')
            except Exception as e:
                logger.debug(f'[V104.52] Predictor error: {e}')
        _kb_sc_verdict = verdict_type
        _kb_sc_answer = final_answer
        _kb_sc_conf = confidence
        if _kb_sc_verdict == 'PASS' and _kb_sc_answer and (_kb_sc_conf >= 0.85) and v100_kb_hits:
            _best_hit = v100_kb_hits[0]
            _hit_tier = getattr(_best_hit, 'source_tier', 9)
            if _hit_tier <= 2:
                logger.info(f'[V104.46 #BI] KB short-circuit early return (post-security): tier={_hit_tier}')
                verdict = JudgeVerdict(question=question, final_answer=final_answer, confidence=confidence, verdict=verdict_type, domain='general', reasoning=reasoning, evidence={'v100_kb_short_circuit': True, 'source_tier': _hit_tier}, timestamp=ts)
                return verdict
        if self.error_store_index:
            try:
                _similar = None
                if hasattr(self.error_store_index, '_search_sync'):
                    _similar = self.error_store_index._search_sync(question, limit=3)
                else:
                    import asyncio as _a
                    try:
                        _loop = _a.get_event_loop()
                        if _loop.is_running():
                            import asyncio as _a2
                            _similar = _a2.run_coroutine_threadsafe(self.error_store_index.search_similar(question, top_k=3), _loop).result(timeout=2.0)
                        else:
                            _similar = _loop.run_until_complete(self.error_store_index.search_similar(question, top_k=3))
                    except Exception:
                        _similar = None
                if _similar:
                    _pre_verdict_evidence['v104_similar_errors'] = [{'question': (s.get('question', '') if isinstance(s, dict) else getattr(s, 'question', ''))[:100], 'verdict': s.get('verdict', '') if isinstance(s, dict) else getattr(s, 'verdict', '')} for s in _similar[:3]]
                    _fail_count = sum((1 for s in _similar if (s.get('verdict', '') if isinstance(s, dict) else getattr(s, 'verdict', '')) == 'FAIL'))
                    if _fail_count >= 2:
                        _es_index_threshold_boost = 0.1
                        logger.info(f'[V104.44 #BX] Similar errors: {_fail_count} FAILs → threshold boost +{_es_index_threshold_boost}')
            except Exception as e:
                logger.debug(f'[V104.44 #BX] ErrorStoreIndex search error: {e}')
        domains = self._route_question(question, domain_override=domain_override)
        applied_principle_ids: list[int] = []
        adjusted_threshold = self.confidence_threshold
        if domains:
            try:
                exp_pol = self._get_exp_policies()
                tolerances = exp_pol.get('domain_tolerances', {})
                primary_dom = domains[0]
                if primary_dom in tolerances:
                    adjusted_threshold = min(0.9, self.confidence_threshold * tolerances[primary_dom])
            except Exception as e:
                logger.debug(f'[V93.6] domain_tolerance apply error: {e}')
        if _enable_closed_loop and self.policy_applier and domains:
            try:
                primary_dom = domains[0]
                adjustment = self.policy_applier.get_adjustment(question, primary_dom, base_threshold=self.confidence_threshold)
                adjusted_threshold = adjustment['confidence_threshold']
                adjustment.get('prefer_sources', [])
                adjustment.get('avoid_sources', [])
                applied_principle_ids = adjustment.get('applied_principle_ids', [])
            except Exception as e:
                logger.debug(f'PolicyApplier error: {e}')
        if _es_index_threshold_boost > 0:
            adjusted_threshold = min(0.95, adjusted_threshold + _es_index_threshold_boost)
        prediction_skip_api = False
        prediction_verdict = None
        if _enable_closed_loop and self.predictor and domains:
            try:
                pred = self.predictor.predict(question, domains[0], ai_answer)
                prediction_verdict = pred.verdict
                if pred.skip_api and pred.confidence > 0.85:
                    prediction_skip_api = True
            except Exception as e:
                logger.debug(f'VerdictPredictor error: {e}')
        slm_responses = []

        def _call_slm(domain: str) -> dict:
            """Call 1 SLM, return response dict."""
            slm = self.slms.get(domain)
            if slm:
                try:
                    try:
                        if os.environ.get('SCP_WHY_PRE_ROUTE', '0') == '1' and why_plan:
                            slm.why_sources_hint = list(why_plan.sources_to_query)
                            logger.debug(f'[V5.7-WHY] pre-route hint set on {domain} SLM: {why_plan.sources_to_query}')
                        elif hasattr(slm, 'why_sources_hint'):
                            try:
                                del slm.why_sources_hint
                            except Exception as e:
                                logger.warning(f'Silent except: {e}')
                    except Exception as _hint_err:
                        logger.debug(f'[V5.7-WHY] pre-route hint set failed (non-fatal): {_hint_err}')
                    resp = slm.predict(question)
                    return {'domain': domain, 'answer': resp.answer, 'confidence': resp.confidence, 'reasoning': resp.reasoning, 'evidence': resp.evidence, 'slm_name': resp.slm_name, 'processing_time': resp.processing_time}
                except Exception as e:
                    return {'domain': domain, 'error': str(e), 'confidence': 0.0}
            else:
                try:
                    v13_result = self.v13.process(question, ai_answer)
                    real_value = v13_result.real_value
                    source = v13_result.source or 'v13'
                    if real_value is not None:
                        return {'domain': domain, 'answer': f'= {real_value}', 'confidence': 0.85, 'reasoning': f'V13 RealityEngine: {source}', 'evidence': {'source': source, 'value': real_value}, 'slm_name': 'V13Reality', 'processing_time': 0.0}
                except Exception as e:
                    logger.warning(f'[judge] V13Reality fallback failed: {e}')
                return {'domain': domain, 'error': 'no SLM', 'confidence': 0.0}
        if len(domains) == 1:
            primary_domain = domains[0]
            if primary_domain not in ('universal', 'general'):
                domains.append('universal')
            slm_responses.append(_call_slm(domains[0]))
            if len(domains) > 1:
                slm_responses.append(_call_slm(domains[1]))
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=min(4, len(domains))) as executor:
                future_to_domain = {executor.submit(_call_slm, d): d for d in domains}
                for future in as_completed(future_to_domain, timeout=30):
                    try:
                        result = future.result(timeout=15)
                        slm_responses.append(result)
                    except Exception as e:
                        domain = future_to_domain[future]
                        slm_responses.append({'domain': domain, 'error': str(e), 'confidence': 0.0})
        if not slm_responses:
            if self.llm_client:
                try:
                    import asyncio as _a
                    llm_context = ''
                    if v100_kb_hits:
                        llm_context = '\n'.join((f'- {h.answer[:200]}' for h in v100_kb_hits[:3]))
                    try:
                        import concurrent.futures as _cf
                        _llm_pool = _cf.ThreadPoolExecutor(max_workers=1)
                        llm_answer, llm_model = _llm_pool.submit(_a.run, self.llm_client.chat(question, context=llm_context, task='judge')).result(timeout=10)
                        _llm_pool.shutdown(wait=False)
                    except RuntimeError:
                        llm_answer, llm_model = _a.run(self.llm_client.chat(question, context=llm_context, task='judge'))
                    except Exception as e:
                        llm_answer, llm_model = ('', f'llm_error: {e}')
                    if llm_answer and 'không khả dụng' not in llm_answer:
                        return JudgeVerdict(question=question, slm_responses=[], final_answer=llm_answer[:2000], confidence=0.3, verdict='UNKNOWN', reasoning=f'SLM không có answer → LLM ({llm_model}) trả lời — chưa verify, confidence thấp', evidence={'scope': 'llm_fallback', 'llm_model': llm_model}, domain=domains[0] if domains else 'unknown', cross_validation={}, slm_scores={}, timestamp=ts)
                except Exception as e:
                    logger.debug(f' LLM fallback error: {e}')
            return JudgeVerdict(question=question, slm_responses=[], final_answer='[SCP] Tôi không có đủ thông tin để trả lời câu hỏi này. Không có SLM nào có dữ liệu liên quan đến lĩnh vực này.', confidence=0.0, verdict='UNKNOWN', reasoning='Không có SLM nào response — ngoài phạm vi kiến thức hiện có', evidence={'scope': 'out_of_scope'}, domain=domains[0] if domains else 'unknown', cross_validation={}, slm_scores={}, timestamp=ts)
        valid_responses = []
        for r in slm_responses:
            if 'error' in r or not r.get('answer'):
                continue
            ans = str(r['answer']).strip()
            r_domain = r.get('domain', '')
            if len(ans) <= 2 and r_domain not in ('math', 'conversion', 'reality'):
                logger.debug(f"Filtering garbage SLM answer: '{ans}' from {r_domain}")
                continue
            valid_responses.append(r)
        if not valid_responses:
            valid_responses = [r for r in slm_responses if 'error' not in r and r.get('answer')]
        is_consistent = self._check_consistency(valid_responses)
        if len(valid_responses) >= 2:
            try:
                from scp.core.conflict_resolver import resolve_value
                confidence = max((r.get('confidence', 0) for r in valid_responses), default=0)
                values_for_resolution = []
                _watchlist_for_vote = getattr(self, '_source_watchlist', None)
                _blocked_in_vote: list[str] = []
                for r in valid_responses:
                    val = r.get('evidence', {}).get('value')
                    if val is None:
                        continue
                    _src = r.get('evidence', {}).get('source', r.get('slm_name', '?'))
                    _ew: float = 1.0
                    if _watchlist_for_vote is not None and hasattr(_watchlist_for_vote, 'ingestion_decision'):
                        try:
                            _ing = _watchlist_for_vote.ingestion_decision(_src, tier=3)
                            _action = _ing.get('action', 'commit')
                            if _action == 'block':
                                _blocked_in_vote.append(_src)
                                continue
                            _ew = float(_ing.get('effective_weight', 1.0) or 1.0)
                        except Exception as e:
                            logger.debug(f'[judgecore_mixin.py:770] silenced: {e}')
                    values_for_resolution.append({'value': val, 'source': _src, 'effective_weight': _ew})
                if _blocked_in_vote:
                    logger.info(f' Skipped {len(_blocked_in_vote)} blocked source(s) in consensus voting: {_blocked_in_vote[:3]}')
                    verdict.evidence.setdefault('consensus_blocked_sources', _blocked_in_vote[:10])
                if len(values_for_resolution) >= 2:
                    conflict_result = resolve_value(values_for_resolution, strategy='weighted_avg')
                    try:
                        from scp.core.conflict_resolver import log_conflict as _log_conflict
                        _entity = valid_responses[0].get('evidence', {}).get('entity') or question[:60]
                        _log_conflict(_entity, 'value', values_for_resolution, conflict_result)
                    except Exception as _le:
                        logger.debug(f' log_conflict failed: {_le}')
                    if conflict_result.conflict_detected:
                        agreement = getattr(conflict_result, 'agreement_score', 0.5)
                        if agreement < 0.5:
                            confidence = max(0.2, confidence * agreement)
                            logger.info(f"[CONFLICT] Sources disagree (agreement={agreement:.2f}): {[(v['source'], v['value']) for v in values_for_resolution]}")
                        else:
                            resolved_val = getattr(conflict_result, 'final_value', None)
                            if resolved_val is not None:
                                for r in valid_responses:
                                    if r.get('evidence', {}).get('source') == conflict_result.source:
                                        r['answer'] = f'= {resolved_val}'
                                        r['evidence']['value'] = resolved_val
                                        break
                                confidence = confidence * (0.7 + 0.3 * agreement)
                    else:
                        confidence = min(0.97, confidence + 0.05)
                    try:
                        _rep_store = getattr(getattr(self, '_source_watchlist', None), 'store', None)
                        if _rep_store is not None and hasattr(_rep_store, 'get_reputation'):
                            _domain = domains[0] if domains else 'unknown'
                            _cold_start_count = 0
                            _mature_reps: list[float] = []
                            for _v in values_for_resolution:
                                _src = _v.get('source', '')
                                _outcomes = 0
                                if hasattr(_rep_store, 'get_outcome_count'):
                                    _outcomes = _rep_store.get_outcome_count(_src, _domain)
                                _threshold = getattr(_rep_store, 'COLD_START_THRESHOLD', 10)
                                if _outcomes < _threshold:
                                    _cold_start_count += 1
                                else:
                                    _rep = _rep_store.get_reputation(_src, _domain)
                                    if _rep is not None:
                                        _mature_reps.append(_rep)
                            if _mature_reps:
                                _worst_rep = min(_mature_reps)
                            else:
                                _worst_rep = 1.0
                            if _cold_start_count > 0:
                                verdict.evidence.setdefault('cold_start_sources', _cold_start_count)
                                logger.debug(f" {_cold_start_count}/{len(values_for_resolution)} sources in cold-start (<{getattr(_rep_store, 'COLD_START_THRESHOLD', 10)} outcomes) — skipped from worst-rep scaling")
                            if _worst_rep < 1.0:
                                confidence = max(0.1, confidence * (0.3 + 0.7 * _worst_rep))
                                if _worst_rep < 0.4:
                                    logger.info(f' Low-reputation source (rep={_worst_rep:.2f}) dragged confidence to {confidence:.2f}')
                    except Exception as _re:
                        logger.debug(f' reputation scaling failed: {_re}')
            except Exception as e:
                logger.debug(f'ConflictResolver error: {e}')
        slm_scores = {}
        for r in valid_responses:
            slm_scores[r.get('domain', 'unknown')] = {'score': r.get('confidence', 0), 'answer': r.get('answer', '')}
        if valid_responses:
            from difflib import SequenceMatcher
            _groups = []
            for r in valid_responses:
                _r_ans = (r.get('answer') or '').strip().lower()
                _matched = False
                for _g in _groups:
                    _g_ans = _g['answer']
                    if _r_ans and _g_ans:
                        _sim = SequenceMatcher(None, _r_ans, _g_ans).ratio()
                        if _sim >= 0.6:
                            _g['count'] += 1
                            _g['members'].append(r)
                            _matched = True
                            break
                if not _matched:
                    _groups.append({'answer': _r_ans, 'conf': r.get('confidence', 0), 'count': 1, 'members': [r]})
            _best_group = max(_groups, key=lambda g: g['count'] * sum((m.get('confidence', 0) for m in g['members'])) / max(len(g['members']), 1))
            if _best_group['count'] >= 2:
                primary = max(_best_group['members'], key=lambda x: x.get('confidence', 0))
                _consensus_boost = 0.05 * (_best_group['count'] - 1)
                confidence_boost = _consensus_boost
            else:
                primary = max(valid_responses, key=lambda x: x.get('confidence', 0))
                confidence_boost = 0
        else:
            primary = None
            confidence_boost = 0
        _routed_fallback_domain = domains[0] if domains else 'unknown'
        primary_domain = primary.get('domain', _routed_fallback_domain) if primary else _routed_fallback_domain
        final_answer = primary.get('answer', '') if primary else ''
        confidence = primary.get('confidence', 0) if primary else 0
        try:
            if 'confidence_boost' in dir() and confidence_boost:
                _all_strong = True
                if '_best_group' in dir() and _best_group:
                    for _member in _best_group.get('members', []):
                        if _member.get('confidence', 0) < 0.5:
                            _all_strong = False
                            break
                if _all_strong:
                    confidence = min(0.95, confidence + confidence_boost)
                else:
                    logger.debug('[AUDIT-3] consensus boost skipped — some SLMs < 0.5 conf')
        except Exception as e:
            logger.warning(f'Silent except: {e}')
        if self.calibration and primary_domain:
            try:
                confidence = self.calibration.apply_calibration(confidence, primary_domain)
                if os.environ.get('SCP_DEBUG_CONF'):
                    import sys as _sys
                    print(f'  [DBG] After calibration: {confidence} (factor applied)', file=_sys.stderr)
            except Exception as e:
                logger.debug(f'Calibration apply error: {e}')
        if primary_domain:
            try:
                exp_pol = self._get_exp_policies()
                conf_adj = exp_pol.get('confidence_adjustments', {})
                if primary_domain in conf_adj:
                    confidence = confidence * conf_adj[primary_domain]
            except Exception as e:
                logger.debug(f'[V93.6] confidence_adjustment apply error: {e}')
        DETERMINISTIC_SLMS = ('MathSLM', 'ConversionSLM', 'StatisticsSLM', 'LogicSLM')
        if primary and confidence >= 0.95:
            _slm_name = str(primary.get('slm_name', '') or primary.get('source', '') or '')
            if any((_d in _slm_name for _d in DETERMINISTIC_SLMS)):
                _reality_ok = True
                _reality_msg = 'skipped (no checker implemented)'
                try:
                    _reality_ok, _reality_msg = self._reality_check_deterministic(_slm_name, question, final_answer, primary)
                except Exception as _rc_err:
                    logger.warning(f"[P0-2] reality_check_deterministic crashed for '{_slm_name}': {_rc_err}")
                    _reality_ok = False
                    _reality_msg = f'checker crashed: {_rc_err}'
                if _reality_ok:
                    logger.info(f"[ROOT-FIX 43-A R16] Deterministic SLM '{_slm_name}' (conf={confidence:.2f}) PASSED reality check: {_reality_msg}")
                    return JudgeVerdict(question=question, slm_responses=slm_responses, final_answer=final_answer, confidence=confidence, verdict='PASS', reasoning=f'Deterministic SLM ({_slm_name}) conf={confidence:.2f} + reality check PASSED: {_reality_msg} (DNA SCP #1: Reality > Model — verified, not just claimed)', evidence={'primary_domain': primary_domain, 'deterministic_slm': True, 'slm_name': _slm_name, 'skip_why_verification': True, 'root_fix': '43-A/Fix1 + R16/P0-2 (reality check added)', 'reality_check_passed': True, 'reality_check_msg': _reality_msg}, domain=primary_domain, cross_validation={'answers': [r.get('answer', '') for r in valid_responses], 'consistency_score': self._consistency_score(valid_responses)}, slm_scores=slm_scores, reality_check={'is_correct': True, 'reason': f'Deterministic SLM ({_slm_name}) + reality check passed: {_reality_msg}', 'source': _slm_name, 'verified_by': 'r16_reality_check'}, timestamp=ts, similar_errors=[])
                else:
                    logger.warning(f"[P0-2 R16] Deterministic SLM '{_slm_name}' claimed conf={confidence:.2f} but reality check FAILED: {_reality_msg} — downgrading to UNKNOWN")
                    confidence = min(confidence, 0.4)
        adversary_result = None
        if self.adversary and primary and (not prediction_skip_api):
            try:
                primary_value = primary.get('evidence', {}).get('value')
                primary_source = primary.get('evidence', {}).get('source', '')
                entity = primary.get('evidence', {}).get('entity', '')
                if primary_value is not None and primary_source:
                    adv = self.adversary.verify(primary_value, primary_source, primary_domain, question, entity or '')
                    if adv.adversary_values:
                        adversary_result = adv
                        if adv.conflict_detected and adv.agreement_score < 0.85:
                            confidence = max(0.3, confidence - 0.2)
                            _adversary_conflict = True
                            _adversary_conflict_reason = f'. Adversary conflict: agreement={adv.agreement_score:.2f} (source says different value)'
                        elif adv.agreement_score >= 0.85:
                            confidence = min(0.95, confidence + 0.05)
                    else:
                        if os.environ.get('SCP_DEBUG_CONF'):
                            import sys as _sys
                            print(f'  [DBG] Adversary no_values, final_conf={adv.final_confidence}', file=_sys.stderr)
                        if adv.final_confidence > confidence:
                            confidence = adv.final_confidence
            except Exception as e:
                logger.debug(f'Adversary verify error: {e}')
        reality_check = {'is_correct': None, 'reason': 'Not yet checked'}
        effective_threshold = adjusted_threshold
        if is_consistent and confidence > effective_threshold:
            slm_answer = final_answer
            if ai_answer and slm_answer:
                ai_extracted = self._extract_value(question, ai_answer)
                slm_extracted = self._extract_value(question, slm_answer)
                if ai_extracted and slm_extracted:
                    if ai_extracted.lower() == slm_extracted.lower():
                        verdict_type = 'PASS'
                        reasoning = f"Value match: '{ai_extracted[:50]}' == '{slm_extracted[:50]}'"
                    elif ai_extracted.lower() in slm_extracted.lower() or slm_extracted.lower() in ai_extracted.lower():
                        verdict_type = 'PASS'
                        reasoning = f"Value substring match: '{ai_extracted[:50]}' ⊆ '{slm_extracted[:50]}'"
                    else:
                        verdict_type = None
                else:
                    verdict_type = None
                if verdict_type is None:
                    import re
                    slm_result_part = slm_answer
                    ai_result_part = ai_answer
                    if '=' in slm_answer:
                        slm_result_part = slm_answer.split('=')[-1].strip()
                    if '=' in ai_answer:
                        ai_result_part = ai_answer.split('=')[-1].strip()
                    num_pattern = '-?\\d+\\.?\\d*(?:[eE][+-]?\\d+)?'
                    slm_nums = re.findall(num_pattern, slm_result_part)
                    ai_nums = re.findall(num_pattern, ai_result_part)
                    if slm_nums and ai_nums:
                        ai_val = float(ai_nums[0])
                        best_slm_val = None
                        best_diff = float('inf')
                        for sn in slm_nums:
                            try:
                                sv = float(sn)
                                diff = abs(sv - ai_val)
                                if diff < best_diff:
                                    best_diff = diff
                                    best_slm_val = sv
                            except ValueError:
                                continue
                        if best_slm_val is None:
                            best_slm_val = float(slm_nums[0])
                        slm_val = best_slm_val
                        abs_diff = abs(slm_val - ai_val)
                        abs_max = max(abs(slm_val), abs(ai_val))
                        rel_diff = abs_diff / max(abs_max, 1e-300)
                        if abs_max >= 1:
                            tolerance = abs_max * 0.005
                        elif abs_max >= 0.01:
                            tolerance = abs_max * 0.01
                        else:
                            tolerance = abs_max * 0.02
                        is_sci = abs_max > 1000000.0 or (abs_max > 0 and abs_max < 0.001)
                        if is_sci:
                            if rel_diff > 0.01:
                                verdict_type = 'FAIL'
                                reasoning = f'SLM tính {slm_val:.6g}, AI nói {ai_val:.6g} (chênh {rel_diff * 100:.2f}%)'
                            else:
                                verdict_type = 'PASS'
                                reasoning = 'Các SLM đồng thuận, đạt ngưỡng tin cậy'
                        elif abs_diff > tolerance and rel_diff > 0.005:
                            verdict_type = 'FAIL'
                            reasoning = f'SLM tính {slm_val}, AI nói {ai_val} (chênh {abs_diff:.4f})'
                        else:
                            verdict_type = 'PASS'
                            reasoning = 'Các SLM đồng thuận, đạt ngưỡng tin cậy'
                    else:
                        slm_str = slm_answer.strip().lower().rstrip('.?!,;:').replace('.', '')
                        ai_str = ai_answer.strip().lower().rstrip('.?!,;:').replace('.', '')
                        answer_prefixes = ['^thủ đô của \\w+ là\\s+', '^capital of \\w+ is\\s+', '^=\\s*']
                        for pat in answer_prefixes:
                            slm_str = re.sub(pat, '', slm_str).strip()
                            ai_str = re.sub(pat, '', ai_str).strip()
                        ai_value = self._extract_value(question, ai_str)
                        slm_value = self._extract_value(question, slm_str)
                        if ai_value and slm_value:
                            ai_compare = ai_value
                            slm_compare = slm_value
                        else:
                            ai_compare = ai_str
                            slm_compare = slm_str
                        if ai_value and slm_value and (ai_value.lower() == slm_value.lower()):
                            verdict_type = 'PASS'
                            reasoning = f"Value match: '{ai_value}' == '{slm_value}'"
                        elif not ai_compare or not slm_compare:
                            verdict_type = 'FAIL'
                            reasoning = 'Empty answer from SLM or AI'
                        elif ai_str in slm_str or slm_str in ai_str:
                            match_len = min(len(ai_str), len(slm_str))
                            if match_len >= 3:
                                verdict_type = 'PASS'
                                reasoning = 'Các SLM đồng thuận (string match), đạt ngưỡng tin cậy'
                            else:
                                verdict_type = 'FAIL'
                                reasoning = f"String match too short: '{ai_str}' vs '{slm_str}'"
                        else:
                            stopwords = [' ra ', ' của ', ' là ', ' và ', ' được ', ' tại ', ' ở ', ' bằng ', ' có ', ' cho ', ' từ ', ' vào ', ' lên ', ' xuống ']
                            slm_clean = slm_str
                            ai_clean = ai_str
                            for sw in stopwords:
                                slm_clean = slm_clean.replace(sw, ' ')
                                ai_clean = ai_clean.replace(sw, ' ')
                            slm_clean = ' '.join(slm_clean.split())
                            ai_clean = ' '.join(ai_clean.split())
                            if ai_clean in slm_clean or slm_clean in ai_clean:
                                match_len = min(len(ai_clean), len(slm_clean))
                                if match_len >= 3:
                                    verdict_type = 'PASS'
                                    reasoning = 'Các SLM đồng thuận (fuzzy string match), đạt ngưỡng tin cậy'
                                else:
                                    verdict_type = 'FAIL'
                                    reasoning = f"Fuzzy match too short: '{ai_clean}' vs '{slm_clean}'"
                            else:
                                ai_words = set(ai_clean.split())
                                slm_words = set(slm_clean.split())
                                if ai_words and slm_words:
                                    overlap = len(ai_words & slm_words) / len(ai_words)
                                    if overlap >= 0.6:
                                        verdict_type = 'PASS'
                                        reasoning = f'Các SLM đồng thuận (word overlap {overlap * 100:.0f}%), đạt ngưỡng tin cậy'
                                    else:
                                        verdict_type = 'FAIL'
                                        reasoning = f"SLM says '{slm_str[:30]}', AI says '{ai_str[:30]}' (overlap {overlap * 100:.0f}%)"
                                else:
                                    verdict_type = 'FAIL'
                                    reasoning = f"SLM says '{slm_str[:30]}', AI says '{ai_str[:30]}' (string mismatch)"
            elif not ai_answer:
                if confidence >= 0.65 and final_answer:
                    verdict_type = 'UNKNOWN'
                    reasoning = f'SLM self-answered (conf={confidence:.2f}) but no external source — cannot verify (Evidence-First)'
                else:
                    verdict_type = 'UNKNOWN'
                    reasoning = 'No AI answer to verify'
            elif not final_answer:
                verdict_type = 'UNKNOWN'
                reasoning = 'SLM has no answer'
            else:
                verdict_type = 'PASS'
                reasoning = 'Các SLM đồng thuận, đạt ngưỡng tin cậy'
        elif is_consistent:
            if confidence < 0.05:
                verdict_type = 'UNKNOWN'
                reasoning = 'SLM returned no useful answer (confidence ~0)'
                if not final_answer:
                    final_answer = '[SCP] Tôi không có đủ dữ liệu để trả lời câu hỏi này. Đây là ngoài phạm vi kiến thức hiện tại của tôi.'
                _speculative_keywords = ['hãy tạo ra', 'hãy xây dựng', 'hãy đề xuất', 'hãy tưởng tượng', 'ý tưởng mới', 'hoàn toàn mới', 'đột phá', 'giả định', 'mô hình', 'học thuyết', 'dự đoán', 'suy đoán', 'create', 'imagine', 'propose', 'hypothetical', 'nếu', 'what if', 'giả sử']
                _is_speculative = any((kw in question.lower() for kw in _speculative_keywords))
                _is_attack = v98_guard_verdict and v98_guard_verdict.is_poisoned
                if _is_speculative and (not _is_attack):
                    verdict_type = 'SPECULATIVE'
                    reasoning = 'Phase 9.5 Speculative Mode: Câu hỏi mang tính sáng tạo/giả định, không phải tấn công. SCP không có ground truth để verify, nhưng không kìm hãm sáng tạo — trả về với cảnh báo.'
                    _spec_assumptions = []
                    if 'đạo đức' in question.lower() or 'ethic' in question.lower():
                        _spec_assumptions = ['Giả định 1: Các nguyên tắc đạo đức cơ bản (không giết người, trung thực, công bằng) là phổ quát', 'Giả định 2: Hệ thống AI có khả năng đánh giá hậu quả trong thời gian thực', "Giả định 3: Có thể lượng hóa được 'lợi ích' và 'nghĩa vụ' trên cùng một thang đo", 'Giả định 4: Quyết định đạo đức có thể được biểu diễn dưới dạng thuật toán']
                    elif 'lịch sử' in question.lower() or 'khảo cổ' in question.lower() or 'văn minh' in question.lower():
                        _spec_assumptions = ['Giả định 1: Các dữ liệu khảo cổ hiện tại phản ánh đúng thực tế lịch sử', 'Giả định 2: Sự sụp đổ của nền văn minh có thể được giải thích bằng một nguyên nhân chính', 'Giả định 3: Hệ thống chữ viết chưa giải mã có cấu trúc nhất quán có thể suy luận', 'Giả định 4: Các mô hình xã hội học hiện đại có thể áp dụng cho xã hội cổ đại']
                    elif 'khoa học' in question.lower() or 'vật lý' in question.lower() or 'vũ trụ' in question.lower():
                        _spec_assumptions = ['Giả định 1: Các định luật vật lý hiện tại (nhiệt động, lượng tử, tương đối) là đúng', 'Giả định 2: Ý tưởng mới không mâu thuẫn với dữ liệu thực nghiệm đã biết', 'Giả định 3: Có thể kiểm tra ý tưởng bằng thí nghiệm trong tương lai', 'Giả định 4: Toán học là ngôn ngữ phù hợp để mô tả vũ trụ']
                    else:
                        _spec_assumptions = [f"Giả định 1: Câu hỏi '{question[:60]}...' có thể được suy luận từ kiến thức hiện có", 'Giả định 2: Các giả định logic có thể được xây dựng từ các nguyên lý đã biết', 'Giả định 3: Kết quả suy đoán có thể được kiểm chứng trong tương lai']
                    _spec_response = '[SPECULATIVE - ZERO EVIDENCE]\n⚠️ CẢNH BÁO: Phản hồi dưới đây là SUY ĐOÁN, không có bằng chứng thực nghiệm.\nSCP không có ground truth để verify. Không nên sử dụng làm cơ sở quyết định quan trọng.\n\nCâu hỏi của bạn yêu cầu sáng tạo/giả định — ngoài phạm vi verify của SCP.\n\nCác giả định logic được đưa ra:\n'
                    for i, assumption in enumerate(_spec_assumptions, 1):
                        _spec_response += f'  {i}. {assumption}\n'
                    _spec_response += '\nNếu các giả định trên đúng, thì một hướng tiếp cận có thể là:\n  → Phân tích câu hỏi từ góc nhìn multi-disciplinary\n  → Xây dựng framework logic dựa trên các giả định\n  → Kiểm tra tính nhất quán nội bộ\n  → Đề xuất phương pháp kiểm chứng trong tương lai\n\n⚠️ SCP KHÔNG xác nhận tính đúng đắn của bất kỳ phần nào trong phản hồi này.\nĐây là Speculative Mode — con người quyết định.'
                    final_answer = _spec_response
                    confidence = 0.0
                    verdict_evidence_spec = {'speculative_mode': True, 'assumptions': _spec_assumptions, 'warning': 'ZERO EVIDENCE — suy đoán không có ground truth', 'human_decision_required': True}
            else:
                num_slm_answers = len([r for r in valid_responses if r.get('answer')])
                has_reality_check = bool(reality_check and reality_check.get('real_value') is not None)
                if num_slm_answers < 2 and (not has_reality_check) and (confidence < 0.6):
                    verdict_type = 'UNKNOWN'
                    reasoning = f'Không đủ bằng chứng (chỉ {num_slm_answers} nguồn, conf={confidence:.2f})'
                else:
                    verdict_type = 'PARTIAL'
                    reasoning = f'Các SLM đồng thuận nhưng độ tin cậy thấp ({num_slm_answers} nguồn, conf={confidence:.2f})'
        else:
            ai_lower = (ai_answer or '').strip().lower()
            matched_slm = None
            if ai_lower:
                for r in valid_responses:
                    slm_ans = (r.get('answer') or '').strip().lower()
                    if ai_lower in slm_ans or slm_ans in ai_lower:
                        matched_slm = r
                        break
                    ai_words = set(ai_lower.split())
                    slm_words = set(slm_ans.split())
                    if ai_words and slm_words:
                        overlap = len(ai_words & slm_words) / max(len(ai_words), 1)
                        if overlap >= 0.6:
                            matched_slm = r
                            break
            if matched_slm is None:
                try:
                    import re as _answer_match_re
                    _math_like = bool(_answer_match_re.search('(?i)(?:calculate|compute|arithmetic|tinh|tinh toan|phep tinh)|[-+*/]\\s*\\d|\\d\\s*[-+*/=]\\s*\\d', str(question or '')))
                    if _math_like and (ai_answer or final_answer):

                        def _nums(_text):
                            return _answer_match_re.findall('(?<![A-Za-z_])[-+]?\\d+(?:[.,]\\d+)?', str(_text or ''))
                        _comparison_answer = ai_answer or final_answer
                        _ai_nums = _nums(_comparison_answer)
                        _ai_last = _ai_nums[-1].replace(',', '.') if _ai_nums else None
                        if _ai_last is not None:
                            from decimal import Decimal as _AnswerDecimal
                            for _candidate in valid_responses:
                                _candidate_nums = _nums(_candidate.get('answer', ''))
                                if not _candidate_nums:
                                    continue
                                _candidate_last = _candidate_nums[-1].replace(',', '.')
                                if _AnswerDecimal(_ai_last) == _AnswerDecimal(_candidate_last):
                                    matched_slm = _candidate
                                    break
                except (ValueError, TypeError, ArithmeticError):
                    matched_slm = None
            if matched_slm:
                _primary_slm = max(valid_responses, key=lambda r: r.get('confidence', 0)) if valid_responses else None
                _is_primary = matched_slm == _primary_slm
                if _is_primary:
                    verdict_type = 'PASS'
                    confidence = matched_slm.get('confidence', confidence)
                    reasoning = f"Các SLM có mâu thuẫn nhưng AI match PRIMARY SLM[{matched_slm.get('domain', '?')}]"
                else:
                    verdict_type = 'CONFLICT'
                    confidence = min(confidence, matched_slm.get('confidence', 0.5))
                    reasoning = f"Các SLM mâu thuẫn, AI match non-primary SLM[{matched_slm.get('domain', '?')}] (not enough for PASS)"
            else:
                verdict_type = 'CONFLICT'
                reasoning = 'Các SLM có mâu thuẫn và AI không match bất kỳ SLM nào'
            final_answer = primary.get('answer', '') if primary else ''
        _best_slm_answer = ''
        if valid_responses:
            _best = max(valid_responses, key=lambda r: r.get('confidence', 0))
            _best_slm_answer = _best.get('answer', '')
        if not ai_answer and _best_slm_answer and (confidence >= 0.65):
            reality_check = {'is_correct': None, 'real_value': None, 'reason': 'SLM self-answered but no external source — cannot verify (Evidence-First)', 'source': 'slm_self_unverified'}
        else:
            reality_check = {'is_correct': None, 'reason': 'No AI answer to verify'}
        slm_has_real_value = any((r.get('evidence', {}).get('value') is not None for r in valid_responses))
        if ai_answer and (not slm_has_real_value):
            v13_result = self.v13.process(question, ai_answer)
            reality_check = {'is_correct': v13_result.final_verdict == 'PASS', 'verdict': v13_result.final_verdict, 'reason': v13_result.final_reason[:200], 'real_value': v13_result.real_value, 'source': v13_result.source, 'verdict_detail': v13_result.verdict_detail}
            if v13_result.final_verdict == 'FAIL':
                verdict_type = 'FAIL'
                reasoning += f'. Reality check: {v13_result.final_reason[:100]}'
            if v13_result.final_verdict == 'UNKNOWN' and ai_answer:
                try:
                    if hasattr(self.v13, 'direct_verifier') and self.v13.direct_verifier:
                        direct_result = self.v13.direct_verifier.verify(question, ai_answer, primary_domain)
                        if direct_result['verdict'] != 'UNKNOWN':
                            reality_check = {'is_correct': direct_result['verdict'] == 'PASS', 'verdict': direct_result['verdict'], 'reason': direct_result['reason'][:200], 'real_value': direct_result['real_value'], 'source': direct_result['source'], 'verdict_detail': ''}
                            if direct_result['verdict'] == 'FAIL':
                                verdict_type = 'FAIL'
                                reasoning += f". Direct verify: {direct_result['reason'][:100]}"
                            elif direct_result['verdict'] == 'PASS':
                                if verdict_type in ('UNKNOWN', 'PARTIAL'):
                                    verdict_type = 'PASS'
                                    reasoning += f". Direct verify PASS: {direct_result['reason'][:100]}"
                except Exception as e:
                    logger.warning(f'Direct verify failed: {e}')
        elif slm_has_real_value:
            best_resp = max(valid_responses, key=lambda x: x.get('confidence', 0))
            real_val = best_resp.get('evidence', {}).get('value')
            src = best_resp.get('evidence', {}).get('source', 'slm')
            reality_check = {'is_correct': None, 'verdict': 'PASS' if verdict_type == 'PASS' else 'FAIL', 'reason': f"SLM {best_resp.get('slm_name', '?')} provided value", 'real_value': real_val, 'source': src, 'verdict_detail': ''}
        similar_errors = []
        if _adversary_conflict and verdict_type == 'PASS':
            verdict_type = 'CONFLICT'
            reasoning += _adversary_conflict_reason
        if confidence is not None:
            confidence = max(0.0, min(1.0, confidence))
        try:
            if verdict_type == 'UNKNOWN' and self.llm_client is not None and ai_answer:
                from scp.ai_patterns import TreeOfThoughts
                tot_result = TreeOfThoughts.explore_paths(self.llm_client, question, ai_answer)
                if tot_result.get('verdict') == 'CORRECT':
                    verdict_type = 'PASS'
                    confidence = max(confidence, tot_result.get('confidence', 0.5))
                    reasoning += f". ToT upgrade UNKNOWN→PASS (agreement={tot_result.get('agreement', 0):.2f}, branches={tot_result.get('branches_used', 0)})"
                    logger.info(f"[ToT] upgrade UNKNOWN→PASS for q='{question[:60]}' (branches={tot_result.get('branches_used')}, agreement={tot_result.get('agreement'):.2f})")
        except Exception as e:
            logger.debug(f'ToT explore failed: {e}')
        _math_verdict = None
        try:
            from scp.core.math_evaluator import verify_math as _verify_math
            _math_verdict, _math_value, _math_reason = _verify_math(question or '', ai_answer or final_answer or '')
            if _math_verdict == 'PASS':
                verdict_type = 'PASS'
                confidence = max(confidence, 0.99)
                reasoning = f'Deterministic math verify PASS: {_math_reason}'
            elif _math_verdict == 'FAIL':
                verdict_type = 'FAIL'
                confidence = max(confidence, 0.99)
                reasoning = f'Deterministic math verify FAIL: {_math_reason}'
        except Exception as _math_err:
            logger.debug(f'Deterministic math verification unavailable: {_math_err}')
        verdict = JudgeVerdict(question=question, slm_responses=slm_responses, final_answer=final_answer, confidence=confidence, verdict=verdict_type, reasoning=reasoning, evidence={'primary_domain': primary_domain, 'consistency': is_consistent, 'slm_count': len(slm_responses), 'valid_slm_count': len(valid_responses), **_pre_verdict_evidence, **({'speculative_mode': verdict_evidence_spec} if verdict_evidence_spec is not None and verdict_type == 'SPECULATIVE' else {})}, domain=primary_domain, cross_validation={'answers': [r.get('answer', '') for r in valid_responses], 'consistency_score': self._consistency_score(valid_responses)}, slm_scores=slm_scores, reality_check=reality_check, timestamp=ts, similar_errors=similar_errors)
        try:
            from scp.meta.why_gate import get_why_gate
            _why_gate = get_why_gate()
            if verdict.verdict == 'PASS':
                _why_result = _why_gate.gate(action_type='verdict', action_desc=f'Verdict PASS for question: {question[:100]}', context=f'confidence={confidence}, sources={len(slm_responses)}, reasoning={reasoning[:200]}', constitution_kill=False)
                verdict.evidence['why_gate'] = _why_result.to_dict()
                if _why_result.blocked:
                    logger.info(f'[V9.0-WHY-GATE] PASS blocked by WHY: {_why_result.falsification_reason[:100]}')
                    verdict.verdict = 'UNKNOWN'
                    verdict.reasoning += f' | [WHY-GATE BLOCKED] {_why_result.falsification_reason[:100]}'
                    verdict.confidence = min(verdict.confidence, 0.4)
                elif _why_result.decision.name == 'UPHOLD':
                    verdict.reasoning += f' | [WHY-GATE UPHOLD] {_why_result.necessity_reason[:80]}'
        except Exception as _why_err:
            logger.debug(f'[V9.0-WHY-GATE] WHY Gate error (non-blocking): {_why_err}')
        if _enable_closed_loop and self.policy_applier and applied_principle_ids:
            try:
                self.policy_applier.record_outcome(applied_principle_ids, verdict.verdict)
            except Exception as e:
                logger.debug(f'PolicyApplier record_outcome error: {e}')
        if adversary_result:
            verdict.evidence['adversary'] = {'primary_value': adversary_result.primary_value, 'adversary_values': adversary_result.adversary_values, 'final_value': adversary_result.final_value, 'agreement_score': adversary_result.agreement_score, 'conflict_detected': adversary_result.conflict_detected, 'strategy': adversary_result.strategy}
        if prediction_verdict:
            verdict.evidence['prediction'] = {'predicted_verdict': prediction_verdict, 'skipped_api': prediction_skip_api}
        self._run_multi_llm_check(verdict, question, ai_answer)
        self._apply_why_confidence_adjust(verdict, why_plan, why_result)
        confidence = self._attach_why_to_verdict(verdict, why_plan, why_result, confidence, question, ai_answer, primary_domain)
        with self._verdict_history_lock:
            self.verdict_history.append(verdict)
            if len(self.verdict_history) > 100:
                self.verdict_history = self.verdict_history[-100:]
        self._run_cognitive_engine(verdict, why_plan, question, primary_domain, confidence, primary, slm_responses, reality_check)
        confidence = self._apply_cognitive_gate(verdict, why_plan, confidence, question, primary_domain, slm_responses)
        if self.predictor and verdict.verdict == 'PASS' and (primary_domain in ('weather', 'finance', 'conversion')) and (confidence > 0.5):
            try:
                from datetime import datetime as _dt
                from datetime import timedelta as _td
                check_date = (_dt.now() + _td(hours=1)).strftime('%Y-%m-%d %H:%M')
                real_value = verdict.reality_check.get('real_value')
                source = verdict.reality_check.get('source', '')
                pred_id = self.predictor.save_prediction(question=question, ai_answer=ai_answer, domain=primary_domain, check_date=check_date, source=source, entity=question[:50], current_value=real_value, confidence=confidence)
                verdict.evidence['prediction_saved'] = {'pred_id': pred_id, 'check_date': check_date, 'saved_value': str(real_value) if real_value is not None else None}
            except Exception as e:
                logger.debug(f'Predictive save error: {e}')
        if self.calibration:
            try:
                self.calibration.log_verdict(domain=primary_domain, slm_name=primary.get('slm_name', '') if primary else '', confidence=confidence, actual_verdict=verdict.verdict, question=question[:200], cycle_id=cycle_count)
                if cycle_count > 0 and cycle_count % 50 == 0:
                    try:
                        self.calibration.recompute_factors(min_samples=10)
                    except Exception as e:
                        logger.debug(f'Calibration recompute error: {e}')
            except Exception as e:
                logger.debug(f'Calibration log error: {e}')
        try:
            from scp.meta.question_tracker import get_question_tracker
            tracker = get_question_tracker()
            if not source:
                src = 'generator' if cycle_count > 0 else 'external'
            else:
                src = source
            _duration_ms = (time.perf_counter() - _judge_start_perf) * 1000.0
            try:
                _slm_count = len(valid_responses)
            except NameError:
                _slm_count = None
            tracker.log(question=question, source=src, domain=primary_domain, verdict=verdict.verdict, confidence=confidence, cycle_id=cycle_count, duration_ms=round(_duration_ms, 1), slm_count=_slm_count)
        except Exception as e:
            logger.debug(f'QuestionTracker log error: {e}')
        if verdict.verdict == 'PASS' and confidence > 0.5:
            if question.lower().startswith('kiểm tra lại:'):
                pass
            elif ai_answer and ai_answer.strip().isdigit() and (len(ai_answer.strip()) <= 4):
                pass
            else:
                try:
                    real_val = verdict.reality_check.get('real_value') if verdict.reality_check else None
                    source = verdict.reality_check.get('source', '') if verdict.reality_check else ''
                    if real_val is None and verdict.slm_responses:
                        for r in verdict.slm_responses:
                            ev = r.get('evidence', {})
                            if ev.get('value') is not None:
                                real_val = ev['value']
                                source = ev.get('source', r.get('slm_name', 'SLM'))
                                break
                    if real_val is None and ai_answer:
                        real_val = ai_answer[:200]
                        source = source or 'verified_ai_answer'
                    if real_val is not None and source:
                        import re as _re86
                        entity = None
                        m = _re86.match('tell\\s+me\\s+about\\s+(?:the\\s+(?:tv\\s+show|movie|book|star\\s+wars\\s+\\w+)\\s*[:\\-]?\\s*)?(.+?)\\.?\\s*$', question, _re86.I)
                        if m:
                            entity = m.group(1).strip().lower()
                        if not entity:
                            m = _re86.match('what\\s+does\\s+the\\s+bible\\s+say\\s+in\\s+(.+?)\\??$', question, _re86.I)
                            if m:
                                entity = f'bible:{m.group(1).strip().lower()}'
                        if not entity:
                            m = _re86.match('what\\s+is\\s+the\\s+recipe\\s+for\\s+(.+?)\\??$', question, _re86.I)
                            if m:
                                entity = m.group(1).strip().lower()
                        if not entity:
                            m = _re86.match('how\\s+do\\s+you\\s+make\\s+the\\s+cocktail\\s+(.+?)\\??$', question, _re86.I)
                            if m:
                                entity = f'cocktail:{m.group(1).strip().lower()}'
                        if not entity:
                            m = _re86.match('what\\s+is\\s+a\\s+public\\s+holiday\\s+in\\s+(\\w+)\\??$', question, _re86.I)
                            if m:
                                entity = f'holiday:{m.group(1).strip().lower()}'
                        if not entity:
                            m = _re86.match('what\\s+is\\s+the\\s+nutritional\\s+value\\s+of\\s+(.+?)\\??$', question, _re86.I)
                            if m:
                                entity = f'nutrition:{m.group(1).strip().lower()}'
                        if not entity:
                            m = _re86.match('what\\s+type\\s+of\\s+thing\\s+is\\s+(.+?)\\??$', question, _re86.I)
                            if m:
                                entity = m.group(1).strip().lower()
                        if not entity:
                            m = _re86.match('when\\s+was\\s+(.+?)\\s+born\\??$', question, _re86.I)
                            if m:
                                entity = f'person:{m.group(1).strip().lower()}'
                        if not entity:
                            pass
                        else:
                            try:
                                _watchlist = self._source_watchlist
                                try:
                                    if _watchlist is not None and hasattr(_watchlist, 'ingestion_decision'):
                                        _ing = _watchlist.ingestion_decision(source, tier=3)
                                        _action = _ing.get('action', '?')
                                        if _action != 'commit':
                                            logger.info(f" Ingestion decision for source={source}: action={_action} weight={_ing.get('effective_weight')} require_verification={_ing.get('require_verification')} reason={_ing.get('reason', '')[:80]}")
                                        verdict.evidence.setdefault('ingestion_decisions', []).append({'source': source, 'action': _action, 'effective_weight': _ing.get('effective_weight'), 'require_verification': _ing.get('require_verification')})
                                except Exception as _ie:
                                    logger.debug(f' ingestion_decision logging failed: {_ie}')
                                if _watchlist and _watchlist.is_blocked(source):
                                    logger.warning(f'[V104.42 #AH] Knowledge write blocked by watchlist: source={source}')
                                    pass
                                else:
                                    raise _AllowedByWatchlist()
                            except _AllowedByWatchlist as e:
                                logger.warning(f'Silent except: {e}')
                            except Exception as _wl_err:
                                logger.debug(f'[V104.42 #AH] Watchlist check error: {_wl_err}')
                                pass
                            try:
                                try:
                                    db_exec('INSERT INTO knowledge (entity, attribute, value, value_type, confidence, source, timestamp, times_verified) VALUES (?, ?, ?, ?, ?, ?, ?, 1)', (entity, 'verified_value', str(real_val)[:500], 'float' if isinstance(real_val, (int, float)) else 'str', confidence, source, datetime.now().isoformat()))
                                except Exception:
                                    db_exec('UPDATE knowledge SET value = ?, confidence = ?, source = ?, timestamp = ?, times_verified = times_verified + 1 WHERE entity = ? AND attribute = ?', (str(real_val)[:500], confidence, source, datetime.now().isoformat(), entity, 'verified_value'))
                            except Exception as e:
                                logger.debug(f'Knowledge save error: {e}')
                except Exception as e:
                    logger.warning(f'[judge] knowledge save outer block failed: {e}')
        if self.experience is not None and question and (len(question.strip()) > 0):
            try:
                real_val = verdict.reality_check.get('real_value') if verdict.reality_check else None
                lesson = {'question': question, 'ai_answer': ai_answer, 'real_value': str(real_val) if real_val is not None else None, 'error_type': primary_domain or 'unknown', 'cause': (verdict.reasoning or '')[:200], 'timestamp': datetime.now().isoformat(), 'lesson_type': f'VERDICT_{verdict.verdict}', 'policy_action': f'verdict_{verdict.verdict.lower()}', 'policy_target': primary_domain or 'unknown', 'policy_value': confidence, 'lesson_description': f'{verdict.verdict}: {question[:100]}', 'entity': primary_domain or 'unknown', 'domain': primary_domain or 'unknown', 'source': 'reality_judge', 'verdict': verdict.verdict}
                self.experience.learn([lesson])
            except Exception as e:
                logger.debug(f'ExperienceEngine learn error: {e}')
        self._run_falsification(verdict, question, ai_answer)
        if self.error_store and (verdict.verdict in ('FAIL', 'CONFLICT') or verdict.confidence < 0.5):
            try:
                self.error_store.add(question=question[:500] if question else '', answer=verdict.final_answer[:500] if verdict.final_answer else '', verdict=verdict.verdict, domain=verdict.domain or 'unknown', error_type='low_confidence' if verdict.confidence < 0.5 else verdict.verdict.lower(), details={'confidence': verdict.confidence, 'reasoning': verdict.reasoning[:200] if verdict.reasoning else ''})
            except Exception as e:
                logger.debug(f' ErrorStore add error: {e}')
        if self.governance:
            try:
                ab_results = _build_governance_antibody_results(verdict.slm_responses)
                gov_decision = self.governance.decide(ctx={'domain': verdict.domain, 'session_id': ''}, verdict={'confidence': verdict.confidence, 'antibody_results': ab_results, 'hallucination_detected': verdict.verdict == 'FAIL', 'missing_evidence': verdict.verdict == 'UNKNOWN'}, council_confidence=verdict.confidence)
                verdict.evidence['governance_decision'] = gov_decision.decision.value
                verdict.evidence['governance_reason'] = gov_decision.reason
                verdict.evidence['governance_principle_violations'] = gov_decision.principle_violations
                if gov_decision.decision.value == 'KILL':
                    verdict.verdict = 'FAIL'
                    verdict.final_answer = ''
                    verdict.reasoning += f' | Governance KILL: {gov_decision.reason} (answer withheld)'
                    verdict.evidence['governance_abstain'] = True
                    logger.info(f'[V104.40] Governance KILL abstain: {gov_decision.reason}')
                    if self.notifications:
                        try:
                            self.notifications.notify(event_type='governance_kill', title='Governance KILL', message=f'Question: {question[:100]}\nReason: {gov_decision.reason}', severity='critical')
                        except Exception as e:
                            logger.warning(f'[judge] governance_kill notify failed: {e}')
                elif gov_decision.decision.value == 'ESCALATE':
                    if verdict.verdict == 'PASS':
                        verdict.verdict = 'UNKNOWN'
                        verdict.reasoning += f' | Governance ESCALATE: {gov_decision.reason} (human review required)'
                        verdict.evidence['human_review_required'] = True
                        logger.info(f'[V104.40] Governance ESCALATE: {gov_decision.reason}')
            except Exception as e:
                logger.debug(f' Governance decide error: {e}')
        v98_policy = None
        v98_counter_result = None
        if self.attack_policy:
            try:
                classification_dict = v98_classification.to_dict() if v98_classification else {'actor': 'human', 'attack_type': 'none', 'severity': 'none', 'confidence': verdict.confidence}
                if v98_attack_match and v98_attack_match.get('matched'):
                    classification_dict['attack_type'] = 'injection'
                    classification_dict['severity'] = 'high'
                target_verification = None
                if v98_threat_signal and v98_threat_signal.asn_intel:
                    target_verification = {'safe_to_counter': not v98_threat_signal.asn_intel.get('is_residential', False) and (not v98_threat_signal.asn_intel.get('is_tor', False)), 'is_residential': v98_threat_signal.asn_intel.get('is_residential', False), 'is_tor': v98_threat_signal.asn_intel.get('is_tor', False)}
                governance_dict = {'decision': verdict.evidence.get('governance_decision', 'UPHOLD')}
                v98_policy = self.attack_policy.decide(classification=classification_dict, target_verification=target_verification, governance_decision=governance_dict)
                verdict.evidence['v98_attack_policy'] = v98_policy.to_dict()
            except Exception as e:
                logger.debug(f' AttackPolicyEngine error: {e}')
        if v98_policy and v98_policy.phase > 0 and self.counter_response:
            try:
                attacker_ip = (v98_context or {}).get('ip', 'internal')
                attack_type = v98_classification.attack_type if v98_classification else v98_attack_match.get('attack_type', 'injection') if v98_attack_match else 'injection'
                import asyncio as _a
                try:
                    v98_counter_result = _a.run(self.counter_response.execute(policy=v98_policy, attacker_ip=attacker_ip, original_response=verdict.final_answer, attack_type=attack_type))
                    if v98_counter_result and v98_counter_result.modified_response:
                        if 'poison_response' in v98_counter_result.actions:
                            verdict.final_answer = v98_counter_result.modified_response
                            verdict.evidence['v98_counter_response'] = {'actions': v98_counter_result.actions, 'phase': v98_policy.phase, 'canary_token': v98_counter_result.canary_token}
                except RuntimeError as re:
                    logger.debug(f' CounterResponse asyncio.run fallback: {re}')
                    import concurrent.futures as _cf
                    try:
                        _cr_pool = _cf.ThreadPoolExecutor(max_workers=1)
                        _future = _cr_pool.submit(_a.run, self.counter_response.execute(policy=v98_policy, attacker_ip=attacker_ip, original_response=verdict.final_answer, attack_type=attack_type))
                        v98_counter_result = _future.result(timeout=10)
                        _cr_pool.shutdown(wait=False)
                        if v98_counter_result and v98_counter_result.modified_response:
                            if 'poison_response' in v98_counter_result.actions:
                                verdict.final_answer = v98_counter_result.modified_response
                                verdict.evidence['v98_counter_response'] = {'actions': v98_counter_result.actions, 'phase': v98_policy.phase, 'canary_token': v98_counter_result.canary_token}
                    except Exception as e2:
                        logger.debug(f' CounterResponse thread fallback error: {e2}')
            except Exception as e:
                logger.debug(f' CounterResponseEngine error: {e}')
        if v98_policy and v98_policy.phase >= 2 and self.canary_monitor:
            try:
                attacker_ip = (v98_context or {}).get('ip', 'internal')
                canary = self.canary_monitor.generate(attacker_ip)
                verdict.evidence['v98_canary_token'] = canary.token
            except Exception as e:
                logger.debug(f' CanaryTokenMonitor error: {e}')
        if self.attack_memory and verdict.verdict == 'PASS':
            _attacker_actors = {'bot_legacy', 'scanner', 'attacker', 'exploit_tool'}
            is_attack = v98_attack_match and v98_attack_match.get('matched') or (v98_guard_verdict and v98_guard_verdict.is_poisoned) or (v98_classification and v98_classification.actor in _attacker_actors and (getattr(v98_classification, 'severity', 'low') in ('medium', 'high', 'critical')))
            if is_attack:
                try:
                    attack_type = v98_classification.attack_type if v98_classification else v98_attack_match.get('attack_type', 'injection') if v98_attack_match else 'injection'
                    signatures = v98_classification.strong_signals if v98_classification else []
                    self.attack_memory.record_bypass(question=question[:500], answer=verdict.final_answer[:500], attack_type=attack_type, signatures=signatures)
                    verdict.evidence['v98_bypass_recorded'] = True
                    if verdict.verdict == 'PASS':
                        verdict.verdict = 'FAIL'
                        verdict.final_answer = '[SCP: Answer withheld — bypass detected]'
                        verdict.reasoning += ' | [V104.42 #BA] Bypass detected → FAIL + abstain'
                        verdict.evidence['bypass_retract'] = True
                    logger.warning('[V104.42 #BA] Bypass retract: verdict downgraded PASS → FAIL')
                    if self.notifications:
                        try:
                            self.notifications.notify(event_type='bypass_detected', title='Bypass Detected', message=f'Question: {question[:100]}\nAttack: {attack_type}', severity='critical')
                        except Exception as e:
                            logger.warning(f'[judge] bypass_detected notify failed: {e}')
                except Exception as e:
                    logger.debug(f' AttackPatternMemory record error: {e}')
        if v98_guard_verdict:
            verdict.evidence['v98_guard_verdict'] = v98_guard_verdict.to_dict()
        if v98_threat_signal:
            verdict.evidence['v98_threat_signal'] = v98_threat_signal.to_dict()
        if v98_classification:
            verdict.evidence['v98_classification'] = v98_classification.to_dict()
        if v98_attack_match:
            verdict.evidence['v98_attack_match'] = v98_attack_match
        with _v100_timer.phase('extraction'):
            self._run_antibodies(verdict, question, ai_answer)
            if self.claim_extractor and verdict.final_answer:
                try:
                    v100_claims = self.claim_extractor.extract(verdict.final_answer, question)
                    if self.claim_verifier and v100_claims:
                        _filtered_slm_responses, _evidence_filter_report = filter_slm_responses(question, slm_responses or [])
                        if _evidence_filter_report.get('droppedCount'):
                            slm_responses = _filtered_slm_responses
                            verdict.slm_responses = _filtered_slm_responses
                        verdict.evidence['evidence_consistency'] = _evidence_filter_report
                        ground_truth = {}
                        for hit in v100_kb_hits:
                            ground_truth[hit.source] = hit.answer
                        for _slm_resp in slm_responses or []:
                            if 'error' in _slm_resp or not _slm_resp.get('answer'):
                                continue
                            _slm_name = _slm_resp.get('slm_name') or _slm_resp.get('source') or _slm_resp.get('domain', 'unknown')
                            _slm_evidence = _slm_resp.get('evidence') or {}
                            if isinstance(_slm_evidence, dict):
                                if _slm_evidence.get('value') is not None:
                                    ground_truth[f'{_slm_name}_value'] = _slm_evidence['value']
                                    if _slm_evidence.get('unit'):
                                        ground_truth[f'{_slm_name}_unit'] = _slm_evidence['unit']
                                if _slm_evidence.get('source'):
                                    ground_truth[f'{_slm_name}_source'] = _slm_evidence['source']
                        v100_claims = self.claim_verifier.verify(v100_claims, ground_truth)
                        v100_claim_summary = self.claim_verifier.summarize(v100_claims)
                        verdict.evidence['v100_claims'] = v100_claim_summary
                        _refuted = v100_claim_summary.get('refuted', 0)
                        _verified = v100_claim_summary.get('verified', 0)
                        _unverified = v100_claim_summary.get('unverified', 0)
                        _total = _verified + _unverified + _refuted
                        if _refuted > 0:
                            verdict.confidence *= 0.5
                            verdict.reasoning += f' |  {_refuted} claims refuted'
                        if _total > 0 and _unverified / _total > 0.5 and (not (_math_verdict == 'PASS' and verdict.verdict == 'PASS')):
                            logger.warning(f' {_unverified}/{_total} claims unverified — UPHOLD verdict from {verdict.verdict} to UNKNOWN')
                            if verdict.verdict == 'PASS':
                                verdict.verdict = 'UNKNOWN'
                                verdict.confidence = min(verdict.confidence, 0.4)
                                verdict.reasoning += f' | [R17] UPHOLD: {_unverified}/{_total} claims unverified'
                except Exception as e:
                    logger.debug(f' Claim extraction error: {e}')
        with _v100_timer.phase('falsification'):
            if self.logical_auditor and self.logical_auditor.should_audit(verdict.verdict, verdict.final_answer):
                try:
                    import asyncio as _a
                    import concurrent.futures as _cf
                    _pool = _cf.ThreadPoolExecutor(max_workers=1)
                    audit_result = _pool.submit(_a.run, self.logical_auditor.audit(text_to_audit=verdict.final_answer, context=f'Question: {question[:200]}')).result(timeout=30)
                    self._apply_logical_audit(verdict, audit_result)
                    _pool.shutdown(wait=False)
                except Exception as e:
                    logger.debug(f' LogicalAuditor error: {e}')
        if self.self_questioning and verdict.verdict in ('PASS', 'FAIL', 'SPECULATIVE'):
            try:
                sq_result = self.self_questioning.question(question=question, answer=verdict.final_answer, verdict=verdict.verdict, confidence=verdict.confidence, reasoning=verdict.reasoning, slm_responses=verdict.slm_responses, evidence=verdict.evidence, domain=verdict.domain)
                verdict.evidence['v106_self_questioning'] = sq_result.to_dict()
                if sq_result.verdict_challenged:
                    verdict.confidence = sq_result.revised_confidence
                    verdict.reasoning += f' | [V106 SelfQuestion] {sq_result.self_critique[:100]}'
            except Exception as e:
                logger.debug(f' SelfQuestioning error: {e}')
        with _v100_timer.phase('learning'):
            if self.domain_knowledge_store and verdict.verdict == 'PASS' and verdict.final_answer:
                try:
                    self.domain_knowledge_store.store(question=question[:500], answer=verdict.final_answer[:500], domain=verdict.domain or 'general', source='scp_learned', source_url='', confidence=verdict.confidence, collected_by='on_demand', verified_by=['scp_pipeline'])
                except Exception as e:
                    logger.debug(f' KB save error: {e}')
            if self.h8_redteam and verdict.verdict == 'PASS':
                try:
                    self.h8_redteam.record_normal_question(question[:200])
                except Exception as e:
                    logger.warning(f'[judge] h8_redteam.record_normal_question failed: {e}')
            if self.h8_redteam:
                try:
                    h8_record = self.h8_redteam.record_bypass(question=question, answer=verdict.final_answer, verdict=verdict.verdict, classification=v98_classification.to_dict() if v98_classification else {'actor': 'human', 'confidence': 0.5}, source=source or 'unknown', attacker_ip=(v98_context or {}).get('ip', 'internal'))
                    if h8_record:
                        verdict.evidence['v100_bypass_detected'] = True
                        verdict.evidence['v100_bypass_id'] = h8_record.bypass_id
                        verdict.evidence['v100_canary_token'] = h8_record.canary_token
                except Exception as e:
                    logger.debug(f' H8 error: {e}')
        with _v100_timer.phase('output'):
            v100_timings = _v100_timer.finish()
            verdict.evidence['v100_phase_timings'] = v100_timings.to_dict()
            verdict.evidence['v100_kb_hits'] = len(v100_kb_hits)
            if v100_kb_hits:
                verdict.evidence['v100_kb_top_hit'] = {'question': v100_kb_hits[0].question[:100], 'answer': v100_kb_hits[0].answer[:100], 'source': v100_kb_hits[0].source, 'tier': v100_kb_hits[0].source_tier, 'confidence': v100_kb_hits[0].confidence}
        if self.healing_engine and verdict.verdict in ('FAIL', 'CONFLICT', 'UNKNOWN'):
            try:
                _system_state = {'verdict': verdict.verdict, 'confidence': verdict.confidence, 'domain': verdict.domain or 'general', 'question': question[:200]}
                _issues = self.healing_engine.monitor(_system_state)
                if _issues and _issues.get('issues'):
                    for _issue in _issues['issues'][:3]:
                        try:
                            _heal_result = self.healing_engine.heal(_issue)
                            _strategy = _heal_result.get('strategy', 'NO_STRATEGY') if _heal_result else 'NO_STRATEGY'
                            _success = _heal_result.get('success', False) if _heal_result else False
                            _verdict_improved = False
                            _RECHECK_ISSUE_TYPES = ('slm_confidence_low', 'all_slm_fail', 'slm_error', 'stale_data')
                            if _success and _issue.get('type') in _RECHECK_ISSUE_TYPES:
                                try:
                                    _heal_slm_name = primary.get('slm_name', '') if primary else ''
                                    _heal_domain = verdict.domain or 'general'
                                    if _heal_slm_name and _heal_slm_name in self.slms:
                                        _re_slm = self.slms[_heal_slm_name]
                                        _re_result = _re_slm.predict(question)
                                        _new_conf = _re_result.confidence if hasattr(_re_result, 'confidence') else 0
                                        if _new_conf > confidence:
                                            _verdict_improved = True
                                            logger.info(f'[V104.47 #10] Healing improved: {confidence:.2f} → {_new_conf:.2f}')
                                except Exception as e:
                                    logger.warning(f'Silent except: {e}')
                            _heal_result['verdict_improved'] = _verdict_improved
                            verdict.evidence.setdefault('healing_actions', []).append({'strategy': _strategy, 'success': _success, 'verdict_improved': _verdict_improved})
                            logger.info(f'[V104.45 #BV] Healing: strategy={_strategy} success={_success} improved={_verdict_improved}')
                        except Exception as _he:
                            logger.debug(f'[V104.45 #BV] Healing strategy error: {_he}')
            except Exception as e:
                logger.debug(f'[V104.45 #BV] Healing monitor error: {e}')
        try:
            _rep_store = None
            if self._source_watchlist is not None:
                _rep_store = getattr(self._source_watchlist, 'store', None)
            if _rep_store is None:
                from scp.knowledge.source_reputation import ReputationStore as _RS
                _rep_store = _RS()
            _v58_was_correct = verdict.verdict == 'PASS'
            _v58_domain = verdict.domain or 'general'
            _v58_sources_seen: set = set()
            for _r in verdict.slm_responses or []:
                try:
                    _ev = _r.get('evidence') or {}
                    _src = _ev.get('source') or _r.get('slm_name')
                    if _src and isinstance(_src, str) and (_src not in _v58_sources_seen):
                        _v58_sources_seen.add(_src)
                        try:
                            _rep_store.record_outcome(_src, _v58_domain, _v58_was_correct)
                        except Exception as _re:
                            logger.debug(f'[V5.8-OPT] record_outcome failed for SLM source={_src!r}: {_re}')
                except Exception:
                    continue
            try:
                _rc = (verdict.evidence or {}).get('reality_check')
                if isinstance(_rc, dict):
                    _rc_src = _rc.get('source')
                    if _rc_src and isinstance(_rc_src, str) and (_rc_src not in _v58_sources_seen):
                        _v58_sources_seen.add(_rc_src)
                        try:
                            _rep_store.record_outcome(_rc_src, _v58_domain, _v58_was_correct)
                        except Exception as _re:
                            logger.debug(f'[V5.8-OPT] record_outcome failed for reality source={_rc_src!r}: {_re}')
            except Exception as e:
                logger.warning(f'Silent except: {e}')
            if _v58_sources_seen:
                try:
                    verdict.evidence['v58_source_reputation_recorded'] = {'sources': sorted(_v58_sources_seen), 'domain': _v58_domain, 'was_correct': _v58_was_correct, 'verdict': verdict.verdict}
                except Exception as e:
                    logger.warning(f'Silent except: {e}')
        except Exception as e:
            logger.debug(f'[V5.8-OPT] source_reputation wire failed (non-fatal): {e}')
        try:
            _meta = _SCPMeta()
            _meta_review = _meta.review(question, verdict.verdict)
            if _meta_review.council_decision.value == 'SKIP':
                verdict.verdict = 'UNKNOWN'
                verdict.reasoning += '. META: SKIP'
            elif _meta_review.council_decision.value == 'DEFER_HUMAN':
                verdict.verdict = 'UNKNOWN'
                verdict.reasoning += '. META: DEFER_HUMAN'
        except Exception as _meta_err:
            import logging as _logging
            _logging.getLogger('scp.judge').debug(f'SCPMeta review failed: {_meta_err}')
        return verdict

    def _check_knowledge_conflicts(self, why_result, why_plan, question, _pre_verdict_evidence):
        """[OPT-42] Check for knowledge conflicts using KnowledgeArbiter.

        Extracted from judge() to reduce CC. TẠI SAO: KnowledgeArbiter was
        wired inline (CC bloat). ADDITIVE: only consults arbiter + logs;
        does not modify why_engine logic. Arbiter facts are per-judge-call
        (short-lived) — same pattern as why_result.
        """
        try:
            if not hasattr(self, 'knowledge_arbiter') or not self.knowledge_arbiter or (not why_result):
                return
            _all_values = why_result.get('all_values') or []
            _target = why_result.get('target') or getattr(why_plan, 'target', '') or question
            if len(_all_values) > 1:
                for _sv in _all_values:
                    self.knowledge_arbiter.add_fact(entity=_target, attribute='value', value=str(_sv.get('value', '')), source=str(_sv.get('source', 'unknown')), confidence=float(why_result.get('confidence', 0.5)))
                _arbiter_result = self.knowledge_arbiter.resolve(_target, 'value')
                if _arbiter_result.get('conflict'):
                    logger.warning(f"[KnowledgeArbiter] Conflict for '{_target}': values={_arbiter_result.get('conflicting_values')} winner={_arbiter_result.get('winner_source')} requires_verification={_arbiter_result.get('requires_verification')}")
                    _pre_verdict_evidence['knowledge_arbiter_conflict'] = {'entity': _target, 'conflicting_values': _arbiter_result.get('conflicting_values'), 'winner_source': _arbiter_result.get('winner_source'), 'requires_verification': _arbiter_result.get('requires_verification'), 'reason': _arbiter_result.get('reason')}
                else:
                    logger.debug(f"[KnowledgeArbiter] No conflict for '{_target}': reason={_arbiter_result.get('reason')}")
        except Exception as _ka_err:
            logger.debug(f'[KnowledgeArbiter] error: {_ka_err}')

    def _map_cwe_for_attack(self, unified_result, _pre_verdict_evidence):
        """[OPT-42] Map detected attack patterns to CWE.

        Extracted from judge() to reduce CC. TẠI SAO: CWEExploitStore was
        wired inline. ADDITIVE: ImportError/Exception is non-fatal; original
        UnifiedDetector flow untouched. Maps first confident pattern match
        to a CWE so verdict carries concrete mitigation + antibody hints.
        """
        try:
            if not unified_result or not getattr(unified_result, 'is_attack', False):
                return
            from scp.knowledge.cwe_exploit_store import CWEExploitStore
            _cwe_store = CWEExploitStore()
            for _pattern in unified_result.matched_patterns or []:
                _p_lower = str(_pattern).lower()
                if 'injection' in _p_lower or 'jailbreak' in _p_lower or 'ignore' in _p_lower:
                    _cwe = _cwe_store.get_cwe('CWE-LLM01')
                elif 'rce' in _p_lower or 'exec' in _p_lower or 'eval' in _p_lower:
                    _cwe = _cwe_store.get_cwe('CWE-94')
                elif 'exfil' in _p_lower:
                    _cwe = _cwe_store.get_cwe('CWE-LLM01')
                elif 'ssrf' in _p_lower or 'url' in _p_lower:
                    _cwe = _cwe_store.get_cwe('CWE-444')
                elif 'path' in _p_lower or 'traversal' in _p_lower:
                    _cwe = _cwe_store.get_cwe('CWE-22')
                elif 'xss' in _p_lower:
                    _cwe = _cwe_store.get_cwe('CWE-79')
                elif 'sql' in _p_lower:
                    _cwe = _cwe_store.get_cwe('CWE-89')
                else:
                    _cwe = None
                if _cwe:
                    logger.info(f"[CWE] Pattern '{_pattern}' → {_cwe.cwe_id}: {_cwe.name} (severity={_cwe.severity}, antibodies={_cwe.antibodies})")
                    _pre_verdict_evidence['cwe_mapping'] = {'pattern': _pattern, 'cwe_id': _cwe.cwe_id, 'cwe_name': _cwe.name, 'severity': _cwe.severity, 'mitigation': _cwe.mitigation, 'antibodies': _cwe.antibodies}
                    break
        except ImportError as e:
            logger.warning(f'Silent except: {e}')
        except Exception as _cwe_err:
            logger.debug(f'[CWE] lookup error: {_cwe_err}')

    def _reality_check_deterministic(self, slm_name: str, question: str, answer: str, primary_response: dict) -> tuple[bool, str]:
        """[P0-2 FIX R16] Lightweight independent verify cho deterministic SLM.

        WHY: Q11-FP-3 found MathSLM/ConversionSLM/StatisticsSLM/LogicSLM with
        conf>=0.95 returned PASS without any verification. A bug in any of
        these 4 SLMs would go unchecked. This method independently re-verifies
        the SLM's answer before allowing the PASS short-circuit.

        Returns: (ok: bool, message: str)
          - (True, "re-eval matched") → SLM answer confirmed, PASS allowed
          - (False, "mismatch: expected X got Y") → SLM answer wrong, downgrade to UNKNOWN
          - (True, "no checker for {slm_name}, trusting (logged)") → fail-open for unimplemented

        DNA #26 (Reality > Model): deterministic SLM confidence is a MODEL claim;
        this method provides the REALITY check.
        """
        import re as _re
        try:
            _ans_str = str(answer or '').strip()
            _result_match = _re.search('=\\s*(-?\\d+(?:\\.\\d+)?)', _ans_str)
            if _result_match:
                _ans_num = float(_result_match.group(1))
            else:
                _numbers = _re.findall('-?\\d+(?:\\.\\d+)?', _ans_str)
                _ans_num = float(_numbers[-1]) if _numbers else None
            if 'MathSLM' in slm_name:
                _expr_match = _re.search('[\\d\\s\\+\\-\\*\\/\\(\\)\\.\\^]+=\\s*\\??\\s*[\\d\\?\\s]*', question)
                if not _expr_match:
                    _expr_match = _re.search('(?:what is|calculate|tính|compute|eval)\\s+(.+)', question, _re.IGNORECASE)
                if _expr_match and _ans_num is not None:
                    _expr = _expr_match.group(1).strip().rstrip('?').strip()
                    _expr = _re.sub('\\s*=\\s*.*$', '', _expr).strip()
                    if _re.fullmatch('[\\d\\s\\+\\-\\*\\/\\(\\)\\.\\^]+', _expr):
                        try:
                            from scp.runtime.safe_math import safe_eval_arithmetic
                            _re_eval = safe_eval_arithmetic(_expr)
                            if _re_eval is not None:
                                _re_num = float(_re_eval)
                                if abs(_re_num - _ans_num) < 0.01:
                                    return (True, f'MathSLM re-eval matched: {_expr}={_re_num}')
                                else:
                                    return (False, f'MathSLM mismatch: re-eval {_expr}={_re_num}, SLM said {_ans_num}')
                        except Exception as _ee:
                            return (True, f'MathSLM re-eval failed ({_ee}), trusting SLM (logged)')
                return (True, 'MathSLM: no expression extracted, trusting SLM (logged)')
            if 'ConversionSLM' in slm_name:
                if _ans_num is not None:
                    _src_match = _re.search('(\\d+(?:\\.\\d+)?)\\s*(?:usd|vnd|km|mi|miles?|kg|lb|lbs|c|f)', question, _re.IGNORECASE)
                    if _src_match:
                        _src_num = float(_src_match.group(1))
                        _unit = _src_match.group(0).lower().split()[-1] if _src_match.group(0).lower().split() else ''
                        if _ans_num <= 0:
                            return (False, f'ConversionSLM: answer {_ans_num} is non-positive (conversion error)')
                        if 'vnd' in question.lower() and 'usd' in question.lower():
                            if _src_num > 0 and _ans_num > 0:
                                _rate = _ans_num / _src_num if 'to vnd' in question.lower() else _src_num / _ans_num
                                if not 15000 < _rate < 30000:
                                    return (False, f'ConversionSLM: rate {_rate} outside plausible VND/USD range (15000-30000)')
                        return (True, f'ConversionSLM: answer {_ans_num} plausible (source={_src_num})')
                return (True, 'ConversionSLM: no numeric value extracted, trusting SLM (logged)')
            if 'StatisticsSLM' in slm_name:
                if _ans_num is not None:
                    _q_lower = question.lower()
                    if 'probability' in _q_lower or 'xác suất' in _q_lower:
                        if not 0 <= _ans_num <= 1:
                            return (False, f'StatisticsSLM: probability {_ans_num} outside [0,1]')
                        return (True, f'StatisticsSLM: probability {_ans_num} in [0,1] ✓')
                    if 'percent' in _q_lower or 'phần trăm' in _q_lower:
                        if not 0 <= _ans_num <= 100:
                            return (False, f'StatisticsSLM: percentage {_ans_num} outside [0,100]')
                        return (True, f'StatisticsSLM: percentage {_ans_num} in [0,100] ✓')
                    if _ans_num < 0 and 'count' in _q_lower or 'số lượng' in _q_lower:
                        return (False, f'StatisticsSLM: count {_ans_num} is negative')
                    return (True, f'StatisticsSLM: answer {_ans_num} plausible')
                return (True, 'StatisticsSLM: no numeric value extracted, trusting SLM (logged)')
            if 'LogicSLM' in slm_name:
                _ans_lower = _ans_str.lower()
                if _ans_lower in ('true', 'false', 'đúng', 'sai', '0', '1'):
                    return (True, f"LogicSLM: answer '{_ans_lower}' is valid boolean")
                if any((op in _ans_str for op in ['∧', '∨', '¬', '→', '↔', 'AND', 'OR', 'NOT', 'True', 'False'])):
                    return (True, 'LogicSLM: answer contains logic operators')
                logger.warning(f" LogicSLM answer '{_ans_str[:50]}' not verifiable — trusting (logged)")
                return (True, 'LogicSLM: answer format not recognized, trusting SLM (logged)')
            return (True, f"Unknown deterministic SLM '{slm_name}', trusting (logged)")
        except Exception as _rc:
            return (False, f'reality_check crashed: {_rc}')

    def _run_why_engine(self, question, ai_answer, _enable_closed_loop):
        """[Task 45-B] WHY Engine — create + execute verification plan.

        Extracted from judge() to reduce CC. TẠI SAO: WHY engine block was
        inline (~14 lines, 4 branches). Returns (why_plan, why_result) tuple.
        ADDITIVE: same logic, same guard, same logging — only relocated.
        """
        why_plan = None
        why_result = None
        if _enable_closed_loop and self.why_engine:
            try:
                why_plan = self.why_engine.create_verification_plan(question)
                if why_plan and ai_answer:
                    why_result = self.why_engine.execute_plan(why_plan, ai_answer)
                    logger.info(f"[WHY-FIX] Plan executed: verdict={why_result.get('verdict')}, sources={why_result.get('sources_queried')}")
            except Exception as e:
                logger.debug(f'WHY engine error: {e}')
        return (why_plan, why_result)

    def _run_falsification(self, verdict, question, ai_answer):
        """[Task 45-B] FalsificationEngine — translate + deviation + contradiction report.

        Extracted from judge() to reduce CC. TẠI SAO: Falsification block was
        inline (~100 lines, ~10 branches). Mutates verdict.evidence in place.
        ADDITIVE: same logic, same guards, same logging — only relocated.
        """
        if self.falsification:
            try:
                falsif_result = self.falsification.translate_old_verdict(verdict.verdict, {'confidence': verdict.confidence, 'domain': verdict.domain, 'contradictions': verdict.cross_validation.get('conflicts', []), 'scope': f'53 SLMs, {(self.error_store.count() if self.error_store else 0)} ErrorStore records'})
                verdict.evidence['falsification_status'] = falsif_result['status']
                verdict.evidence['falsification_scope'] = falsif_result.get('scope', '')
                verdict.evidence['falsification_note'] = falsif_result.get('note', '')
                try:
                    from scp.meta.falsification_engine import FalsificationStatus as _FS
                    _fstatus = falsif_result['status']
                    _fs_enum = _fstatus if isinstance(_fstatus, _FS) else _FS(_fstatus)
                    verdict.evidence['falsification_skeptical'] = _fs_enum.is_skeptical()
                    verdict.skeptical = bool(_fs_enum.is_skeptical())
                    if _fs_enum.requires_human() and getattr(self, 'escalation_manager', None):
                        self.escalation_manager.on_threat_detected({'type': 'falsification_human_review', 'severity': 'high', 'falsification_status': _fs_enum.value, 'question': question[:120], 'verdict': verdict.verdict, 'confidence': verdict.confidence, 'note': falsif_result.get('note', '')[:200]})
                        logger.warning(f" Falsification requires human review: status={_fs_enum.value} q={question[:60]!r} conf={verdict.confidence:.2f} — escalated to Dead Man's Switch")
                except Exception as _fe:
                    logger.debug(f' falsification escalation failed: {_fe}')
            except Exception as e:
                logger.debug(f' Falsification translate error: {e}')
        if self.falsification and verdict.reality_check:
            try:
                ground_truth: dict[str, Any] = {}
                real_val = verdict.reality_check.get('real_value')
                if real_val is not None:
                    ground_truth['real_value'] = real_val
                for _rk, _rv in verdict.reality_check.items():
                    if _rk in ('real_value', 'is_correct', 'verdict', 'reason', 'source', 'verdict_detail'):
                        continue
                    if isinstance(_rv, (int, float)) or (isinstance(_rv, str) and _rv.strip()):
                        ground_truth[_rk] = _rv
                if ground_truth:
                    evidence_list: list = []
                    for _r in verdict.slm_responses or []:
                        if isinstance(_r, dict):
                            _ans = _r.get('answer', '')
                            if _ans:
                                evidence_list.append(str(_ans))
                        else:
                            evidence_list.append(str(_r))
                    _dev = self.falsification.measure_deviation(ai_answer or '', ground_truth)
                    _report = self.falsification.generate_contradiction_report(question=question or '', llm_answer=ai_answer or '', evidence=evidence_list, ground_truth=ground_truth)
                    verdict.evidence['falsification_report'] = {'contradiction_count': len(_report.get('contradictions', [])), 'max_deviation': _dev.get('max_deviation', 0.0), 'deviation_status': _dev.get('status', ''), 'confidence': _report.get('confidence', 0.5), 'human_decision_required': _report.get('human_decision_required', False), 'v4_recommendation': _report.get('v4_recommendation', '')}
                    if _report.get('contradictions'):
                        verdict.evidence['falsification_contradictions'] = _report['contradictions'][:5]
                        logger.info(f" FalsificationEngine: {len(_report['contradictions'])} contradiction(s) detected (max_dev={_dev.get('max_deviation')})")
            except Exception as e:
                logger.debug(f' Falsification report error: {e}')

    def _run_antibodies(self, verdict, question, ai_answer=''):
        """[Task 45-B] DomainAntibodySystem — run 38 antibodies + downgrade/KILL.

        Extracted from judge() to reduce CC. TẠI SAO: Antibody block was inline
        (~35 lines, ~8 branches). Mutates verdict in place (evidence, reasoning,
        confidence, verdict, final_answer). ADDITIVE: same logic, same guards,
        same logging — only relocated.

        [G5-FIX] Previously only scanned `verdict.final_answer` (SCP's response).
        But the AI's *original claim* (`ai_answer`) may contain closure words
        even when SCP's response doesn't — e.g. AI says "Obviously true" to
        "Is earth flat?" → SCP's final_answer becomes a fallback like "Tôi
        không có đủ dữ liệu" → antibody finds no closure → no FAIL → test
        test_judge_closure_words_fail expects FAIL but got UNKNOWN.
        Fix: scan BOTH ai_answer AND verdict.final_answer; union the flagged
        results so closure words in either trigger downgrade.
        """
        if not self.antibody_system:
            return
        texts_to_scan = []
        if ai_answer:
            texts_to_scan.append(('ai_answer', ai_answer))
        if verdict.final_answer:
            texts_to_scan.append(('final_answer', verdict.final_answer))
        if not texts_to_scan:
            return
        try:
            all_results = []
            flagged = []
            seen_keys = set()
            for _source_label, text in texts_to_scan:
                ab_results = self.antibody_system.check(question=question, answer=text, domain=verdict.domain or 'general')
                for r in ab_results:
                    if not r.passed:
                        key = (r.antibody_name, r.details)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            flagged.append(r)
                    all_results.append(r)
            verdict.evidence['v103_antibodies'] = {'total_run': len(all_results), 'flagged': len(flagged), 'results': [r.to_dict() for r in all_results], 'scanned_texts': [t[0] for t in texts_to_scan]}
            if flagged:
                for r in flagged:
                    verdict.reasoning += f' | [Antibody] {r.antibody_name}: {r.details}'
                    if str(r.severity) in ('high', 'critical'):
                        verdict.confidence *= 0.5
                has_critical = any((str(r.severity) in ('critical', 'high') and (not r.passed) for r in flagged))
                if has_critical and verdict.verdict not in ('FAIL', 'KILL'):
                    _prev_verdict = verdict.verdict
                    verdict.verdict = 'FAIL'
                    verdict.final_answer = ''
                    verdict.reasoning += f' | [V104.41 #AF] CRITICAL antibody fail → FAIL (was {_prev_verdict}, abstain)'
                    verdict.evidence['antibody_kill'] = True
                    logger.info(f'[V104.41 #AF] Antibody CRITICAL override: {_prev_verdict} → FAIL (abstain)')
        except Exception as e:
            logger.debug(f' Antibody check error: {e}')

    def _attach_why_to_verdict(self, verdict, why_plan, why_result, confidence, question, ai_answer, primary_domain):
        """[Task 45-B] Attach WHY Engine plan/result to verdict evidence + Self-Suspend.

        Extracted from judge() to reduce CC. TẠI SAO: WHY-plan-to-verdict block
        was inline (~70 lines, ~10 branches). Mutates verdict.evidence, verdict.verdict,
        verdict.confidence, verdict.reasoning. Returns possibly-updated confidence.
        ADDITIVE: same logic, same guards, same logging — only relocated.
        """
        if why_plan:
            verdict.evidence['why_plan'] = {'target': why_plan.target, 'target_type': why_plan.target_type, 'evidence_type': why_plan.evidence_type, 'verification_strategy': why_plan.verification_strategy, 'sources_to_query': why_plan.sources_to_query, 'proof_criteria': why_plan.proof_criteria[:100], 'falsification_criteria': why_plan.falsification_criteria[:100], 'confidence_threshold': why_plan.confidence_threshold, 'reasoning': why_plan.reasoning}
            if why_result:
                verdict.evidence['why_result'] = {'verdict': why_result.get('verdict'), 'confidence': why_result.get('confidence'), 'sources_queried': why_result.get('sources_queried'), 'all_values': why_result.get('all_values'), 'reasoning': why_result.get('reasoning')}
                why_v = why_result.get('verdict', 'UNKNOWN')
                if why_v == 'FAIL' and verdict.verdict == 'PASS':
                    verdict.verdict = 'FAIL'
                    verdict.reasoning += f" | WHY Engine FAIL: {why_result.get('reasoning', '')[:100]}"
                elif why_v == 'CONFLICT':
                    verdict.verdict = 'CONFLICT'
                    verdict.reasoning += f" | WHY Engine CONFLICT: {why_result.get('reasoning', '')[:100]}"
                elif why_v == 'PASS' and verdict.verdict in ('UNKNOWN', 'PARTIAL'):
                    verdict.verdict = 'PASS'
                    confidence = max(confidence, why_result.get('confidence', 0.5))
                    verdict.confidence = max(verdict.confidence, why_result.get('confidence', 0.5))
                    verdict.reasoning += f" | WHY Engine PASS: {why_result.get('reasoning', '')[:100]}"
            if verdict.verdict == 'PASS' and confidence < why_plan.confidence_threshold and (why_plan.evidence_type not in ('deterministic_calculation', 'deterministic_evaluation', 'codata_constants')):
                verdict.evidence['self_suspend'] = {'reason': f'PASS but confidence {confidence:.2f} < WHY threshold {why_plan.confidence_threshold}', 'action': 'marked_for_re_verification'}
                logger.info(f'Self-Suspend: {verdict.verdict} but confidence low — marked for re-verification')
                if self.reverify_scheduler:
                    try:
                        reverify_id = self.reverify_scheduler.enqueue_if_needed(question=question, ai_answer=ai_answer, domain=primary_domain, verdict=verdict.verdict, confidence=confidence, why_threshold=why_plan.confidence_threshold, evidence_type=why_plan.evidence_type)
                        if reverify_id:
                            verdict.evidence['self_suspend']['reverify_id'] = reverify_id
                    except Exception as e:
                        logger.debug(f'ReVerify enqueue error: {e}')
        return confidence

    def _apply_why_confidence_adjust(self, verdict, why_plan, why_result):
        """[Task 45-B] V5.7 WHY confidence adjustment (opt-in).

        Extracted from judge() to reduce CC. TẠI SAO: WHY confidence adjustment
        block was inline (~38 lines, ~6 branches). Mutates verdict.confidence,
        verdict.reasoning, verdict.evidence. ADDITIVE: same logic, same guards,
        same logging — only relocated. Opt-in via SCP_WHY_CONFIDENCE_ADJUST=1.
        """
        if os.environ.get('SCP_WHY_CONFIDENCE_ADJUST', '0') == '1' and why_plan and why_result and verdict:
            try:
                _why_v = why_result.get('verdict', 'UNKNOWN')
                _slm_v = verdict.verdict
                _adj_amount = 0.0
                _adj_reason = ''
                if _why_v == 'FAIL' and _slm_v == 'PASS':
                    _adj_amount = -0.2
                    _adj_reason = 'WHY FAIL vs SLM PASS — disagreement'
                elif _why_v == 'CONFLICT' and _slm_v == 'PASS':
                    _adj_amount = -0.15
                    _adj_reason = 'WHY CONFLICT vs SLM PASS — partial disagreement'
                elif _why_v == 'PASS' and _slm_v == 'PASS':
                    _adj_amount = 0.1
                    _adj_reason = 'WHY PASS + SLM PASS — agreement boost'
                if _adj_amount != 0.0:
                    _old_conf = verdict.confidence
                    verdict.confidence = max(0.0, min(1.0, verdict.confidence + _adj_amount))
                    verdict.reasoning += f' | [V5.7-WHY] confidence {_adj_amount:+.2f} ({_adj_reason}): {_old_conf:.2f} → {verdict.confidence:.2f}'
                    verdict.evidence['v57_why_confidence_adjust'] = {'why_verdict': _why_v, 'slm_verdict': _slm_v, 'adjustment': _adj_amount, 'before': _old_conf, 'after': verdict.confidence, 'reason': _adj_reason}
                    logger.info(f'[V5.7-WHY] confidence {_adj_amount:+.2f} ({_adj_reason}): {_old_conf:.2f} → {verdict.confidence:.2f}')
            except Exception as _why_conf_err:
                logger.debug(f'[V5.7-WHY] confidence adjustment failed (non-fatal): {_why_conf_err}')

    def _run_cognitive_engine(self, verdict, why_plan, question, primary_domain, confidence, primary, slm_responses, reality_check):
        """[Task 45-B] Cognitive Engine — 5 layers analysis.

        Extracted from judge() to reduce CC. TẠI SAO: Cognitive Engine block
        was inline (~82 lines, ~15 branches). Mutates verdict.evidence["cognitive"].
        ADDITIVE: same logic, same guards, same logging — only relocated.
        """
        if self.cognitive:
            try:
                if hasattr(why_plan, 'evidence_type'):
                    evidence_type = why_plan.evidence_type
                elif isinstance(why_plan, dict):
                    evidence_type = why_plan.get('evidence_type', '')
                else:
                    evidence_type = ''
                is_deterministic = evidence_type in ('deterministic_calculation', 'deterministic_evaluation', 'codata_constants', 'biological_database')
                primary_source = ''
                if primary:
                    primary_source = primary.get('evidence', {}).get('source', '')
                sources_succeeded = []
                sources_failed = []
                for r in slm_responses:
                    if 'error' in r:
                        sources_failed.append(r.get('domain', '?'))
                    elif r.get('evidence', {}).get('sources_succeeded'):
                        sources_succeeded.extend(r['evidence']['sources_succeeded'])
                    if r.get('evidence', {}).get('source'):
                        sources_succeeded.append(r['evidence']['source'])
                    elif r.get('answer'):
                        sources_succeeded.append(r.get('slm_name', r.get('domain', '?')))
                cognitive_result = self.cognitive.analyze(question=question, domain=primary_domain, verdict=verdict.verdict, confidence=confidence, sources_succeeded=sources_succeeded, sources_failed=sources_failed, why_plan=why_plan, reality_check=reality_check, evidence=verdict.evidence, primary_source=primary_source, evidence_type=evidence_type)
                if cognitive_result:
                    if is_deterministic:
                        cognitive_result['deterministic'] = True
                    verdict.evidence['cognitive'] = cognitive_result
                    layers_ran = []
                    if cognitive_result.get('meta_falsification'):
                        layers_ran.append('MetaFalsifier')
                    if cognitive_result.get('unknown_state'):
                        layers_ran.append('UnknownState')
                    if cognitive_result.get('counter_questions'):
                        layers_ran.append(f"CounterQuestion({len(cognitive_result['counter_questions'])})")
                    if cognitive_result.get('proof_graph'):
                        layers_ran.append('ProofGraph')
                    if cognitive_result.get('recursive_why'):
                        layers_ran.append('RecursiveWhy')
                    logger.info(f"[Cognitive V49] Layers ran: {', '.join(layers_ran) or 'none'} | domain={primary_domain} conf={confidence:.2f}")
                elif primary:
                    primary_source = primary.get('evidence', {}).get('source', '')
                    if primary_source:
                        rw = self.cognitive.recursive_why.recursive_why(question, primary_source, evidence_type)
                        verdict.evidence['cognitive'] = {'recursive_why': {'depth': rw.depth_reached, 'terminated_at': rw.terminated_at, 'final_trust': rw.final_trust, 'chain': [{'level': link.level, 'answer': link.answer, 'is_axiom': link.is_axiom} for link in rw.chain[:2]]}, 'skipped': 'no_cognitive_result'}
            except Exception as e:
                logger.debug(f'Cognitive analysis error: {e}')

    def _apply_cognitive_gate(self, verdict, why_plan, confidence, question, primary_domain, slm_responses):
        """[Task 45-B] Cognitive Gate — cognitive layers AFFECT verdict.

        Extracted from judge() to reduce CC. TẠI SAO: Cognitive Gate block was
        inline (~46 lines, ~10 branches). Mutates verdict.evidence, verdict.verdict,
        verdict.confidence. Returns possibly-updated confidence.
        ADDITIVE: same logic, same guards, same logging — only relocated.
        """
        cognitive_result = verdict.evidence.get('cognitive')
        if cognitive_result and verdict.verdict == 'PASS':
            try:
                from scp.meta.cognitive_gate import get_cognitive_gate
                gate = get_cognitive_gate()
                evidence_type = why_plan.evidence_type if why_plan else ''
                sources_succeeded_for_gate = []
                for r in slm_responses:
                    ev = r.get('evidence', {})
                    if ev.get('sources_succeeded'):
                        sources_succeeded_for_gate.extend(ev['sources_succeeded'])
                    if ev.get('source'):
                        sources_succeeded_for_gate.append(ev['source'])
                    elif r.get('answer') and (not ev.get('source')):
                        sources_succeeded_for_gate.append(r.get('slm_name', r.get('domain', '?')))
                gated_verdict, gate_reasons, original_verdict = gate.evaluate(verdict=verdict.verdict, confidence=confidence, cognitive_result=cognitive_result, evidence_type=evidence_type, sources_succeeded=sources_succeeded_for_gate, question=question, domain=primary_domain)
                if gated_verdict != verdict.verdict:
                    verdict.evidence['cognitive_gate'] = {'original_verdict': original_verdict, 'gated_verdict': gated_verdict, 'reasons': gate_reasons}
                    verdict.verdict = gated_verdict
                    if gated_verdict == 'UNKNOWN':
                        confidence *= 0.4
                        verdict.confidence = confidence
                    elif gated_verdict == 'PARTIAL':
                        confidence *= 0.7
                        verdict.confidence = confidence
            except Exception as e:
                logger.debug(f'CognitiveGate error: {e}')
        return confidence

    def _run_multi_llm_check(self, verdict, question, ai_answer):
        """[Task 45-B] Multi-LLM cross-check (opt-in via SCP_MULTI_LLM_CHECK=1).

        Extracted from judge() to reduce CC. TẠI SAO: Multi-LLM check block was
        inline (~33 lines, ~5 branches). Mutates verdict.evidence, verdict.confidence,
        verdict.reasoning. ADDITIVE: same logic, same guards, same logging — only
        relocated. Two independent layers: source-level (adversary) + model-level
        (multi-LLM). Opt-in via SCP_MULTI_LLM_CHECK=1 (default OFF — adds 2 LLM
        API calls/question). If providers disagree (speculative=True) → lower
        confidence by 0.1.
        """
        multi_llm_checker = _get_multi_llm_checker()
        if multi_llm_checker is not None and ai_answer:
            try:
                ml_result = multi_llm_checker.check(question, ai_answer)
                verdict.evidence['v106_multi_llm_check'] = {'consensus': ml_result.get('consensus'), 'similarity': ml_result.get('similarity'), 'speculative': ml_result.get('speculative'), 'reason': ml_result.get('reason'), 'providers_queried': list(ml_result.get('provider_answers', {}).keys())}
                if ml_result.get('speculative'):
                    old_conf = verdict.confidence
                    verdict.confidence = max(0.0, verdict.confidence - 0.1)
                    verdict.reasoning += f" | [V5.3] Multi-LLM speculative ({ml_result.get('consensus')}, sim={ml_result.get('similarity', 0):.2f}): confidence {old_conf:.2f} → {verdict.confidence:.2f}"
                    logger.info(f"[V5.3-WIRE] Multi-LLM speculative: consensus={ml_result.get('consensus')} sim={ml_result.get('similarity')} — confidence lowered by 0.1")
                else:
                    logger.debug(f"[V5.3-WIRE] Multi-LLM consensus={ml_result.get('consensus')} sim={ml_result.get('similarity')} — no confidence adjustment")
            except Exception as e:
                logger.warning(f'[V5.3-WIRE] multi_llm_check failed: {e} — skipping (non-fatal)')
                verdict.evidence['v106_multi_llm_check'] = {'error': str(e)}
