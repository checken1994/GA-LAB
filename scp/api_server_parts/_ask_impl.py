# Auto-extracted from api_server.py
from __future__ import annotations
from scp.security.env_loader import load_selected_env
from fastapi import Depends
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Histogram
from fastapi.responses import Response
from scp.security.jwt_guard import get_current_user
from scp.observability.telemetry import setup_telemetry
import asyncio
import base64
import binascii
import logging
import os
import threading
from typing import Any
import time
from collections import deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from scp.web_control.internet_search import InternetSearch
from scp.api_server_parts.helpers import AskRequest, AskResponse, _extract_v98_context, _safe_fetch_url, get_judge
from scp.core.request_run_ledger import RequestRunLedger, stage_request, traced_request
from typing import TYPE_CHECKING
from scp import __version__ as _SCP_VERSION
from scp.core.release_identity import DOMAIN_EXPERT_ENSEMBLE_TERM, RELEASE_LABEL, public_release_metadata
from scp.core.streaming_factcheck import StreamingFactChecker
from scp.meta.simple_explainer import SimpleExplainer
from scp.runtime.judge import RealityJudge
from scp.security.attack_crawler import AttackCrawler
from scp.security.cross_language_learner import CrossLanguageLearner
from scp.security.image_voice_detector import ImageJailbreakDetector, VoiceJailbreakDetector
from scp.security.multi_turn_tracker import MultiTurnTracker
from scp.core.real_learning_engine import RealLearningEngine
from scp.api.route_profile import resolve_api_profile, route_group_enabled
from pydantic import BaseModel

async def _ask_impl(req: AskRequest, request: Request):
    """Main endpoint │Ă¢â€šÂ¬Ă¢â‚¬Â  question → V98 pipeline → verdict.

    Pipeline:
      1.  MemoryPoisoningGuard + AttackPatternMemory + ThreatDetector
      2.  Route → SLM predict → RealityJudge
      3.  FalsificationEngine + ErrorStore + Governance
      4.  AttackPolicy + CounterResponse + Canary + AttackPatternMemory.record_bypass
    """
    t0 = time.time()
    judge = get_judge()
    stage_request(request, 'judge_ready')
    v98_context = _extract_v98_context(request)
    _web_fallback_used = False
    _web_fallback: dict = {}
    v98_context['body'] = req.question
    if req.session_id:
        v98_context['session_id'] = req.session_id
    _history = []
    for _turn in (req.conversation_history or [])[-8:]:
        if not isinstance(_turn, dict):
            continue
        _role = str(_turn.get('role', 'user'))[:16]
        _content = str(_turn.get('content', ''))[:500].strip()
        if _content and _role in {'user', 'assistant'}:
            _history.append({'role': _role, 'content': _content})
    if _history:
        v98_context['conversation_history'] = _history
    try:
        from scp.api.cognitive_router import run_pre_judge_hooks
        v98_context = await run_pre_judge_hooks(req.question, v98_context)
    except Exception as e:
        logger.warning(f'Cognitive router failed: {e}')
    if hasattr(judge, 'dos_protection') and judge.dos_protection:
        try:
            client_ip = request.client.host if request.client else 'unknown'
            dos_alert = judge.dos_protection.check_request(client_ip)
            action = getattr(dos_alert, 'action_taken', '') if dos_alert else ''
            should_block = action in ('block', 'throttle') or (isinstance(dos_alert, dict) and dos_alert.get('should_block'))
            if should_block:
                status_code = int(getattr(dos_alert, 'status_code', 0) or 429)
                headers = dict(getattr(dos_alert, 'recommended_headers', {}) or {})
                return JSONResponse({'error': {'message': 'Rate limit exceeded', 'type': 'rate_limit_error'}}, status_code=status_code, headers=headers)
        except Exception as e:
            logger.debug(f'[V104.17] DoS check error: {e}')
    _multimodal_block = False
    _img_bytes = None
    if req.image_data:
        try:
            _raw_image = req.image_data
            if ',' in _raw_image and _raw_image.lower().startswith('data:'):
                _raw_image = _raw_image.split(',', 1)[1]
            _img_bytes = base64.b64decode(_raw_image, validate=True)
            if not _img_bytes or len(_img_bytes) > 6000000:
                raise ValueError('image_too_large_or_empty')
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=400, detail='Invalid or oversized image_data') from None
    if req.image_url and _img_bytes is None:
        try:
            _img_bytes = await asyncio.to_thread(_safe_fetch_url, req.image_url)
        except ValueError:
            logger.warning('[V104.45 #CP] /ask image_url rejected by _safe_fetch_url policy')
            raise HTTPException(status_code=400, detail='Invalid or disallowed image_url') from None
        except Exception as e:
            logger.debug(f'[V104.45 #CP] Image fetch error: {e}')
            _img_bytes = None
        if _img_bytes:
            try:
                _img_result = _image_detector.detect(image_bytes=_img_bytes)
                if _img_result and _img_result.jailbreak_detected:
                    logger.warning('[V104.45 #CP] Image jailbreak detected on /ask')
                    _multimodal_block = True
            except Exception as e:
                logger.debug(f'[V104.45 #CP] Image detect error: {e}')
    if req.voice_url:
        try:
            _voice_bytes = await asyncio.to_thread(_safe_fetch_url, req.voice_url)
        except ValueError:
            logger.warning('[V104.45 #CP] /ask voice_url rejected by _safe_fetch_url policy')
            raise HTTPException(status_code=400, detail='Invalid or disallowed voice_url') from None
        except Exception as e:
            logger.debug(f'[V104.45 #CP] Voice fetch error: {e}')
            _voice_bytes = None
        if _voice_bytes:
            try:
                _voice_result = _voice_detector.detect(audio_bytes=_voice_bytes)
                if _voice_result and _voice_result.jailbreak_detected:
                    logger.warning('[V104.45 #CP] Voice jailbreak detected on /ask')
                    _multimodal_block = True
            except Exception as e:
                logger.debug(f'[V104.45 #CP] Voice detect error: {e}')
    if _multimodal_block:
        return AskResponse(verdict='FAIL', final_answer='[SCP: Answer withheld │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d multimodal jailbreak detected]', confidence=0.0, domain='security', elapsed_ms=0, session_id=v98_context['session_id'])
    _ai_answer = req.ai_answer
    if not _ai_answer or not _ai_answer.strip():
        try:
            from scp.llm_gateway import get_gateway
            _gateway = get_gateway()
            _generated_answer, _provider = await _gateway.chat(req.question, context='Lịch sử gần đây (chỉ để tham khảo):\n' + '\n'.join((f"{t['role']}: {t['content']}" for t in _history)) if _history else '', system_prompt='Bạn là SCP — một trợ lý AI thông minh. Trả lời ngắn gọn, chính xác, bằng tiếng Việt. Chỉ trả lời câu hỏi HIỆN TẠI ở cuối yêu cầu. Không tiếp tục chủ đề cũ nếu câu hỏi mới đổi chủ đề. Nếu thiếu dữ liệu, nói rõ chưa đủ dữ liệu thay vì đoán.', task='chat')
            if _generated_answer:
                _ai_answer = _generated_answer
                logger.info(f'[CHATBOT] LLM ({_provider}) generated answer: {_generated_answer[:80]}...')
        except Exception as _generation_error:
            logger.warning(f'[CHATBOT] LLM call failed: {_generation_error}')
            if os.environ.get('SCP_WEB_FALLBACK', '1') == '1':
                try:
                    _web_timeout = min(float(os.environ.get('SCP_WEB_FALLBACK_TIMEOUT', '8')), 12.0)
                    _web_search = InternetSearch(timeout=min(_web_timeout / 2.0, 4.0))
                    _web_fallback = await asyncio.wait_for(_web_search.search(req.question, max_results=6), timeout=_web_timeout)
                    _web_fallback_used = bool(_web_fallback.get('success'))
                    _web_fallback['trigger'] = 'llm_timeout_or_error'
                    _web_fallback['llm_error'] = str(_generation_error)[:240]
                    if _web_fallback_used:
                        _snippets = []
                        for _item in _web_fallback.get('results', [])[:6]:
                            _title = str(_item.get('title', '')).strip()
                            _snippet = str(_item.get('snippet', '')).strip()
                            _url = str(_item.get('url', '')).strip()
                            _snippets.append(f'- {_title}: {_snippet} ({_url})')
                        _ai_answer = '[SCP public-web evidence; untrusted, requires verification]\n' + '\n'.join(_snippets)
                        v98_context['web_fallback'] = _web_fallback
                    else:
                        logger.warning('[CHATBOT] Public web fallback returned no result: %s', _web_fallback.get('errors'))
                except Exception as _web_err:
                    _web_fallback = {'success': False, 'method': 'public-search', 'error': str(_web_err)[:240]}
                    logger.warning('[CHATBOT] Public web fallback failed: %s', _web_err)
    _q_lower = req.question.lower() if req.question else ''
    _FACT_CHECK_KEYWORDS = ('true or false', 'fact check', 'is it true', 'fact-check', 'có thật', 'đúng không', 'có thật không', 'kiểm chứng', 'real or fake', 'verify this claim')
    if any((kw in _q_lower for kw in _FACT_CHECK_KEYWORDS)):
        try:
            from scp.core.multi_source_verifier import AsyncMultiSourceVerifier
            from scp.data_sources import get_registry
            _fc_sources = []
            try:
                _registry = get_registry()
                _candidates = []
                try:
                    _candidates = _registry.get_sources_for_intent('fact_check') or []
                except Exception:
                    _candidates = list(getattr(_registry, '_sources', {}).values())
                for _src in _candidates:
                    try:
                        if _src.can_handle('fact_check'):
                            _fc_sources.append(_src)
                    except Exception:
                        continue
            except Exception as _reg_err:
                logger.debug(f'[OPT-22] registry lookup failed: {_reg_err}')
            async_verifier = AsyncMultiSourceVerifier()
            fact_result = await async_verifier.verify_async(req.question, sources=_fc_sources or None)
            _extra_verified = 0
            _extra_contradicted = 0
            for _raw in fact_result.get('results', []) or []:
                try:
                    _meta = _raw.get('metadata', {}) if isinstance(_raw, dict) else {}
                    _verdict = str(_meta.get('consensus', '')).upper() if _meta else ''
                    if _verdict == 'FALSE':
                        _extra_contradicted += 1
                    elif _verdict == 'TRUE':
                        _extra_verified += 1
                except Exception:
                    continue
            if _extra_verified or _extra_contradicted:
                fact_result['verified'] = fact_result.get('verified', 0) + _extra_verified
                fact_result['contradicted'] = fact_result.get('contradicted', 0) + _extra_contradicted
                if fact_result['contradicted'] > fact_result['verified']:
                    fact_result['consensus'] = 'contradicted'
                elif fact_result['verified'] > fact_result['contradicted']:
                    fact_result['consensus'] = 'verified'
            if fact_result.get('consensus') == 'contradicted':
                logger.info(f"[OPT-22] Pre-judge fact check: claim contradicted by {fact_result.get('contradicted', 0)} sources (sources_checked={fact_result.get('sources_checked', 0)})")
                v98_context['fact_check_hint'] = fact_result
            elif fact_result.get('consensus') == 'verified':
                logger.info(f"[OPT-22] Pre-judge fact check: claim verified by {fact_result.get('verified', 0)} sources (sources_checked={fact_result.get('sources_checked', 0)})")
                v98_context['fact_check_hint'] = fact_result
        except Exception as e:
            logger.debug(f'[OPT-22] async fact check failed: {e}')
    stage_request(request, 'verifier_started')
    from scp.core.top_systems_learning import inspect_untrusted as _sf_inspect
    _raw_evidence = [str(c) for c in req.contexts or [] if str(c).strip()] + ([str(req.retrieved_context).strip()] if str(getattr(req, 'retrieved_context', '') or '').strip() else [])
    _clean_evidence = []
    _injection_blocked = 0
    for _ev in _raw_evidence:
        _quarantined, _reason = _sf_inspect(_ev)
        if _quarantined:
            _injection_blocked += 1
            logger.warning('[SEMANTIC-FIREWALL] Blocked injection in evidence: %s', _reason)
            continue
        _clean_evidence.append(_ev)
    if _injection_blocked:
        v98_context['semantic_firewall'] = {'blocked': _injection_blocked, 'total': len(_raw_evidence)}
    _evidence_context = ' '.join(_clean_evidence)
    if hasattr(judge, 'judge_with_react_fallback'):
        v = await judge.judge_with_react_fallback(question=req.question, ai_answer=_ai_answer, cycle_count=0, source=req.source, context=_evidence_context, v98_context=v98_context)
    else:
        v = await asyncio.to_thread(judge.judge, question=req.question, ai_answer=_ai_answer, cycle_count=0, source=req.source, context=_evidence_context, v98_context=v98_context)

    class DotDict(dict):

        def __getattr__(self, name):
            return self.get(name, None)

        def __setattr__(self, name, value):
            self[name] = value
    if isinstance(v, dict):
        if v.get('evidence') is None:
            v['evidence'] = {}
        if v.get('slm_responses') is None:
            v['slm_responses'] = []
        if v.get('confidence') is None:
            v['confidence'] = 0.0
        if v.get('final_answer') is None:
            v['final_answer'] = v.get('evidence', {}).get('final_answer', '')
        v = DotDict(v)
    stage_request(request, 'verifier_completed', verdict=getattr(v, 'verdict', 'FAIL'), governance_decision=getattr(v, 'evidence', {}).get('governance_decision', ''))
    if hasattr(judge, 'dos_protection') and judge.dos_protection:
        try:
            judge.dos_protection.record_verdict(getattr(v, 'verdict', 'FAIL'))
        except Exception as e:
            logger.debug(f'[V104.41 #AC] DoS record_verdict error: {e}')
    elapsed_ms = (time.time() - t0) * 1000
    if hasattr(judge, 'response_monitor') and judge.response_monitor:
        try:
            judge.response_monitor.observe(prompt=req.question, response=v.final_answer or '', latency_ms=elapsed_ms)
        except Exception as e:
            logger.debug(f'[V104.41 #AD] ResponseMonitor observe error: {e}')
    slm_trace = []
    for r in v.slm_responses:
        slm_trace.append({'domain': r.get('domain', '?'), 'slm_name': r.get('slm_name', r.get('domain', '?')), 'answer': str(r.get('answer', ''))[:200], 'confidence': r.get('confidence', 0), 'source': r.get('evidence', {}).get('source', '?') if isinstance(r.get('evidence'), dict) else '?', 'evidence': r.get('evidence', {}) if isinstance(r.get('evidence'), dict) else {}, 'processing_time_ms': r.get('processing_time', 0)})
    phase_timings = v.evidence.get('v100_phase_timings', {})
    mt_result = None
    _mt_session = req.session_id or v98_context.get('session_id', '')
    if _mt_session:
        mt_result = _multi_turn_tracker.track(_mt_session, req.question, v.verdict)
        if mt_result.suspicious:
            if v.verdict in ('PASS', 'FAIL', 'UNKNOWN', 'PARTIAL'):
                v.verdict = 'FLAGGED'
                v.confidence *= 0.5
                if v.reasoning:
                    v.reasoning += f' [V104 Multi-turn: {mt_result.pattern_type}]'
            logger.warning(f'V104 Multi-turn attack: session={_mt_session}, pattern={mt_result.pattern_type}, reason={mt_result.reason}')
            v98_context['v104_multi_turn'] = mt_result.__dict__
    has_attack = bool(v98_context.get('v99_vietnamese_attack'))
    has_bypass = bool(v.evidence.get('v100_bypass_detected'))
    has_human_review = bool(v.evidence.get('v102_human_review_pending'))
    source_count = len([r for r in v.slm_responses if r.get('answer')])
    _simple_explainer.explain(verdict=v.verdict, confidence=v.confidence, domain=v.domain or '' or '' or '', sources=source_count, has_attack=has_attack, has_bypass=has_bypass, has_human_review=has_human_review, lineage_overlap=0.0, reliability_factor=v.evidence.get('v102_reliability_factor', 1.0))
    _api_final_answer = v.final_answer
    _gov_decision = v.evidence.get('governance_decision', '')
    _api_slm_responses = [{k: str(v2)[:200] for k, v2 in r.items()} for r in v.slm_responses]
    _api_slm_trace = slm_trace
    _api_reasoning = v.reasoning[:500] if v.reasoning else None
    _api_v100_claims = v.evidence.get('v100_claims')
    _api_v103_antibodies = v.evidence.get('v103_antibodies')
    _api_speculative_mode = v.evidence.get('speculative_mode')
    _api_v98_canary_token = v.evidence.get('v98_canary_token')
    _api_v98_guard = v.evidence.get('v98_guard_verdict') or v.evidence.get('v98_guard')
    _api_v98_classification = v.evidence.get('v98_classification')
    _api_v98_attack_policy = v.evidence.get('v98_attack_policy')
    _api_v98_counter_executed = v.evidence.get('v98_counter_executed')
    _api_v98_bypass_recorded = v.evidence.get('v98_bypass_recorded')
    _api_falsification_status = v.evidence.get('falsification_status')
    if _gov_decision == 'KILL' or v.verdict in ('FAIL', 'FLAGGED'):
        _api_final_answer = f'[SCP: Answer withheld — verdict: {v.verdict}]'
        if _gov_decision == 'KILL':
            _api_final_answer = '[SCP: Answer withheld — Governance KILL]'
        _api_slm_responses = []
        _api_slm_trace = []
        _api_reasoning = '[SCP: Answer withheld]'
        _api_v100_claims = None
        _api_v103_antibodies = None
        _api_speculative_mode = None
        _api_v98_canary_token = None
        _api_v98_guard = None
        _api_v98_classification = None
        _api_v98_attack_policy = None
        _api_v98_counter_executed = None
        _api_v98_bypass_recorded = None
        _api_falsification_status = None
        logger.info(f'[V104.41 #X] API boundary enforcing abstain (all fields cleared): verdict={v.verdict}, gov={_gov_decision}')
    elif v.verdict == 'UNKNOWN' and v.evidence.get('why_gate', {}).get('decision') == 'REJECT':
        _api_final_answer = '[SCP: Answer withheld — WHY Gate blocked]'
        _api_slm_responses = []
        _api_slm_trace = []
        _api_reasoning = '[SCP: WHY Gate blocked]'
        _api_v100_claims = None
        _api_v103_antibodies = None
        _api_speculative_mode = None
        _api_v98_canary_token = None
        _api_v98_guard = None
        _api_v98_classification = None
        _api_v98_attack_policy = None
        _api_v98_counter_executed = None
        _api_v98_bypass_recorded = None
        _api_falsification_status = None
        logger.info(f'[FIX-1] API boundary enforcing WHY Gate block (all fields cleared): verdict={v.verdict}')
    elif v.verdict == 'UNKNOWN':
        if _api_final_answer and '[SCP: unverified]' not in _api_final_answer:
            _sources = []
            for r in v.slm_responses:
                if r.get('answer'):
                    _sources.append(f"  • {r.get('slm_name', '?')}: {str(r.get('answer', ''))[:60]}")
            _source_text = '\n'.join(_sources) if _sources else '  (không có SLM nào trả lời)'
            _api_final_answer = str(_api_final_answer) + str(f'\n\nSCP đã kiểm tra:\n{_source_text}\nĐộ tin cậy: {v.confidence:.0%} — chưa đạt ngưỡng (cần ≥70%)')
    if v.verdict == 'PASS' and _api_final_answer and (len(_api_final_answer) > 20):
        try:
            _fc_task = asyncio.create_task(_async_fact_check(_api_final_answer, req.question, v98_context.get('session_id', '')))
            _async_factcheck_tasks.add(_fc_task)
            _fc_task.add_done_callback(_async_factcheck_tasks.discard)
        except Exception as e:
            logger.debug(f'[V104.37] api_server.py: e={e}')
    stage_request(request, 'response_boundary', verdict=v.verdict, governance_decision=_gov_decision)
    if _web_fallback_used:
        _api_slm_trace.append({'domain': v.domain or '' or '', 'slm_name': 'public_web_search', 'answer': 'retrieved public snippets', 'time_ms': None, 'source': 'public-search', 'evidence': _web_fallback})
    return AskResponse(verdict=v.verdict, final_answer=_api_final_answer, confidence=v.confidence, domain=v.domain or '' or '', falsification_status=_api_falsification_status, governance_decision=v.evidence.get('governance_decision'), v98_guard=_api_v98_guard, v98_classification=_api_v98_classification, v98_attack_policy=_api_v98_attack_policy, v98_counter_executed=_api_v98_counter_executed, v98_canary_token=_api_v98_canary_token, v98_bypass_recorded=_api_v98_bypass_recorded, elapsed_ms=round(elapsed_ms, 1), session_id=v98_context['session_id'], slm_trace=_api_slm_trace, phase_timings=phase_timings, reasoning=_api_reasoning, slm_responses=_api_slm_responses, v100_claims=_api_v100_claims, v103_antibodies=_api_v103_antibodies, speculative_mode=_api_speculative_mode, web_fallback_used=_web_fallback_used, web_fallback=_web_fallback or None)
