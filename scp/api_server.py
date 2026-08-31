"""
SCP V99 │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d API Server
Copyright (c) 2026 Minh. MIT License.

FastAPI server exposing V98 pipeline qua HTTP.

Endpoints:
  POST /ask                          │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d Main: question → V98 pipeline → verdict
  POST /v1/chat/completions          │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d OpenAI-compatible (for PyRIT/garak)
  GET  /v1/models                    │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d OpenAI models list
  POST /v98/analyze-session          │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d Rogue AI detection on session
  POST /v98/run-simulation           │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d Trigger threat simulation
  POST /v98/run-intel-crawl          │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d Trigger threat intel crawl
  GET  /v98/status                   │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d All V98 module status
  GET  /v98/counter/stats            │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d Counter response stats
  GET  /v98/canary/triggers          │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d Canary token triggers
  GET  /v98/error-store/stats        │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d ErrorStore stats
  GET  /dashboard                    │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d HTML dashboard
  GET  /health                       │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d Health check
  GET  /                             │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d Root info
"""
from __future__ import annotations

from .api_server_parts._scp_service_identity import _scp_service_identity
from .api_server_parts.lifespan import lifespan
from .api_server_parts._ask_impl import _ask_impl
from .api_server_parts._async_fact_check import _async_fact_check
from .api_server_parts.health_detailed import health_detailed
from scp.security.env_loader import load_selected_env
load_selected_env()
from fastapi import Depends
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Histogram
from fastapi.responses import Response
from scp.security.jwt_guard import get_current_user
from scp.observability.telemetry import setup_telemetry
REQUEST_COUNT = Counter('scp_request_count', 'Total SCP Requests', ['method', 'endpoint'])
REQUEST_LATENCY = Histogram('scp_request_latency_seconds', 'Request latency', ['endpoint'])
import asyncio
import base64
import binascii
import logging
import os
import threading
from typing import Any
_CACHED_COMMIT: str | None = None
_CACHED_CONFIG_HASH: str | None = None
import time
from collections import deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
logger = logging.getLogger('scp.api')
from scp.web_control.internet_search import InternetSearch
from scp.api_server_parts.helpers import AskRequest, AskResponse, _extract_v98_context, _safe_fetch_url, get_judge
from scp.core.request_run_ledger import RequestRunLedger, stage_request, traced_request
_REQUEST_RUN_LEDGER = RequestRunLedger()
_ASK_KERNEL_ADAPTERS: dict[tuple[str, str], Any] = {}
_ASK_KERNEL_ADAPTER_LOCK = threading.Lock()
_ASK_KERNEL_INIT_ERROR: Exception | None = None

def _ask_is_context_rag(req: AskRequest) -> bool:
    return bool(getattr(req, 'rag_enabled', False) or getattr(req, 'contexts', None) or str(getattr(req, 'retrieved_context', '') or '').strip())

def _ask_kernel_enabled(req: AskRequest) -> bool:
    """Return true only when the durable RAG kernel is explicitly enabled."""
    return os.environ.get('SCP_ASK_KERNEL_ENABLED', '1') == '1'

def _get_ask_kernel_adapter() -> Any:
    """Get the durable adapter for the configured process-local paths."""
    global _ASK_KERNEL_INIT_ERROR
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.environ.get('SCP_KERNEL_DB_PATH', os.path.join(root, 'data', 'ask_task_kernel.sqlite3'))
    trace_path = os.environ.get('SCP_KERNEL_TRACE_PATH', os.path.join(root, 'data', 'ask_task_kernel_trace.jsonl'))
    key = (db_path, trace_path)
    with _ASK_KERNEL_ADAPTER_LOCK:
        if key in _ASK_KERNEL_ADAPTERS:
            return _ASK_KERNEL_ADAPTERS[key]
        try:
            from scp.ask_kernel_adapter import AskKernelAdapter
            adapter = AskKernelAdapter(db_path, trace_path)
            _ASK_KERNEL_ADAPTERS[key] = adapter
            return adapter
        except Exception as exc:
            _ASK_KERNEL_INIT_ERROR = exc
            logger.error('[ASK-KERNEL] durable adapter initialization failed: %s', type(exc).__name__)
            return None

def _kernel_gate_unavailable_response(req: AskRequest, exc: Exception) -> AskResponse:
    return AskResponse(verdict='FAIL', final_answer='[SCP: Answer withheld — Kernel gate unavailable]', confidence=0.0, domain=req.domain_override or req.domain or 'general', falsification_status='KERNEL_GATE_UNAVAILABLE', governance_decision='KILL', v98_guard={'mode': 'rag-verified', 'readOnly': True, 'security_blocked': True, 'kernel_error': type(exc).__name__}, v98_classification={'provenance': 'kernel_gate', 'evidence_count': 0}, elapsed_ms=0.0, session_id=req.session_id or 'ask-kernel-unavailable', run_status='REJECTED', ledger_status='BLOCKED')
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(name)s | %(message)s')
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
if TYPE_CHECKING:
    from scp.prediction.predictive import PredictiveOrchestrator as PredictiveEngine
try:
    from scp.api.chat import router as chat_router
    _CHAT_AVAILABLE = True
except ImportError as e:
    logger.warning(f'V104.48 Chat router unavailable: {e}')
    _CHAT_AVAILABLE = False
_V98_V100_ROUTERS_AVAILABLE = False
v98_admin_router = None
v100_admin_router = None
from scp.core.real_learning_engine import RealLearningEngine
try:
    from scp.core.fast_learning_engine import FastLearningEngine, start_fast_learning_thread
    _V1042_AVAILABLE = True
except ImportError as e:
    logger.warning(f'V104.2 FastLearningEngine unavailable: {e}')
    _V1042_AVAILABLE = False
try:
    from scp.core.startup_optimizer import STARTUP_DEFER_SECONDS, cleanup_data_directory, deferred_background_start, get_data_directory_stats, run_startup_optimization
    _V1043_AVAILABLE = True
except ImportError as e:
    logger.warning(f'V104.3 StartupOptimizer unavailable: {e}')
    _V1043_AVAILABLE = False
try:
    from scp.core.data_partitioner import DOMAIN_KEYWORDS, DOMAIN_TABLES, TTL_QUESTION_LOG, TTL_VERDICT_CACHE, TTL_VERDICT_CACHE_DB, BypassLessonsStore, DataPartitioner, ThreeTierCache, TTLExpirer, detect_domain, migrate_old_to_new
    _V1044_AVAILABLE = True
except ImportError as e:
    logger.warning(f'V104.4 DataPartitioner unavailable: {e}')
    _V1044_AVAILABLE = False
_judge: RealityJudge | None = None
_judge_lock = threading.Lock()
_background_task: asyncio.Task | None = None
_attack_crawler: AttackCrawler | None = None
_multi_turn_tracker = MultiTurnTracker()
_image_detector = ImageJailbreakDetector()
_voice_detector = VoiceJailbreakDetector()
_cross_language_learner = CrossLanguageLearner()
_fact_checker = StreamingFactChecker()
_simple_explainer = SimpleExplainer()
_real_learning = RealLearningEngine(scp_db_path='data/v13.db', data_dir='data')
_fast_learning: FastLearningEngine | None = None
if _V1042_AVAILABLE:
    _fast_learning = FastLearningEngine(scp_db_path='data/v13.db', data_dir='data')
_predictive_engine: PredictiveEngine | None = None
_async_factcheck_tasks: set = set()

class SimulationRequest(BaseModel):
    count: int = Field(50, ge=1, le=500)
try:
    from scp.api.routes.admin_v98 import router as v98_admin_router
    from scp.api.routes.admin_v100 import router as v100_admin_router
    _V98_V100_ROUTERS_AVAILABLE = True
except ImportError as e:
    logger.warning(f'[Task 7-A] V98/V100 admin routers unavailable: {e}')
    _V98_V100_ROUTERS_AVAILABLE = False
try:
    from scp.api.dashboard_html import DASHBOARD_HTML
except ImportError as e:
    logger.warning(f'[Task 8-A] dashboard_html unavailable: {e}')
    DASHBOARD_HTML = '<html><body>Dashboard unavailable</body></html>'
_EXTRA_ROUTERS_AVAILABLE = False
from scp.api.route_profile import resolve_api_profile, route_group_enabled
_API_PROFILE = resolve_api_profile()

def _route_enabled(group: str) -> bool:
    return route_group_enabled(group, _API_PROFILE)
app = FastAPI(title=f'{RELEASE_LABEL} - Self-Correcting Pipeline API', description=f'{DOMAIN_EXPERT_ENSEMBLE_TERM} + FalsificationEngine + Governance + Chat + Evolution', version=_SCP_VERSION, lifespan=lifespan)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
try:
    setup_telemetry(app)
except Exception as e:
    logger.warning(f'Telemetry setup skipped: {e}')

@app.get('/metrics')
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
_cors_origins_raw = os.environ.get('SCP_CORS_ORIGINS', 'http://localhost:3000')
_cors_origins = [o.strip() for o in _cors_origins_raw.split(',') if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins or ['http://localhost:3000'], allow_methods=['GET', 'POST', 'DELETE'], allow_headers=['Authorization', 'Content-Type'], allow_credentials=False)
try:
    from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
    if os.environ.get('SCP_FORCE_HTTPS', '0') == '1':
        app.add_middleware(HTTPSRedirectMiddleware)
        logger.info('[Security] HTTPS redirect enabled (SCP_FORCE_HTTPS=1)')
    else:
        _bind_host = os.environ.get('SCP_HOST', '127.0.0.1')
        if _bind_host not in ('127.0.0.1', 'localhost', '::1'):
            logger.warning(f'[Security] │Ă‚Â\x9aĂ‚Â\xa0Ä‚Â¯Ă‚Â¸Ă‚Â\x8f  PRODUCTION DEPLOYMENT without HTTPS! Host={_bind_host} │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d set SCP_FORCE_HTTPS=1 or use a TLS-terminating reverse proxy. Without HTTPS, auth tokens travel in plaintext.')
        else:
            logger.info('[Security] HTTPS redirect disabled (set SCP_FORCE_HTTPS=1 in prod)')
except ImportError:
    logger.debug('[Security] HTTPSRedirectMiddleware unavailable (older FastAPI)')
logger.info('[Security] CSRF protection: Bearer token auth (attacker cannot forge Authorization header)')
if _CHAT_AVAILABLE and _route_enabled('chat'):
    app.include_router(chat_router, tags=['chat'])
if _V98_V100_ROUTERS_AVAILABLE and _route_enabled('versioned_admin'):
    app.include_router(v98_admin_router)
    app.include_router(v100_admin_router)
try:
    from scp.api.routes.import_routes import router as import_router
    from scp.api.routes.openai_compat import router as openai_compat_router
    from scp.api.routes.v102_v103_routes import router as v102_v103_router
    from scp.api.routes.v104_routes import router as v104_router
    from scp.api.routes.v105_routes import router as v105_router
    _EXTRA_ROUTERS_AVAILABLE = True
except ImportError as e:
    logger.warning(f'[Task 9-B] V102-V105/import routers unavailable: {e}')
    _EXTRA_ROUTERS_AVAILABLE = False
if _EXTRA_ROUTERS_AVAILABLE:
    if _route_enabled('openai_compat'):
        app.include_router(openai_compat_router)
    if _route_enabled('versioned_admin'):
        app.include_router(v102_v103_router)
        app.include_router(v104_router)
        app.include_router(v105_router)
    if _route_enabled('import'):
        app.include_router(import_router)
try:
    from scp.api.routes.control_routes import router as control_router
    if _route_enabled('control'):
        app.include_router(control_router, tags=['control'])
        _CONTROL_ROUTES_AVAILABLE = True
    else:
        _CONTROL_ROUTES_AVAILABLE = False
except ImportError as e:
    logger.warning(f'[SCP Control] Control router unavailable: {e}')
    _CONTROL_ROUTES_AVAILABLE = False
try:
    from scp.api.routes.stream_routes import router as stream_router
    if _route_enabled('stream'):
        app.include_router(stream_router, tags=['stream'])
except ImportError as _e:
    logger.warning(f' stream_routes router unavailable: {_e}')
try:
    from scp.api.routes.threat_routes import router as threat_router
    if _route_enabled('threat'):
        app.include_router(threat_router, tags=['threats'])
except ImportError as _e:
    logger.warning(f' threat_routes router unavailable: {_e}')
try:
    from scp.api.routes.audit_routes import router as audit_router
    if _route_enabled('audit'):
        app.include_router(audit_router, tags=['audit'])
except ImportError as _e:
    logger.warning(f' audit_routes router unavailable: {_e}')
try:
    from scp.api.routes.prediction_routes import router as prediction_router
    if _route_enabled('prediction'):
        app.include_router(prediction_router, tags=['predictions'])
except ImportError as _e:
    logger.warning(f' prediction_routes router unavailable: {_e}')
try:
    from scp.api.webhook import router as webhook_router
    if _route_enabled('webhook'):
        app.include_router(webhook_router)
        _WEBHOOK_ROUTER_AVAILABLE = True
    else:
        _WEBHOOK_ROUTER_AVAILABLE = False
except ImportError as e:
    logger.warning(f'[Task 42-B] Webhook router unavailable: {e}')
    _WEBHOOK_ROUTER_AVAILABLE = False
try:
    from scp.api.routes.pc_controller_routes import router as pc_controller_router
    if _route_enabled('pc_controller'):
        app.include_router(pc_controller_router)
        _PC_CONTROLLER_AVAILABLE = True
    else:
        _PC_CONTROLLER_AVAILABLE = False
except ImportError as e:
    logger.warning(f'[V3.1] PC Controller router unavailable: {e}')
    _PC_CONTROLLER_AVAILABLE = False
try:
    from scp.api.routes.web_control_routes import router as web_control_router
    if _route_enabled('web_control'):
        app.include_router(web_control_router)
        _WEB_CONTROL_AVAILABLE = True
    else:
        _WEB_CONTROL_AVAILABLE = False
except ImportError as e:
    logger.warning(f'[V3.1] Web control router unavailable: {e}')
    _WEB_CONTROL_AVAILABLE = False
from pydantic import BaseModel

class TokenRequest(BaseModel):
    admin_key: str

@app.post('/auth/token')
@limiter.limit('5/minute')
def login_for_access_token(req: TokenRequest, request: Request):
    expected_key = os.environ.get('SCP_ADMIN_KEY', 'admin')
    import secrets as _secrets
    if not _secrets.compare_digest(req.admin_key.encode(), expected_key.encode()):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail='Incorrect admin key')
    from scp.security.jwt_guard import create_access_token
    access_token = create_access_token(data={'sub': 'admin'})
    return {'access_token': access_token, 'token_type': 'bearer'}

@app.post('/ask', response_model=AskResponse)
@limiter.limit('60/minute')
@traced_request(_REQUEST_RUN_LEDGER)
async def ask(req: AskRequest, request: Request, current_user: str=Depends(get_current_user)):
    REQUEST_COUNT.labels(method='POST', endpoint='/ask').inc()
    if not _ask_kernel_enabled(req):
        return _kernel_gate_unavailable_response(req, RuntimeError('rag_kernel_disabled'))
    adapter = _get_ask_kernel_adapter()
    if adapter is None:
        return _kernel_gate_unavailable_response(req, _ASK_KERNEL_INIT_ERROR or RuntimeError('kernel_adapter_unavailable'))
    return await adapter.run_rag(req, request, _ask_impl)
_fact_check_retract_queue: deque[dict] = deque(maxlen=1000)

@app.get('/dashboard', response_class=HTMLResponse)
async def dashboard():
    """HTML dashboard │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d real-time V98 stats."""
    return HTMLResponse(DASHBOARD_HTML)

@app.get('/health')
async def health():
    return {'status': 'ok', 'service_identity': _scp_service_identity(), 'version': _SCP_VERSION, 'release': public_release_metadata(), 'routes': len(app.routes), 'modules': '136+ Python files', 'note': 'minimal health — use /health/detailed for full status'}

@app.get('/ready')
@app.get('/readiness')
async def readiness():
    """Report whether the API can serve judge-backed requests.

    ``/health`` is liveness and may return 200 while initialization is still
    running.  These aliases are readiness probes and return 503 until the
    background judge initialization has completed.
    """
    judge_ready = bool(getattr(app.state, 'judge_ready', False))
    scheduler_started = bool(getattr(app.state, 'background_scheduler_started', False))
    payload = {'status': 'ready' if judge_ready else 'initializing', 'service': 'scp-api', 'version': _SCP_VERSION, 'checks': {'judge': 'ok' if judge_ready else 'pending', 'background_scheduler': 'ok' if scheduler_started else 'pending'}, 'reason': getattr(app.state, 'readiness_reason', None)}
    return JSONResponse(payload, status_code=200 if judge_ready else 503)

@app.get('/')
async def root():
    return {'name': 'SCP', 'version': _SCP_VERSION, 'description': 'Self-Correcting Pipeline with V98 security', 'endpoints': ['POST /ask', 'POST /v1/chat/completions', 'GET  /v1/models', 'POST /v98/analyze-session', 'POST /v98/run-simulation', 'POST /v98/run-intel-crawl', 'GET  /v98/status', 'GET  /v98/counter/stats', 'GET  /v98/canary/triggers', 'GET  /v98/error-store/stats', 'GET  /v98/attack-memory/stats', 'GET  /dashboard', 'GET  /health']}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run('scp.api_server:app', host='127.0.0.1', port=8000, reload=False, log_level='info')
try:
    from scp.api.routes.hands_routes import router as hands_router
    if _route_enabled('hands'):
        app.include_router(hands_router)
    from scp.api.routes.batch_benchmark_routes import router as batch_benchmark_router
    if _route_enabled('batch_benchmark'):
        app.include_router(batch_benchmark_router)
    _HANDS_AVAILABLE = _route_enabled('hands')
except ImportError as e:
    logger.warning(f'[SCP Hands v3.2] Hands router unavailable: {e}')
    _HANDS_AVAILABLE = False
try:
    from scp.api.routes.agent_routes import router as agent_router
    if _route_enabled('agent'):
        app.include_router(agent_router)
        _AGENT_ORCHESTRATOR_AVAILABLE = True
    else:
        _AGENT_ORCHESTRATOR_AVAILABLE = False
except ImportError as e:
    logger.warning(f'[SCP Agent] Agent orchestrator router unavailable: {e}')
    _AGENT_ORCHESTRATOR_AVAILABLE = False
try:
    from scp.api.routes.call_routes import router as call_router
    if _route_enabled('call'):
        app.include_router(call_router)
        _CALL_SIGNALING_AVAILABLE = True
    else:
        _CALL_SIGNALING_AVAILABLE = False
except ImportError as e:
    logger.warning(f'[SCP Call] Call signaling router unavailable: {e}')
    _CALL_SIGNALING_AVAILABLE = False
try:
    from scp.observability.otel import configure_fastapi_otel
    _OTEL_STATUS = configure_fastapi_otel(app)
    if _OTEL_STATUS.get('enabled'):
        logger.info('[OTel] FastAPI tracing enabled without request-body/header capture')
    else:
        logger.info('[OTel] tracing disabled: %s', _OTEL_STATUS.get('reason', 'not configured'))
except Exception as e:
    _OTEL_STATUS = {'enabled': False, 'reason': type(e).__name__}
    logger.warning('[OTel] optional instrumentation unavailable: %s', type(e).__name__)
