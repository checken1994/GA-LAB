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

@app.get('/health/detailed')
async def health_detailed():
    """Detailed health check │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d calls get_judge() (may be slow if init in progress)."""
    try:
        judge = get_judge()
        import os as _os
        data_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), 'data')
        db_size = 0
        if _os.path.exists(data_dir):
            for f in _os.listdir(data_dir):
                fp = _os.path.join(data_dir, f)
                if _os.path.isfile(fp):
                    db_size += _os.path.getsize(fp)
        _sched_started = getattr(app.state, 'background_scheduler_started', False)
        from scp.security.os_sandbox import isolation_capability
        return {'status': 'ok', 'version': _SCP_VERSION, 'release': public_release_metadata(), 'domain_experts': len(judge.domain_experts), 'slms': len(judge.domain_experts), 'v98_modules': sum((1 for v in judge.get_v98_status().values() if v != 'inactive')), 'routes': len(app.routes), 'modules': '136+ Python files', 'data_size_mb': round(db_size / (1024 * 1024), 2), 'multi_turn_tracker': _multi_turn_tracker.stats(), 'cross_language': _cross_language_learner.stats(), 'fact_checker': _fact_checker.stats(), 'sandbox_capability': isolation_capability(), 'runtime_routing': {'math_probe_route': list(judge._route_question('2+2')), 'domain_expert_loaded': 'math' in judge.domain_experts, 'math_slm_loaded': 'math' in getattr(judge, 'domain_experts', {})}, 'background_scheduler_started': _sched_started}
    except Exception as e:
        _sched_started = getattr(app.state, 'background_scheduler_started', False)
        return {'status': 'initializing', 'version': _SCP_VERSION, 'routes': len(app.routes), 'error': str(e)[:200], 'background_scheduler_started': _sched_started, 'note': 'judge init in progress │Ă¢â€\x9aÂ¬Ă¢â‚¬Â\x9d /health returns ok, /ask may be slow'}
