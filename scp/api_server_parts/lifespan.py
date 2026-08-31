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

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _background_task
    logger.info('=' * 60)
    logger.info(f'{RELEASE_LABEL} API Server starting...')
    logger.info('=' * 60)
    app.state.judge_ready = False
    app.state.startup_status = 'starting'
    app.state.readiness_reason = 'judge_initialization_pending'
    _orig_why_llm = os.environ.get('SCP_WHY_LLM_ENABLED', '0')
    _orig_evo_auto = os.environ.get('SCP_EVOLUTION_AUTO', '0')
    os.environ['SCP_WHY_LLM_ENABLED'] = '0'
    os.environ['SCP_EVOLUTION_AUTO'] = '0'

    async def _startup_gate_background():
        """Run bounded AST startup scan without blocking socket readiness."""
        await asyncio.sleep(max(0.0, float(os.environ.get('SCP_STARTUP_BACKGROUND_DELAY_SEC', '5'))))
        if os.environ.get('SCP_SKIP_STARTUP_GATE', '0') == '1':
            logger.warning('[STARTUP-GATE] SCP_SKIP_STARTUP_GATE=1 — audit BYPASSED (dev/test mode)')
            return
        try:
            from scp.autofix.runner import ast_scan_scp
            timeout_sec = float(os.environ.get('SCP_STARTUP_SCAN_TIMEOUT_SEC', '15'))
            bugs = await asyncio.wait_for(asyncio.to_thread(ast_scan_scp, max_files=int(os.environ.get('SCP_MAX_STARTUP_FILES', '100')), include_enterprise=os.environ.get('SCP_STARTUP_SCAN_ENTERPRISE', '0') == '1'), timeout=max(1.0, timeout_sec))
            logger.info(f'[STARTUP-GATE] Background scan complete: {len(bugs)} bugs found')
        except asyncio.TimeoutError:
            logger.warning(f'[STARTUP-GATE] Background scan timed out after {timeout_sec}s (non-blocking)')
        except Exception as e:
            logger.warning(f'[STARTUP-GATE] Background scan failed (non-blocking): {e}')
    _startup_gate_task = asyncio.create_task(_startup_gate_background())
    import threading as _threading_r20

    def _init_judge_background_r20():
        """Init judge in background │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d /ask returns 503 until ready, /health returns 200.

        [SCP-DNA-FIX 4-a-001] TÄ‚Â¡Ă‚ÂºĂ‚Â\xa0I SAO: previously this thread function did
        two things that both failed silently:
          1. `asyncio.create_task(judge.schedule_background_jobs())` raised
             `RuntimeError: no running event loop` (thread is not async) →
             swallowed by `except Exception` → background scheduler never ran.
          2. `judge` was a LOCAL variable, never propagated back to module
             scope → the post-yield block referenced `judge` → NameError →
             swallowed → scheduler never ran from there either.
        Reality (DNA #26): ThreatSimulator (6h) + IntelCrawler (12h) NEVER ran.
        Fix: (a) remove the broken in-thread create_task, (b) set the
        module-level `_judge` so the lifespan post-yield block (which runs
        inside the running event loop) can schedule the job correctly.
        """
        global _judge
        try:
            judge = get_judge()
            _judge = judge
            app.state.judge_ready = True
            app.state.startup_status = 'ready'
            app.state.readiness_reason = None
            logger.info(f"[R20-ROOT-FIX-REAL] Judge ready: {len(getattr(judge, 'domain_experts', []))} SLMs")
            logger.info(f'[R20-ROOT-FIX-REAL] V98 status: {judge.get_v98_status()}')
        except Exception as e:
            app.state.judge_ready = False
            app.state.startup_status = 'failed'
            app.state.readiness_reason = 'judge_initialization_failed'
            logger.error(f'[R20-ROOT-FIX-REAL] Judge init FAILED: {e}')
            logger.error('[R20-ROOT-FIX-REAL] /ask will return 503 until judge is available')
    _judge_thread_r20 = _threading_r20.Thread(target=_init_judge_background_r20, name='scp-judge-init-r20', daemon=True)

    async def _launch_judge_deferred():
        await asyncio.sleep(max(0.0, float(os.environ.get('SCP_JUDGE_START_DELAY_SEC', '5'))))
        try:
            _judge_thread_r20.start()
        except RuntimeError as e:
            logger.warning(f'[R20-ROOT-FIX-REAL] Deferred judge launch skipped: {e}')
    _judge_launch_task = asyncio.create_task(_launch_judge_deferred())
    logger.info('[R20-ROOT-FIX-REAL] Judge init dispatched to background thread')
    logger.info('[R20-ROOT-FIX-REAL] Yielding NOW │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d port 8000 binds immediately')
    app.state.background_scheduler_started = False

    async def _start_background_scheduler():
        try:
            for _ in range(60):
                if _judge is not None:
                    break
                await asyncio.sleep(0.5)
            if _judge is not None:
                global _background_task

                def _run_scheduler_offloop():
                    asyncio.run(_judge.schedule_background_jobs())
                _background_task = asyncio.create_task(asyncio.to_thread(_run_scheduler_offloop))
                app.state.background_scheduler_started = True
                logger.info('Background scheduler started (ThreatSimulator 6h + IntelCrawler 12h)')
            else:
                app.state.background_scheduler_started = False
                logger.error('[4-a-001] Background scheduler NOT started: _judge is None after 30s')
        except asyncio.CancelledError:
            app.state.background_scheduler_started = False
            raise
        except Exception as e:
            app.state.background_scheduler_started = False
            logger.error(f'[4-a-001] Background scheduler failed: {e}', exc_info=True)
    _scheduler_bootstrap_task = asyncio.create_task(_start_background_scheduler())
    app.state.evolution_initialized = False

    async def _start_evolution_runtime():
        try:
            await asyncio.sleep(5)
            from scp.autofix.evolution import get_evolution_engine
            await asyncio.to_thread(get_evolution_engine, data_dir=os.environ.get('SCP_DATA_DIR', 'data'))
            app.state.evolution_initialized = True
            logger.info('[EVOLUTION] Runtime initialized; auto promotion remains env-gated')
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning('[EVOLUTION] Runtime initialization failed: %s', exc)
    _evolution_bootstrap_task = asyncio.create_task(_start_evolution_runtime())
    _audit_thread = None
    _attack_thread = None
    app.state.deep_audit_started = False
    app.state.attack_monitor_started = False
    try:
        import threading as _threading
        import time as _time
        from scp.autofix.runner import run_deep_audit
        from scp.core.subsystem_telemetry import SubsystemTelemetry, heartbeat_sleep
        _audit_telemetry = SubsystemTelemetry('deep_audit', os.environ.get('SCP_DATA_DIR', 'data'))
        _audit_telemetry.start(mode='background', config={'interval_seconds': 86400})
        _audit_telemetry.tick(status='IDLE')
        _audit_stop = _threading.Event()
        _audit_state = {'status': 'STARTING'}
        app.state.deep_audit_stop = _audit_stop

        def _deep_audit_heartbeat_loop():
            while not _audit_stop.is_set():
                try:
                    _audit_telemetry.tick(status=_audit_state['status'])
                except Exception as exc:
                    logger.warning('[AUTO] deep-audit heartbeat tick failed: %s', exc)
                if _audit_stop.wait(15):
                    return
        _threading.Thread(target=_deep_audit_heartbeat_loop, daemon=True, name='scp-deep-audit-heartbeat').start()

        def _deep_audit_loop():
            heartbeat_sleep(_audit_telemetry, 60, status='IDLE')
            while not _audit_stop.is_set():
                run_id = f'deep-audit-{_time.time_ns()}'
                _audit_state['status'] = 'RUNNING'
                _audit_telemetry.cycle_started(run_id, trigger='interval')
                try:
                    logger.info('[AUTO] Deep audit cycle starting...')
                    results = run_deep_audit(max_bugs=int(os.environ.get('SCP_MAX_AUDIT_BUGS', '100')))
                    logger.info('[AUTO] Deep audit: %s bugs processed, %s auto-fixed', results.get('processed', 0), results.get('fixed', 0))
                    _audit_telemetry.cycle_completed(run_id, 'SUCCESS', bugs_found=results.get('processed', 0), bugs_fixed=results.get('fixed', 0), stored=results.get('stored', 0))
                except TimeoutError as exc:
                    logger.warning('[AUTO] Deep audit timeout: %s', exc)
                    _audit_telemetry.cycle_failed(run_id, exc, status='TIMEOUT')
                except Exception as exc:
                    logger.warning('[AUTO] Deep audit failed: %s', exc)
                    _audit_telemetry.cycle_failed(run_id, exc, status='PROVIDER_FAILED')
                _audit_state['status'] = 'IDLE'
                heartbeat_sleep(_audit_telemetry, 86400, status='IDLE')
        _audit_thread = _threading.Thread(target=_deep_audit_loop, daemon=True, name='scp-deep-audit-scheduler')
        _audit_thread.start()
        app.state.deep_audit_started = True
        logger.info('[AUTO] Deep audit scheduler started before lifespan yield (24h interval)')
    except Exception as exc:
        logger.warning('[AUTO] Deep audit scheduler failed to start: %s', exc)
    try:
        from scp.autofix.engine import get_autofix_engine
        from scp.core.subsystem_telemetry import SubsystemTelemetry, heartbeat_sleep
        _attack_telemetry = SubsystemTelemetry('attack_monitor', os.environ.get('SCP_DATA_DIR', 'data'))
        _attack_telemetry.start(mode='background', config={'interval_seconds': 300})
        _attack_telemetry.tick(status='IDLE')
        _attack_stop = _threading.Event()
        _attack_state = {'status': 'STARTING'}
        app.state.attack_monitor_stop = _attack_stop

        def _attack_heartbeat_loop():
            while not _attack_stop.is_set():
                try:
                    _attack_telemetry.tick(status=_attack_state['status'])
                except Exception as exc:
                    logger.warning('[AUTO] attack-monitor heartbeat tick failed: %s', exc)
                if _attack_stop.wait(15):
                    return
        _threading.Thread(target=_attack_heartbeat_loop, daemon=True, name='scp-attack-monitor-heartbeat').start()

        def _attack_mode_monitor():
            heartbeat_sleep(_attack_telemetry, 120, status='IDLE')
            while not _attack_stop.is_set():
                run_id = f'attack-monitor-{_time.time_ns()}'
                _attack_state['status'] = 'RUNNING'
                _attack_telemetry.cycle_started(run_id, trigger='interval')
                try:
                    eng = get_autofix_engine()
                    notif = getattr(_judge, 'notifications', None)
                    cutoff = _time.time() - 600
                    kill_count = notif.count_recent_by_type('governance_kill', cutoff) if notif is not None else 0
                    if kill_count > 20 and (not eng.in_attack_mode):
                        eng.set_attack_mode(True)
                        logger.warning('[AUTO] Attack mode ENABLED â€” %s KILLs in 10min', kill_count)
                    elif kill_count < 5 and eng.in_attack_mode:
                        eng.set_attack_mode(False)
                        logger.info('[AUTO] Attack mode DISABLED â€” %s KILLs in 10min', kill_count)
                    _attack_telemetry.cycle_completed(run_id, 'SUCCESS', asked=kill_count, verified=1)
                except TimeoutError as exc:
                    logger.warning('[AUTO] Attack mode monitor timeout: %s', exc)
                    _attack_telemetry.cycle_failed(run_id, exc, status='TIMEOUT')
                except Exception as exc:
                    logger.warning('[AUTO] Attack mode monitor: %s', exc)
                    _attack_telemetry.cycle_failed(run_id, exc, status='PROVIDER_FAILED')
                _attack_state['status'] = 'IDLE'
                heartbeat_sleep(_attack_telemetry, 300, status='IDLE')
        _attack_thread = _threading.Thread(target=_attack_mode_monitor, daemon=True, name='scp-attack-mode-monitor')
        _attack_thread.start()
        app.state.attack_monitor_started = True
        logger.info('[AUTO] Attack mode monitor started before lifespan yield (5min interval)')
    except Exception as exc:
        logger.warning('[AUTO] Attack mode monitor failed to start: %s', exc)
    try:
        from scp.core.doubt_cron import get_doubt_cron
        _data_dir = os.environ.get('SCP_DATA_DIR', 'data')
        _kernel_db = os.path.join(_data_dir, 'ask_task_kernel.sqlite3')
        if os.path.exists(_kernel_db):
            from scp.task_kernel import TaskKernel
            _recovery_kernel = TaskKernel(_kernel_db)
            _recovery = _recovery_kernel.recover_on_boot()
            if _recovery['recovered']:
                logger.warning('[RECOVERY] Boot recovery: %d tasks recovered, %d corrupted', len(_recovery['recovered']), len(_recovery['corrupted']))
            _recovery_kernel.close()
    except Exception as exc:
        logger.warning('[RECOVERY] Boot recovery failed (non-fatal): %s', exc)
    try:
        from scp.core.doubt_cron import get_doubt_cron
        _doubt = get_doubt_cron(data_dir=os.environ.get('SCP_DATA_DIR', 'data'))
        _doubt.start()
        app.state.doubt_cron = _doubt
        logger.info('[DOUBT] Cronjob of Doubt started (interval=%ss)', _doubt.interval)
    except Exception as exc:
        logger.warning('[DOUBT] Cronjob of Doubt failed to start (non-fatal): %s', exc)
    yield
    app.state.judge_ready = False
    app.state.startup_status = 'stopping'
    app.state.readiness_reason = 'server_shutting_down'
    try:
        from scp.meta.external_trust import get_external_trust_root
        _et = get_external_trust_root('.')
        _et_result = _et.verify_external()
        if _et_result['passed']:
            logger.info('[GĂ„â€\x9aĂ‚Â\xa0 -\x9aĂ‚Â§8] External trust roots verified │Ă…â€œĂ¢â‚¬Â¦ (audit tests + CI/CD + constitution)')
        else:
            logger.warning(f"[GĂ„â€\x9aĂ‚Â\xa0 -\x9aĂ‚Â§8] External trust BROKEN │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d missing: {_et_result['missing']}, constitution_approved: {_et_result['constitution_approved']}. Server will start but external anchors are not intact.")
    except Exception as _et_err:
        logger.warning(f'[GĂ„â€\x9aĂ‚Â\xa0 -\x9aĂ‚Â§8] External trust verification failed: {_et_err}')
    os.environ['SCP_WHY_LLM_ENABLED'] = _orig_why_llm
    os.environ['SCP_EVOLUTION_AUTO'] = _orig_evo_auto
    logger.info(f'[STARTUP] WHY LLM + Evolution AUTO restored (why={_orig_why_llm}, evo={_orig_evo_auto})')
    for _stop_event in (getattr(app.state, 'deep_audit_stop', None), getattr(app.state, 'attack_monitor_stop', None)):
        if _stop_event is not None:
            _stop_event.set()
    for _task in (_scheduler_bootstrap_task, _evolution_bootstrap_task, _background_task, _startup_gate_task, _judge_launch_task):
        if _task is not None and (not _task.done()):
            _task.cancel()
    try:
        from scp.core.doubt_cron import get_doubt_cron
        get_doubt_cron(data_dir=os.environ.get('SCP_DATA_DIR', 'data')).stop()
    except Exception:
        pass
    logger.info(f'{RELEASE_LABEL} API Server shutting down...')
