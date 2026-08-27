"""
SCP V99 Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â API Server
Copyright (c) 2026 Minh. MIT License.

FastAPI server exposing V98 pipeline qua HTTP.

Endpoints:
  POST /ask                          Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Main: question Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ V98 pipeline Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ verdict
  POST /v1/chat/completions          Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â OpenAI-compatible (for PyRIT/garak)
  GET  /v1/models                    Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â OpenAI models list
  POST /v98/analyze-session          Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Rogue AI detection on session
  POST /v98/run-simulation           Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Trigger threat simulation
  POST /v98/run-intel-crawl          Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Trigger threat intel crawl
  GET  /v98/status                   Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â All V98 module status
  GET  /v98/counter/stats            Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Counter response stats
  GET  /v98/canary/triggers          Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Canary token triggers
  GET  /v98/error-store/stats        Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â ErrorStore stats
  GET  /dashboard                    Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â HTML dashboard
  GET  /health                       Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Health check
  GET  /                             Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Root info
"""
from __future__ import annotations

from scp.security.env_loader import load_selected_env
load_selected_env()

import asyncio
import base64
import binascii
import logging
import os
import threading
from typing import Any


def _scp_service_identity() -> dict:
    """Expose bounded runtime identity for local service/port verification."""
    import hashlib as _hashlib
    import subprocess as _subprocess
    from pathlib import Path as _Path
    import sys as _sys
    try:
        _port = int(os.environ.get("SCP_PORT", "8000"))
    except (TypeError, ValueError):
        _port = -1
    _mode = os.environ.get("SCP_MODE")
    if not _mode:
        _mode = "production" if _port == 8000 else "test" if _port == 8001 else "unknown"
    try:
        _commit = _subprocess.check_output(
            ["git", "-C", str(_Path(__file__).resolve().parent.parent), "rev-parse", "HEAD"],
            text=True, stderr=_subprocess.DEVNULL, timeout=2,
        ).strip()
    except Exception:
        _commit = "unknown"
    _env_path = _Path(os.environ.get("SCP_ENV_FILE", _Path(__file__).resolve().parent.parent / ".env"))
    _config_hash = os.environ.get("SCP_CONFIG_HASH")
    if not _config_hash and _env_path.exists():
        try:
            _cfg = "\n".join(
                line for line in _env_path.read_text(encoding="utf-8-sig").splitlines()
                if not line.startswith("SCP_CONFIG_HASH=")
            )
            _config_hash = "sha256:" + _hashlib.sha256(_cfg.encode("utf-8")).hexdigest()
        except Exception:
            _config_hash = "unknown"
    return {
        "service_name": os.environ.get("SCP_SERVICE_NAME", "scp-backend"),
        "mode": _mode,
        "host": os.environ.get("SCP_HOST", "127.0.0.1"),
        "configured_port": _port,
        "pid": os.getpid(),
        "commit": _commit or "unknown",
        "config_hash": _config_hash or "unknown",
        "argv": list(_sys.argv),
    }
import time
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("scp.api")

from scp.web_control.internet_search import InternetSearch

from scp.api_server_parts.helpers import (
    AskRequest,
    AskResponse,
    _extract_v98_context,
    _safe_fetch_url,
    get_judge,
)
from scp.core.request_run_ledger import RequestRunLedger, stage_request, traced_request

_REQUEST_RUN_LEDGER = RequestRunLedger()

# Task Kernel integration is deliberately scoped to context-backed/RAG asks.
# Normal chat requests keep the existing JudgeCore path; a RAG request never
# silently bypasses the kernel if its durable DB/trace cannot be initialized.
_ASK_KERNEL_ADAPTERS: dict[tuple[str, str], Any] = {}
_ASK_KERNEL_ADAPTER_LOCK = threading.Lock()
_ASK_KERNEL_INIT_ERROR: Exception | None = None


def _ask_kernel_enabled(req: AskRequest) -> bool:
    if os.environ.get("SCP_ASK_KERNEL_ENABLED", "1") != "1":
        return False
    return bool(
        getattr(req, "rag_enabled", False)
        or getattr(req, "contexts", None)
        or str(getattr(req, "retrieved_context", "") or "").strip()
    )


def _get_ask_kernel_adapter() -> Any:
    """Get the durable adapter for the configured process-local paths."""
    global _ASK_KERNEL_INIT_ERROR
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.environ.get("SCP_KERNEL_DB_PATH", os.path.join(root, "data", "ask_task_kernel.sqlite3"))
    trace_path = os.environ.get("SCP_KERNEL_TRACE_PATH", os.path.join(root, "data", "ask_task_kernel_trace.jsonl"))
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
            logger.error("[ASK-KERNEL] durable adapter initialization failed: %s", type(exc).__name__)
            return None


def _kernel_gate_unavailable_response(req: AskRequest, exc: Exception) -> AskResponse:
    return AskResponse(
        verdict="FAIL",
        final_answer="[SCP: Answer withheld — Kernel gate unavailable]",
        confidence=0.0,
        domain=req.domain_override or req.domain or "general",
        falsification_status="KERNEL_GATE_UNAVAILABLE",
        governance_decision="KILL",
        v98_guard={"mode": "rag-verified", "readOnly": True, "security_blocked": True, "kernel_error": type(exc).__name__},
        v98_classification={"provenance": "kernel_gate", "evidence_count": 0},
        elapsed_ms=0.0,
        session_id=req.session_id or "ask-kernel-unavailable",
        run_status="REJECTED",
        ledger_status="BLOCKED",
    )



logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")

# V103 FIX: Auth cho admin endpoints Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â shared singleton with helpers
# (imported from helpers to ensure all Depends(_security) use the same instance)



# ============================================================
# [FIX-A P0-2] SSRF/LFI-safe URL fetcher
# ============================================================
# Replaces every `urllib.request.urlopen(<user-supplied URL>)` call site.
# Defenses:
#   1. scheme must be exactly http/https (rejects file://, ftp://, gopher://, ...)
#   2. hostname must NOT resolve to private/loopback/link-local/reserved/
#      multicast/unspecified IP (checked across ALL getaddrinfo results to
#      mitigate DNS-rebinding); literal IP forms in those ranges rejected too
#   3. strict User-Agent
#   4. [AUDIT-3 FIX] redirect following: Ä‚Â¢Ă¢â‚¬Â°Ă‚Â¤5 hops, each hop re-validated against
#      _is_disallowed_ip (prevents SSRF via 302 Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ http://169.254.169.254/...).
#      Was: no redirects at all Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ broke legitimate image CDNs (Imgur, S3 presigned,
#      Bit.ly, Google Photos). Now: follow safe redirects, block unsafe ones.
#   5. max_bytes cap via streaming read + early abort (no unbounded resp.read())
#   6. per-request timeout (default 8s)
#   7. proxy disabled (prevents SSRF bypass via HTTP_PROXY env var)
# Callers MUST run this via asyncio.to_thread to avoid blocking the event loop.
# On any violation raises ValueError; callers return generic HTTP 400 (do NOT
# echo the URL or internal error back to the client).
# [Fix 4-a-005 / Phase 3-A] _SCP_SAFE_FETCH_UA was REMOVED from this file
# Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â it was dead code (api_server.py never referenced it after the import
# of _safe_fetch_url from helpers, which uses the canonical UA). The single
# canonical definition now lives in scp.core.url_fetcher. DNA #5: no more
# two definitions of the same constant.




# ============================================================
# V98 RealityJudge init (singleton)
# ============================================================
# [FIX-12] Single source of truth for SCP version Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â import from package root.
# RC-1 FIX: TYPE_CHECKING import so the Optional["PredictiveOrchestrator"]
# annotation at line ~341 resolves at type-check time (was F821 Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â the symbol
# referenced as "PredictiveEngine" never existed; the real class is
# PredictiveOrchestrator, imported lazily inside get_judge()).
from typing import TYPE_CHECKING

from scp import __version__ as _SCP_VERSION
from scp.core.release_identity import (
    DOMAIN_EXPERT_ENSEMBLE_TERM,
    DOMAIN_EXPERT_TERM,
    RELEASE_LABEL,
    public_release_metadata,
)
from scp.core.streaming_factcheck import StreamingFactChecker
from scp.meta.simple_explainer import SimpleExplainer
from scp.runtime.judge import RealityJudge

# V103 NEW: AttackCrawler Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â tÄ‚Â¡Ă‚ÂºĂ‚Â£i tÄ‚Â¡Ă‚ÂºĂ‚Â¥n cĂ„â€Ă‚Â´ng mÄ‚Â¡Ă‚Â»Ă¢â‚¬Âºi tÄ‚Â¡Ă‚Â»Ă‚Â« internet
from scp.security.attack_crawler import AttackCrawler
from scp.security.cross_language_learner import CrossLanguageLearner
from scp.security.image_voice_detector import ImageJailbreakDetector, VoiceJailbreakDetector

# V104 NEW: Multi-turn + Image/Voice + Cross-language + Streaming + Simple Explainer
from scp.security.multi_turn_tracker import MultiTurnTracker

if TYPE_CHECKING:
    from scp.prediction.predictive import PredictiveOrchestrator as PredictiveEngine

# [V104.48] Chat WebSocket + Code Evolution Agent
try:
    from scp.api.chat import router as chat_router
    _CHAT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"V104.48 Chat router unavailable: {e}")
    _CHAT_AVAILABLE = False

# [Task 7-A] V98 + V100 admin routes extracted to modules Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â imported LAZILY below
# (after SessionAnalyzeRequest/SimulationRequest are defined) to avoid circular import.
_V98_V100_ROUTERS_AVAILABLE = False
v98_admin_router = None
v100_admin_router = None

# V104 FIX: Real Learning Engine Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â hÄ‚Â¡Ă‚Â»Ă‚Âc tÄ‚Â¡Ă‚Â»Ă‚Â« Ollama + Local + News
from scp.core.real_learning_engine import RealLearningEngine

# V104.2 NEW: Fast Learning Engine Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â parallel + skip-known + compounding
try:
    from scp.core.fast_learning_engine import (  # noqa: F401 (availability check)
        FastLearningEngine,
        start_fast_learning_thread,
    )
    _V1042_AVAILABLE = True
except ImportError as e:
    logger.warning(f"V104.2 FastLearningEngine unavailable: {e}")
    _V1042_AVAILABLE = False

# [V104.47 RESTORE] V104.3 StartupOptimizer + V104.4 DataPartitioner
# TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: 2 file nĂ„â€Ă‚Â y cĂ„â€Ă‚Â³ trong V104.4 nhÄ‚â€ Ă‚Â°ng mÄ‚Â¡Ă‚ÂºĂ‚Â¥t Ä‚Â¡Ă‚Â»Ă…Â¸ V104.19 baseline.
# KhĂ„â€Ă‚Â´i phÄ‚Â¡Ă‚Â»Ă‚Â¥c tÄ‚Â¡Ă‚Â»Ă‚Â« V104.4 gÄ‚Â¡Ă‚Â»Ă¢â‚¬Ëœc.
try:
    from scp.core.startup_optimizer import (  # noqa: F401 (availability check)
        STARTUP_DEFER_SECONDS,
        cleanup_data_directory,
        deferred_background_start,
        get_data_directory_stats,
        run_startup_optimization,
    )
    _V1043_AVAILABLE = True
except ImportError as e:
    logger.warning(f"V104.3 StartupOptimizer unavailable: {e}")
    _V1043_AVAILABLE = False

try:
    from scp.core.data_partitioner import (  # noqa: F401 (availability check)
        DOMAIN_KEYWORDS,
        DOMAIN_TABLES,
        TTL_QUESTION_LOG,
        TTL_VERDICT_CACHE,
        TTL_VERDICT_CACHE_DB,
        BypassLessonsStore,
        DataPartitioner,
        ThreeTierCache,
        TTLExpirer,
        detect_domain,
        migrate_old_to_new,
    )
    _V1044_AVAILABLE = True
except ImportError as e:
    logger.warning(f"V104.4 DataPartitioner unavailable: {e}")
    _V1044_AVAILABLE = False

_judge: RealityJudge | None = None
# [FIX-10] Module-level lock for get_judge() double-checked locking.
# TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: previously get_judge() had no lock Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â two concurrent /ask
# requests at startup both saw `_judge is None`, both instantiated
# RealityJudge (which spawns AttackCrawler + RealLearningEngine +
# FastLearningEngine + StartupOptimizer threads). Result: thread
# explosion + duplicate singletons. Lock + double-check prevents it.
_judge_lock = threading.Lock()
_background_task: asyncio.Task | None = None
_attack_crawler: AttackCrawler | None = None
# V104 NEW: Singletons
_multi_turn_tracker = MultiTurnTracker()
_image_detector = ImageJailbreakDetector()
_voice_detector = VoiceJailbreakDetector()
_cross_language_learner = CrossLanguageLearner()
_fact_checker = StreamingFactChecker()
_simple_explainer = SimpleExplainer()

# V104 FIX: Real Learning Engine singleton
_real_learning = RealLearningEngine(scp_db_path="data/v13.db", data_dir="data")
# V104.2 NEW: Fast Learning Engine singleton (parallel + skip-known + compounding)
_fast_learning: FastLearningEngine | None = None
if _V1042_AVAILABLE:
    _fast_learning = FastLearningEngine(scp_db_path="data/v13.db", data_dir="data")
# [V104.36 #56-wire] PredictiveEngine singleton Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â wired to production judge
# TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: V104.35 #56 fixed SelfLearner to accept judge, but PredictiveEngine
# was never instantiated with judge Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ self-learning still trained throwaway instance.
# Now: _predictive_engine is created in get_judge() AFTER _judge exists, so it
# gets the PRODUCTION judge reference Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ real self-correction.
_predictive_engine: PredictiveEngine | None = None

# [SCP-DNA-FIX / RUF006] Strong references for fire-and-forget asyncio tasks.
# TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: asyncio.create_task() returns a Task that the GC may collect before
# completion if no reference is held. The /ask handler below spawns a background
# fact-check and returns immediately -> the local reference vanishes -> CPython's
# garbage collector is free to cancel the task mid-flight. Symptom: fact-check
# silently never runs (no error log Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â the task simply ceases to exist). This is
# exactly the "silent failure" pattern SCP's DNA warns about (PASS != TRUE).
# Fix: hold strong refs in a module-level set; a done-callback discards them.
_async_factcheck_tasks: set = set()



# ============================================================
# Request/Response models
# ============================================================



class SimulationRequest(BaseModel):
    count: int = Field(50, ge=1, le=500)


# [Task 7-A] V98 + V100 admin routers Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â imported AFTER SessionAnalyzeRequest/
# SimulationRequest are defined above to avoid circular import.
# TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: admin_v98.py needs SessionAnalyzeRequest/SimulationRequest from this
# module. If imported at top (line 290), api_server.py is still loading Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ ImportError.
try:
    from scp.api.routes.admin_v98 import router as v98_admin_router
    from scp.api.routes.admin_v100 import router as v100_admin_router
    _V98_V100_ROUTERS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"[Task 7-A] V98/V100 admin routers unavailable: {e}")
    _V98_V100_ROUTERS_AVAILABLE = False

# [Task 8-A] DASHBOARD_HTML extracted to api/dashboard_html.py
try:
    from scp.api.dashboard_html import DASHBOARD_HTML
except ImportError as e:
    logger.warning(f"[Task 8-A] dashboard_html unavailable: {e}")
    DASHBOARD_HTML = "<html><body>Dashboard unavailable</body></html>"

# [Task 9-B] V102-V105 + openai-compat + import routers Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â lazy import AFTER
# all shared state defined (avoids circular import: openai_compat needs
# _extract_v98_context, v104 needs _multi_turn_tracker, etc.).
_EXTRA_ROUTERS_AVAILABLE = False


# ============================================================
# Lifespan
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _background_task
    logger.info("=" * 60)
    logger.info(f"{RELEASE_LABEL} API Server starting...")
    logger.info("=" * 60)

    # [SCP-DNA-FIX R12-28] Disable WHY LLM + evolution during startup (fast boot).
    _orig_why_llm = os.environ.get("SCP_WHY_LLM_ENABLED", "0")
    _orig_evo_auto = os.environ.get("SCP_EVOLUTION_AUTO", "0")
    os.environ["SCP_WHY_LLM_ENABLED"] = "0"
    os.environ["SCP_EVOLUTION_AUTO"] = "0"

    # ============================================================
    # [STARTUP-GATE] Pre-startup deep audit Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â chÄ‚Â¡Ă‚ÂºĂ‚Â¡y TRÄ‚â€ Ă‚Â¯Ä‚Â¡Ă‚Â»Ă‚ÂC khi server start
    # [SCP-DNA-FIX R12-29] Use FAST ast_scan_scp (3s) thay vĂ„â€Ă‚Â¬ pre_startup_audit (SLOW Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â LLM).
    # TÄ‚Â¡Ă‚ÂºĂ‚Â¡i sao: pre_startup_audit() calls run_deep_audit() Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ process_bug_with_llm()
    # Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ LLM call mÄ‚Â¡Ă‚Â»Ă¢â‚¬â€i bug Ă„â€Ă¢â‚¬â€ 200 bugs = 2000s = 33 min Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ server timeout.
    # Fix: chÄ‚Â¡Ă‚Â»Ă¢â‚¬Â° SCAN (fast), khĂ„â€Ă‚Â´ng FIX. Bugs sÄ‚Â¡Ă‚ÂºĂ‚Â½ fix background sau khi server up.
    # ============================================================
    async def _startup_gate_background():
        """Run bounded AST startup scan without blocking socket readiness."""
        await asyncio.sleep(max(0.0, float(os.environ.get("SCP_STARTUP_BACKGROUND_DELAY_SEC", "5"))))
        if os.environ.get("SCP_SKIP_STARTUP_GATE", "0") == "1":
            logger.warning("[STARTUP-GATE] SCP_SKIP_STARTUP_GATE=1 Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â audit BYPASSED (dev/test mode)")
            return
        try:
            from scp.autofix.runner import ast_scan_scp
            timeout_sec = float(os.environ.get("SCP_STARTUP_SCAN_TIMEOUT_SEC", "15"))
            bugs = await asyncio.wait_for(
                asyncio.to_thread(
                    ast_scan_scp,
                    max_files=int(os.environ.get("SCP_MAX_STARTUP_FILES", "100")),
                    include_enterprise=os.environ.get("SCP_STARTUP_SCAN_ENTERPRISE", "0") == "1",
                ),
                timeout=max(1.0, timeout_sec),
            )
            logger.info(f"[STARTUP-GATE] Background scan complete: {len(bugs)} bugs found")
        except asyncio.TimeoutError:
            logger.warning(f"[STARTUP-GATE] Background scan timed out after {timeout_sec}s (non-blocking)")
        except Exception as e:
            logger.warning(f"[STARTUP-GATE] Background scan failed (non-blocking): {e}")
    _startup_gate_task = asyncio.create_task(_startup_gate_background())
    # ============================================================
    # Server start (chÄ‚Â¡Ă‚Â»Ă¢â‚¬Â° Ä‚â€Ă¢â‚¬ËœÄ‚Â¡Ă‚ÂºĂ‚Â¿n Ä‚â€Ă¢â‚¬ËœĂ„â€Ă‚Â¢y nÄ‚Â¡Ă‚ÂºĂ‚Â¿u audit PASS)
    # ============================================================
    # [R20-ROOT-FIX-REAL] get_judge() moved to BACKGROUND Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â port binds NOW!
    #
    # ROOT CAUSE of 2-hour 503 (DNA #22: PASS Ä‚Â¢Ă¢â‚¬Â°Ă‚Â  TRUE):
    #   I put R20-ROOT-FIX in _lifespan.py (PASS Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â code exists)
    #   BUT FastAPI uses api_server.py lifespan (TRUE Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â different file!)
    #   get_judge() at line 283 blocks lifespan Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ port doesn't bind Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ 503
    #
    # FIX: Move get_judge() to background thread, yield IMMEDIATELY.
    # DNA #26 (Reality > Model): Reality = log shows "Initializing RealityJudge"
    #   synchronously Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ port 8000 not bound Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ 503 for 2 hours.
    # ============================================================
    import threading as _threading_r20

    def _init_judge_background_r20():
        """Init judge in background Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â /ask returns 503 until ready, /health returns 200.

        [SCP-DNA-FIX 4-a-001] TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: previously this thread function did
        two things that both failed silently:
          1. `asyncio.create_task(judge.schedule_background_jobs())` raised
             `RuntimeError: no running event loop` (thread is not async) Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢
             swallowed by `except Exception` Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ background scheduler never ran.
          2. `judge` was a LOCAL variable, never propagated back to module
             scope Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ the post-yield block referenced `judge` Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ NameError Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢
             swallowed Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ scheduler never ran from there either.
        Reality (DNA #26): ThreatSimulator (6h) + IntelCrawler (12h) NEVER ran.
        Fix: (a) remove the broken in-thread create_task, (b) set the
        module-level `_judge` so the lifespan post-yield block (which runs
        inside the running event loop) can schedule the job correctly.
        """
        global _judge  # propagate judge to module scope for lifespan post-yield
        try:
            judge = get_judge()
            _judge = judge  # module-level singleton Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â lifespan post-yield polls this
            logger.info(f"[R20-ROOT-FIX-REAL] Judge ready: {len(judge.slms)} SLMs")
            logger.info(f"[R20-ROOT-FIX-REAL] V98 status: {judge.get_v98_status()}")
            # [4-a-001] Background scheduler start is deferred to the lifespan
            # post-yield block (which runs inside the running event loop).
            # asyncio.create_task cannot be called from this non-async thread.
        except Exception as e:
            logger.error(f"[R20-ROOT-FIX-REAL] Judge init FAILED: {e}")
            logger.error("[R20-ROOT-FIX-REAL] /ask will return 503 until judge is available")

    _judge_thread_r20 = _threading_r20.Thread(
        target=_init_judge_background_r20,
        name="scp-judge-init-r20",
        daemon=True,
    )
    async def _launch_judge_deferred():
        await asyncio.sleep(max(0.0, float(os.environ.get("SCP_JUDGE_START_DELAY_SEC", "5"))))
        try:
            _judge_thread_r20.start()
        except RuntimeError as e:
            logger.warning(f"[R20-ROOT-FIX-REAL] Deferred judge launch skipped: {e}")
    _judge_launch_task = asyncio.create_task(_launch_judge_deferred())
    logger.info("[R20-ROOT-FIX-REAL] Judge init dispatched to background thread")
    logger.info("[R20-ROOT-FIX-REAL] Yielding NOW Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â port 8000 binds immediately")

    # [R20-ROOT-FIX-REAL] All background services below moved to AFTER yield.
    # They are daemon threads Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â safe to start after port bound.
    # Original synchronous code (lines 322-451) moved to post-yield context.

    # [4-a-001] Initialize health flag BEFORE yield so /health/detailed can
    # report a defined state during the brief window between port bind and
    # scheduler start.
    app.state.background_scheduler_started = False

    # [SCP-DNA-FIX 4-a-001] Bootstrap scheduler before lifespan yield.
    # The bootstrap task runs on the active event loop; post-yield is shutdown.
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
                _background_task = asyncio.create_task(
                    asyncio.to_thread(_run_scheduler_offloop)
                )
                app.state.background_scheduler_started = True
                logger.info("Background scheduler started (ThreatSimulator 6h + IntelCrawler 12h)")
            else:
                app.state.background_scheduler_started = False
                logger.error("[4-a-001] Background scheduler NOT started: _judge is None after 30s")
        except asyncio.CancelledError:
            app.state.background_scheduler_started = False
            raise
        except Exception as e:
            app.state.background_scheduler_started = False
            logger.error(f"[4-a-001] Background scheduler failed: {e}", exc_info=True)
    _scheduler_bootstrap_task = asyncio.create_task(_start_background_scheduler())

    # Initialize the Evolution singleton for an explicit DISABLED heartbeat.
    # Constructor-only: no cycle, no provider call, no policy promotion.
    app.state.evolution_initialized = False
    async def _start_evolution_runtime():
        try:
            await asyncio.sleep(5)
            from scp.autofix.evolution import get_evolution_engine
            await asyncio.to_thread(
                get_evolution_engine, data_dir=os.environ.get("SCP_DATA_DIR", "data")
            )
            app.state.evolution_initialized = True
            logger.info("[EVOLUTION] Runtime initialized; auto promotion remains env-gated")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[EVOLUTION] Runtime initialization failed: %s", exc)
    _evolution_bootstrap_task = asyncio.create_task(_start_evolution_runtime())

    # [RUNTIME-FIX-HEARTBEAT] These loops belong to startup, not shutdown.
    # Code after the lifespan yield is cleanup-only. Keep explicit handles so
    # health/cleanup can distinguish never-started from stopped.
    _audit_thread = None
    _attack_thread = None
    app.state.deep_audit_started = False
    app.state.attack_monitor_started = False
    try:
        import threading as _threading
        import time as _time
        from scp.autofix.runner import run_deep_audit
        from scp.core.subsystem_telemetry import SubsystemTelemetry, heartbeat_sleep

        _audit_telemetry = SubsystemTelemetry("deep_audit", os.environ.get("SCP_DATA_DIR", "data"))
        _audit_telemetry.start(mode="background", config={"interval_seconds": 86400})
        _audit_telemetry.tick(status="IDLE")
        _audit_stop = _threading.Event()
        _audit_state = {"status": "STARTING"}
        app.state.deep_audit_stop = _audit_stop

        def _deep_audit_heartbeat_loop():
            while not _audit_stop.is_set():
                try:
                    _audit_telemetry.tick(status=_audit_state["status"])
                except Exception as exc:
                    logger.warning("[AUTO] deep-audit heartbeat tick failed: %s", exc)
                if _audit_stop.wait(15):
                    return

        _threading.Thread(
            target=_deep_audit_heartbeat_loop,
            daemon=True,
            name="scp-deep-audit-heartbeat",
        ).start()

        def _deep_audit_loop():
            heartbeat_sleep(_audit_telemetry, 60, status="IDLE")
            while not _audit_stop.is_set():
                run_id = f"deep-audit-{_time.time_ns()}"
                _audit_state["status"] = "RUNNING"
                _audit_telemetry.cycle_started(run_id, trigger="interval")
                try:
                    logger.info("[AUTO] Deep audit cycle starting...")
                    results = run_deep_audit(max_bugs=int(os.environ.get("SCP_MAX_AUDIT_BUGS", "100")))
                    logger.info(
                        "[AUTO] Deep audit: %s bugs processed, %s auto-fixed",
                        results.get("processed", 0), results.get("fixed", 0),
                    )
                    _audit_telemetry.cycle_completed(
                        run_id, "SUCCESS", bugs_found=results.get("processed", 0),
                        bugs_fixed=results.get("fixed", 0), stored=results.get("stored", 0),
                    )
                except TimeoutError as exc:
                    logger.warning("[AUTO] Deep audit timeout: %s", exc)
                    _audit_telemetry.cycle_failed(run_id, exc, status="TIMEOUT")
                except Exception as exc:
                    logger.warning("[AUTO] Deep audit failed: %s", exc)
                    _audit_telemetry.cycle_failed(run_id, exc, status="PROVIDER_FAILED")
                _audit_state["status"] = "IDLE"
                heartbeat_sleep(_audit_telemetry, 86400, status="IDLE")

        _audit_thread = _threading.Thread(
            target=_deep_audit_loop, daemon=True, name="scp-deep-audit-scheduler"
        )
        _audit_thread.start()
        app.state.deep_audit_started = True
        logger.info("[AUTO] Deep audit scheduler started before lifespan yield (24h interval)")
    except Exception as exc:
        logger.warning("[AUTO] Deep audit scheduler failed to start: %s", exc)

    try:
        from scp.autofix.engine import get_autofix_engine
        from scp.core.subsystem_telemetry import SubsystemTelemetry, heartbeat_sleep

        _attack_telemetry = SubsystemTelemetry("attack_monitor", os.environ.get("SCP_DATA_DIR", "data"))
        _attack_telemetry.start(mode="background", config={"interval_seconds": 300})
        _attack_telemetry.tick(status="IDLE")
        _attack_stop = _threading.Event()
        _attack_state = {"status": "STARTING"}
        app.state.attack_monitor_stop = _attack_stop

        def _attack_heartbeat_loop():
            while not _attack_stop.is_set():
                try:
                    _attack_telemetry.tick(status=_attack_state["status"])
                except Exception as exc:
                    logger.warning("[AUTO] attack-monitor heartbeat tick failed: %s", exc)
                if _attack_stop.wait(15):
                    return

        _threading.Thread(
            target=_attack_heartbeat_loop,
            daemon=True,
            name="scp-attack-monitor-heartbeat",
        ).start()

        def _attack_mode_monitor():
            heartbeat_sleep(_attack_telemetry, 120, status="IDLE")
            while not _attack_stop.is_set():
                run_id = f"attack-monitor-{_time.time_ns()}"
                _attack_state["status"] = "RUNNING"
                _attack_telemetry.cycle_started(run_id, trigger="interval")
                try:
                    eng = get_autofix_engine()
                    notif = getattr(_judge, "notifications", None)
                    cutoff = _time.time() - 600
                    kill_count = notif.count_recent_by_type("governance_kill", cutoff) if notif is not None else 0
                    if kill_count > 20 and not eng.in_attack_mode:
                        eng.set_attack_mode(True)
                        logger.warning("[AUTO] Attack mode ENABLED â€” %s KILLs in 10min", kill_count)
                    elif kill_count < 5 and eng.in_attack_mode:
                        eng.set_attack_mode(False)
                        logger.info("[AUTO] Attack mode DISABLED â€” %s KILLs in 10min", kill_count)
                    _attack_telemetry.cycle_completed(run_id, "SUCCESS", asked=kill_count, verified=1)
                except TimeoutError as exc:
                    logger.warning("[AUTO] Attack mode monitor timeout: %s", exc)
                    _attack_telemetry.cycle_failed(run_id, exc, status="TIMEOUT")
                except Exception as exc:
                    logger.warning("[AUTO] Attack mode monitor: %s", exc)
                    _attack_telemetry.cycle_failed(run_id, exc, status="PROVIDER_FAILED")
                _attack_state["status"] = "IDLE"
                heartbeat_sleep(_attack_telemetry, 300, status="IDLE")

        _attack_thread = _threading.Thread(
            target=_attack_mode_monitor, daemon=True, name="scp-attack-mode-monitor"
        )
        _attack_thread.start()
        app.state.attack_monitor_started = True
        logger.info("[AUTO] Attack mode monitor started before lifespan yield (5min interval)")
    except Exception as exc:
        logger.warning("[AUTO] Attack mode monitor failed to start: %s", exc)

    # [WIRING-FIX] Start file-backed audit/threat/harm producers in the
    # lifespan that FastAPI actually uses. The extracted `_lifespan.py` had
    # these calls, but this app is bound to this function above. Keep handles
    # so shutdown is explicit and each producer can be inspected independently.
    _data_services_started: list[tuple[str, object]] = []
    for _service_name in ("audit_fetcher", "ai_threat_scanner", "harm_detector"):
        try:
            if _service_name == "audit_fetcher":
                from scp.core.audit_fetcher import start_audit_fetcher, stop_audit_fetcher
                _start_fn, _stop_fn = start_audit_fetcher, stop_audit_fetcher
            elif _service_name == "ai_threat_scanner":
                from scp.core.ai_threat_scanner import start_scanner, stop_scanner
                _start_fn, _stop_fn = start_scanner, stop_scanner
            else:
                from scp.core.harm_detector import start_detector, stop_detector
                _start_fn, _stop_fn = start_detector, stop_detector
            _start_fn()
            _data_services_started.append((_service_name, _stop_fn))
            logger.info("[WIRING-FIX] %s started in active api_server lifespan", _service_name)
        except Exception as _service_err:
            logger.warning("[WIRING-FIX] %s unavailable or failed to start: %s", _service_name, _service_err)
    app.state.data_services_started = [name for name, _ in _data_services_started]

    yield

    # ============================================================
    # [OPT-14 / GĂ„â€Ă‚Â  Ä‚â€Ă‚Â§8] External trust root verification Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â at startup,
    # verify that the 3 external anchors (independent audit tests, CI/CD
    # pipeline, human-approved constitution) are intact. SCP cannot
    # self-verify; it needs these external anchors. If any are missing or
    # tampered, log a WARNING (non-blocking Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â server still starts, but the
    # admin must investigate). This is the "GÄ‚Â¡Ă‚Â»Ă¢â‚¬Ëœc tin cÄ‚Â¡Ă‚ÂºĂ‚Â­y bĂ„â€Ă‚Âªn ngoĂ„â€Ă‚Â i" principle.
    # ============================================================
    try:
        from scp.meta.external_trust import get_external_trust_root
        _et = get_external_trust_root(".")
        _et_result = _et.verify_external()
        if _et_result["passed"]:
            logger.info("[GĂ„â€Ă‚Â  Ä‚â€Ă‚Â§8] External trust roots verified Ä‚Â¢Ă…â€œĂ¢â‚¬Â¦ "
                        "(audit tests + CI/CD + constitution)")
        else:
            logger.warning(
                f"[GĂ„â€Ă‚Â  Ä‚â€Ă‚Â§8] External trust BROKEN Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â missing: "
                f"{_et_result['missing']}, constitution_approved: "
                f"{_et_result['constitution_approved']}. "
                f"Server will start but external anchors are not intact."
            )
    except Exception as _et_err:
        logger.warning(f"[GĂ„â€Ă‚Â  Ä‚â€Ă‚Â§8] External trust verification failed: {_et_err}")

    # [SCP-DNA-FIX R12-28] Restore WHY LLM + Evolution AUTO Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â server about to serve.
    os.environ["SCP_WHY_LLM_ENABLED"] = _orig_why_llm
    os.environ["SCP_EVOLUTION_AUTO"] = _orig_evo_auto
    logger.info(f"[STARTUP] WHY LLM + Evolution AUTO restored (why={_orig_why_llm}, evo={_orig_evo_auto})")

    # [R20-ROOT-FIX-REAL] Old yield was HERE (line 464) Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â moved to line 326 above.

    for _service_name, _stop_fn in reversed(_data_services_started):
        try:
            _stop_fn()
            logger.info("[WIRING-FIX] %s stopped during api_server shutdown", _service_name)
        except Exception as _service_err:
            logger.warning("[WIRING-FIX] %s shutdown failed: %s", _service_name, _service_err)

    for _stop_event in (getattr(app.state, "deep_audit_stop", None), getattr(app.state, "attack_monitor_stop", None)):
        if _stop_event is not None:
            _stop_event.set()
    for _task in (_scheduler_bootstrap_task, _evolution_bootstrap_task, _background_task, _startup_gate_task, _judge_launch_task):
        if _task is not None and not _task.done():
            _task.cancel()
    logger.info(f"{RELEASE_LABEL} API Server shutting down...")


# ============================================================
# FastAPI app
# ============================================================
app = FastAPI(
    title=f"{RELEASE_LABEL} - Self-Correcting Pipeline API",
    description=f"{DOMAIN_EXPERT_ENSEMBLE_TERM} + FalsificationEngine + Governance + Chat + Evolution",
    version=_SCP_VERSION,
    lifespan=lifespan,
)
# [FIX-A P0-3 Bug C] CORS hardening Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â was allow_origins=["*"] + methods=*
# + headers=* which combined with no-auth endpoints let any website call any
# route cross-origin and exfiltrate responses. Now: explicit origin allowlist
# via SCP_CORS_ORIGINS (comma-separated, default localhost:3000 for dev),
# restricted methods, restricted headers, no credentials (we use bearer, not
# cookies Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â credentials=True with wildcard origin is invalid anyway).
_cors_origins_raw = os.environ.get("SCP_CORS_ORIGINS", "http://localhost:3000")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["http://localhost:3000"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)
# ============================================================
# [OPT-43] CSRF + HTTPS HARDENING
# ============================================================
# TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: auditor flagged "no CSRF protection, no HTTPS config".
#
# CSRF:
#   FastAPI does not ship built-in CSRF middleware. However, SCP API uses
#   Bearer-token auth (Authorization: Bearer <token>) for state-changing
#   routes Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â NOT cookies. A CSRF attacker (evil.com) cannot forge the
#   Authorization header on a victim's browser because:
#     1. Cross-origin XHR/fetch cannot set custom `Authorization` header
#        without a CORS preflight, and our CORS allowlist (above) blocks
#        unapproved origins.
#     2. Even if preflight passed, the attacker does not possess the
#        victim's bearer token (it is not auto-attached like a cookie).
#   Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ Bearer-token auth = inherent CSRF protection. OWASP CSWSH + SOP
#     confirm: APIs that do NOT use cookies for auth are not vulnerable
#     to classical CSRF. (See OWASP CSRF Prevention Cheat Sheet Ä‚â€Ă‚Â§"Use
#     Standard Headers to Verify Origin" + Ä‚â€Ă‚Â§"Use Synchronizer Token".)
#   This is logged at startup for audit visibility.
#
# HTTPS:
#   HTTPSRedirectMiddleware is OPT-IN via SCP_FORCE_HTTPS=1. We do NOT
#   force HTTPS in dev (breaks localhost:8002 testing). Production
#   deployments set SCP_FORCE_HTTPS=1 (and typically run behind a TLS-
#   terminating reverse proxy anyway, so the redirect is a defense-in-
#   depth backstop, not the primary TLS layer).
# ============================================================
try:
    from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
    if os.environ.get("SCP_FORCE_HTTPS", "0") == "1":
        app.add_middleware(HTTPSRedirectMiddleware)
        logger.info("[Security] HTTPS redirect enabled (SCP_FORCE_HTTPS=1)")
    else:
        # [AUTOFIX-T2-SEC] Louder warning for production (non-localhost) deployments.
        # DNA SCP #6 Evidence Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â log the risk explicitly so operators can't miss it.
        _bind_host = os.environ.get("SCP_HOST", "127.0.0.1")
        if _bind_host not in ("127.0.0.1", "localhost", "::1"):
            logger.warning(
                "[Security] Ä‚Â¢Ă‚ÂĂ‚Â Ä‚Â¯Ă‚Â¸Ă‚Â  PRODUCTION DEPLOYMENT without HTTPS! "
                f"Host={_bind_host} Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â set SCP_FORCE_HTTPS=1 or use a TLS-terminating "
                f"reverse proxy. Without HTTPS, auth tokens travel in plaintext."
            )
        else:
            logger.info("[Security] HTTPS redirect disabled (set SCP_FORCE_HTTPS=1 in prod)")
except ImportError:
    logger.debug("[Security] HTTPSRedirectMiddleware unavailable (older FastAPI)")
logger.info("[Security] CSRF protection: Bearer token auth (attacker cannot forge Authorization header)")

# [V104.48] Register chat router AFTER app creation
if _CHAT_AVAILABLE:
    app.include_router(chat_router, tags=["chat"])

# [Task 7-A] Register V98 + V100 admin routers (extracted from inline routes)
if _V98_V100_ROUTERS_AVAILABLE:
    app.include_router(v98_admin_router)
    app.include_router(v100_admin_router)





# [Task 9-B] Register V102-V105 + openai-compat + import routers.
# Lazy import AFTER all shared state defined (avoids circular import:
# openai_compat.py needs _extract_v98_context).
try:
    from scp.api.routes.import_routes import router as import_router
    from scp.api.routes.openai_compat import router as openai_compat_router
    from scp.api.routes.v102_v103_routes import router as v102_v103_router
    from scp.api.routes.v104_routes import router as v104_router
    from scp.api.routes.v105_routes import router as v105_router
    _EXTRA_ROUTERS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"[Task 9-B] V102-V105/import routers unavailable: {e}")
    _EXTRA_ROUTERS_AVAILABLE = False

if _EXTRA_ROUTERS_AVAILABLE:
    app.include_router(openai_compat_router)
    app.include_router(v102_v103_router)
    app.include_router(import_router)
    app.include_router(v104_router)
    app.include_router(v105_router)

# SCP control plane: authenticated capability and escalation decisions.
# Import is fail-safe so an optional control module cannot kill startup.
try:
    from scp.api.routes.control_routes import router as control_router
    app.include_router(control_router, tags=["control"])
    _CONTROL_ROUTES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"[SCP Control] Control router unavailable: {e}")
    _CONTROL_ROUTES_AVAILABLE = False

# [R12-10] Wire 4 previously-dead v105 routers (stream/threat/audit/prediction).

# These routers existed in scp/api/routes/ but were never `include_router`-ed
# (wiring-scan report). Each is wrapped in try/except to fail open (DNA #7:
# a router import error must not crash the whole server Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â degraded mode > dead server).
# Routes activated:
#   - stream_routes:      POST /v105/ask/stream
#   - threat_routes:      GET  /v105/threats/ai-scan/{stats,findings},
#                         GET  /v105/threats/harm/{stats,incidents}
#   - audit_routes:       GET  /v105/audit/{stats,findings}
#   - prediction_routes:  POST /v105/predictions/{run-cycle,verify},
#                         GET  /v105/predictions/{pending,all,stats}
try:
    from scp.api.routes.stream_routes import router as stream_router
    app.include_router(stream_router, tags=["stream"])
except ImportError as _e:
    logger.warning(f"[R12-10] stream_routes router unavailable: {_e}")

try:
    from scp.api.routes.threat_routes import router as threat_router
    app.include_router(threat_router, tags=["threats"])
except ImportError as _e:
    logger.warning(f"[R12-10] threat_routes router unavailable: {_e}")

try:
    from scp.api.routes.audit_routes import router as audit_router
    app.include_router(audit_router, tags=["audit"])
except ImportError as _e:
    logger.warning(f"[R12-10] audit_routes router unavailable: {_e}")

try:
    from scp.api.routes.prediction_routes import router as prediction_router
    app.include_router(prediction_router, tags=["predictions"])
except ImportError as _e:
    logger.warning(f"[R12-10] prediction_routes router unavailable: {_e}")

# [Task 42-B / OPT-41] Register webhook router (POST /api/analyze, /api/register,
# GET /api/threats, /api/alerts, /api/systems) Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â additive, no existing route touched.
# DNA SCP #6 Evidence: external AI systems need a programmatic endpoint to send
# prompts for analysis. DNA SCP #9 No harm: webhook is read-only (analyze, no exec).
try:
    from scp.api.webhook import router as webhook_router
    app.include_router(webhook_router)
    _WEBHOOK_ROUTER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"[Task 42-B] Webhook router unavailable: {e}")
    _WEBHOOK_ROUTER_AVAILABLE = False

# ============================================================
# SCP V3.1 PC Controller Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â local-only by default, policy-gated actions.
try:
    from scp.api.routes.pc_controller_routes import router as pc_controller_router
    app.include_router(pc_controller_router)
    _PC_CONTROLLER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"[V3.1] PC Controller router unavailable: {e}")
    _PC_CONTROLLER_AVAILABLE = False

# SCP V3.1 browser and AI orchestration Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â local browser session first.
try:
    from scp.api.routes.web_control_routes import router as web_control_router
    app.include_router(web_control_router)
    _WEB_CONTROL_AVAILABLE = True
except ImportError as e:
    logger.warning(f"[V3.1] Web control router unavailable: {e}")
    _WEB_CONTROL_AVAILABLE = False


async def _ask_benchmark_fast(req: AskRequest, request: Request) -> AskResponse:
    """Read-only benchmark path: local answer first, web retrieval on timeout.

    This path is intentionally explicit and only activated by the internal
    batch source marker. Normal users continue through the full SCP JudgeCore.
    It preserves provenance and marks verification as deferred instead of
    presenting a fast candidate as a fully verified PASS.
    """
    started = time.time()
    answer = (req.ai_answer or "").strip()
    provider = "provided_answer" if answer else ""
    failures: list[str] = []
    web_fallback: dict[str, Any] = {}

    if not answer:
        try:
            from scp.llm_gateway import get_gateway
            timeout = min(float(os.environ.get("SCP_BENCHMARK_LLM_TIMEOUT", "12")), 30.0)
            answer, provider = await asyncio.wait_for(
                get_gateway().chat(
                    req.question,
                    context="",
                    system_prompt=(
                        "Answer the question concisely and directly. "
                        "For arithmetic return the numeric result. "
                        "For geography return only the capital name when known. "
                        "If the prompt is ambiguous or an attack, say UNKNOWN."
                    ),
                    task="benchmark",
                ),
                timeout=timeout,
            )
            answer = (answer or "").strip()
        except Exception as exc:
            failures.append(f"local_llm:{str(exc)[:180]}")

    if not answer and os.environ.get("SCP_WEB_FALLBACK", "1") == "1":
        try:
            timeout = min(float(os.environ.get("SCP_BENCHMARK_WEB_TIMEOUT", "6")), 10.0)
            web_fallback = await asyncio.wait_for(
                InternetSearch(timeout=min(timeout / 2.0, 3.0)).search(req.question, max_results=4),
                timeout=timeout,
            )
            if web_fallback.get("success"):
                provider = "public-search"
                # Keep snippets as evidence, not as a fabricated verified answer.
                first = web_fallback.get("results", [])[0]
                answer = str(first.get("snippet") or first.get("title") or "").strip()
        except Exception as exc:
            failures.append(f"public_search:{str(exc)[:180]}")

    session_id = req.session_id or f"benchmark-fast-{int(started * 1000)}"
    evidence = {
        "mode": "benchmark-fast",
        "verification": "deferred",
        "provider": provider,
        "failures": failures,
        "webFallback": web_fallback or None,
    }
    trace = [{
        "domain": req.domain or "general",
        "slm_name": provider or "none",
        "answer": answer,
        "time_ms": round((time.time() - started) * 1000, 1),
        "source": "benchmark-fast",
        "evidence": evidence,
    }]
    return AskResponse(
        verdict="UNKNOWN" if answer else "FAIL",
        final_answer=answer or "[SCP: benchmark fast path produced no answer]",
        confidence=0.35 if answer else 0.0,
        domain=req.domain or "general",
        falsification_status="DEFERRED_BENCHMARK_FAST",
        governance_decision="DEFERRED_BENCHMARK_FAST",
        v98_guard={"mode": "benchmark-fast", "readOnly": True},
        elapsed_ms=round((time.time() - started) * 1000, 1),
        session_id=session_id,
        slm_trace=trace,
        phase_timings={"benchmark_fast_ms": round((time.time() - started) * 1000, 1)},
        reasoning="Candidate-only benchmark path; full cross-verification is deferred.",
        slm_responses=trace,
        v100_claims=None,
        v103_antibodies=None,
        speculative_mode={"enabled": True, "reason": "benchmark_fast_deferred_verification"},
        web_fallback_used=bool(web_fallback.get("success")),
        web_fallback=(web_fallback or None),
    )


def _rag_terms(value: str) -> set[str]:
    import re as _re
    return set(_re.findall(r"[\wÀ-ỹ]{4,}", (value or "").lower()))


def _ask_context_rag(req: AskRequest, request: Request) -> AskResponse:
    """Explicit read-only RAG branch for caller-supplied evidence.

    This is not a silent JudgeCore bypass: callers opt in with rag_enabled or
    supplied retrieval fields, the response declares ``rag-verified`` mode, and
    no public web/LLM fallback is allowed in this branch.
    """
    started = time.time()
    contexts = [str(value).strip() for value in (req.contexts or []) if str(value).strip()]
    if req.retrieved_context and req.retrieved_context.strip():
        contexts.append(req.retrieved_context.strip())
    answer = (req.ai_answer or "").strip()
    evidence_text = "\n".join(contexts)
    lowered = f"{evidence_text}\n{answer}".lower()
    injection_markers = (
        "ignore previous instructions",
        "ignore all previous",
        "system prompt",
        "jailbreak",
        "bỏ qua hướng dẫn",
        "bỏ qua chỉ dẫn",
    )
    session_id = req.session_id or f"rag-verified-{int(started * 1000)}"
    base_evidence = {
        "mode": "rag-verified",
        "contexts": contexts,
        "evidence_count": len(contexts),
        "ground_truth_used_for_generation": False,
        "provenance": "input_context_only",
    }
    if any(marker in lowered for marker in injection_markers):
        evidence = {**base_evidence, "security_blocked": True, "reason": "prompt_injection_marker"}
        return AskResponse(
            verdict="FAIL",
            final_answer="[SCP: Answer withheld — prompt injection in RAG evidence]",
            confidence=0.0,
            domain="security",
            falsification_status="RAG_CONTEXT_INJECTION_BLOCKED",
            governance_decision="KILL",
            v98_guard={"mode": "rag-verified", "readOnly": True, "security_blocked": True},
            v98_classification=evidence,
            elapsed_ms=round((time.time() - started) * 1000, 1),
            session_id=session_id,
            slm_trace=[],
            reasoning="RAG evidence contained an instruction-like marker; answer withheld.",
            v100_claims={"evidence": evidence},
            v103_antibodies={"injection_blocked": True},
            speculative_mode=None,
        )
    if not contexts or not answer:
        evidence = {**base_evidence, "reason": "missing_context_or_ai_answer"}
        return AskResponse(
            verdict="FAIL",
            final_answer="[SCP: Answer withheld — RAG evidence incomplete]",
            confidence=0.0,
            domain=req.domain_override or req.domain or "general",
            falsification_status="RAG_EVIDENCE_INSUFFICIENT",
            governance_decision="ESCALATE",
            v98_guard={"mode": "rag-verified", "readOnly": True, "security_blocked": False},
            v98_classification=evidence,
            elapsed_ms=round((time.time() - started) * 1000, 1),
            session_id=session_id,
            slm_trace=[],
            reasoning="RAG requires non-empty caller-supplied context and an answer candidate.",
            v100_claims={"evidence": evidence},
            v103_antibodies={"injection_blocked": False},
            speculative_mode=None,
        )
    answer_terms = _rag_terms(answer)
    evidence_terms = _rag_terms(evidence_text)
    grounded_ratio = len(answer_terms & evidence_terms) / max(1, len(answer_terms))
    truth_terms = _rag_terms(req.ground_truth)
    truth_overlap = len(answer_terms & truth_terms) / max(1, len(answer_terms)) if truth_terms else 0.0
    evidence = {
        **base_evidence,
        "grounded_ratio": round(grounded_ratio, 6),
        "ground_truth_overlap": round(truth_overlap, 6),
    }
    if grounded_ratio < 0.35:
        evidence["reason"] = "answer_not_grounded_in_input_context"
        return AskResponse(
            verdict="FAIL",
            final_answer="[SCP: Answer withheld — answer not grounded in supplied RAG evidence]",
            confidence=0.0,
            domain=req.domain_override or req.domain or "general",
            falsification_status="RAG_GROUNDING_FAILED",
            governance_decision="ESCALATE",
            v98_guard={"mode": "rag-verified", "readOnly": True, "security_blocked": False},
            v98_classification=evidence,
            elapsed_ms=round((time.time() - started) * 1000, 1),
            session_id=session_id,
            slm_trace=[],
            reasoning="Answer-token overlap did not meet the 0.35 read-only grounding threshold.",
            v100_claims={"evidence": evidence},
            v103_antibodies={"injection_blocked": False},
            speculative_mode=None,
        )
    return AskResponse(
        verdict="PASS",
        final_answer=answer,
        confidence=round(min(0.99, max(0.35, grounded_ratio)), 6),
        domain=req.domain_override or req.domain or "general",
        falsification_status="GROUNDED_CONTEXT_CHECK",
        governance_decision="UPHOLD",
        v98_guard={"mode": "rag-verified", "readOnly": True, "security_blocked": False},
        v98_classification=evidence,
        elapsed_ms=round((time.time() - started) * 1000, 1),
        session_id=session_id,
        slm_trace=[{"domain": req.domain_override or req.domain or "general", "slm_name": "deterministic-extractive-rag", "answer": answer, "evidence_count": len(contexts)}],
        reasoning="Answer accepted only because its terms are grounded in caller-supplied context.",
        v100_claims={"evidence": evidence},
        v103_antibodies={"injection_blocked": False},
        speculative_mode=None,
    )


# POST /ask Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Main endpoint
# ============================================================
@app.post("/ask", response_model=AskResponse)
@traced_request(_REQUEST_RUN_LEDGER)
async def ask(req: AskRequest, request: Request):
    if _ask_kernel_enabled(req):
        adapter = _get_ask_kernel_adapter()
        if adapter is None:
            return _kernel_gate_unavailable_response(req, _ASK_KERNEL_INIT_ERROR or RuntimeError("kernel_adapter_unavailable"))
        return await adapter.run_rag(req, request, _ask_impl)
    return await _ask_impl(req, request)


async def _ask_impl(req: AskRequest, request: Request):
    """Main endpoint Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â question Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ V98 pipeline Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ verdict.

    Pipeline:
      1. [V98] MemoryPoisoningGuard + AttackPatternMemory + ThreatDetector
      2. [V88] Route Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ SLM predict Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ RealityJudge
      3. [V97] FalsificationEngine + ErrorStore + Governance
      4. [V98] AttackPolicy + CounterResponse + Canary + AttackPatternMemory.record_bypass
    """
    t0 = time.time()
    if os.environ.get("SCP_ASK_KERNEL_ENABLED", "1") == "1" and (req.rag_enabled or req.contexts or str(req.retrieved_context or "").strip()):
        return _ask_context_rag(req, request)
    if req.source == "scp_batch_benchmark_v1":
        return await _ask_benchmark_fast(req, request)
    judge = get_judge()
    stage_request(request, "judge_ready")
    v98_context = _extract_v98_context(request)
    _web_fallback_used = False
    _web_fallback: dict = {}
    v98_context["body"] = req.question
    if req.session_id:
        v98_context["session_id"] = req.session_id
    # Keep only short, user-visible context. The current question is always
    # authoritative; history is supporting context, not an instruction source.
    _history = []
    for _turn in (req.conversation_history or [])[-8:]:
        if not isinstance(_turn, dict):
            continue
        _role = str(_turn.get("role", "user"))[:16]
        _content = str(_turn.get("content", ""))[:500].strip()
        if _content and _role in {"user", "assistant"}:
            _history.append({"role": _role, "content": _content})
    if _history:
        v98_context["conversation_history"] = _history

    # [V104.17 #1 FIX] DoS protection Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â check rate limit before processing
    if hasattr(judge, 'dos_protection') and judge.dos_protection:
        try:
            client_ip = request.client.host if request.client else "unknown"
            dos_alert = judge.dos_protection.check_request(client_ip)
            # [V104.22 #2 FIX] dos_alert may be a dataclass Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â use getattr, not .get
            # (was: .get raised AttributeError Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ swallowed Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ no block)
            action = getattr(dos_alert, "action_taken", "") if dos_alert else ""
            should_block = (
                action in ("block", "throttle")
                or (isinstance(dos_alert, dict) and dos_alert.get("should_block"))
            )
            if should_block:
                status_code = int(getattr(dos_alert, "status_code", 0) or 429)
                headers = dict(getattr(dos_alert, "recommended_headers", {}) or {})
                return JSONResponse(
                    {"error": {"message": "Rate limit exceeded", "type": "rate_limit_error"}},
                    status_code=status_code,
                    headers=headers,
                )
        except Exception as e:
            logger.debug(f"[V104.17] DoS check error: {e}")

    # [V104.45 #CP] Multimodal input is checked BEFORE judge.
    # URLs use the SSRF-safe fetcher. Browser webcam data is accepted only as a
    # bounded data URL and never written to disk.
    # [FIX-A P0-2] Was urllib.request.urlopen(req.image_url) â€” accepted
    # file:///etc/passwd (LFI), http://169.254.169.254/... (cloud metadata
    # SSRF), internal IPs, followed redirects, no size cap, AND blocked the
    # event loop. Now: _safe_fetch_url (scheme/IP/redirect/size defenses) +
    # asyncio.to_thread (non-blocking). Voice path was also broken (called
    # detect(audio_url=...) which has no such kwarg) Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â now fetches bytes safely
    # and passes audio_bytes=... to the detector.
    _multimodal_block = False
    _img_bytes = None
    if req.image_data:
        try:
            _raw_image = req.image_data
            if "," in _raw_image and _raw_image.lower().startswith("data:"):
                _raw_image = _raw_image.split(",", 1)[1]
            _img_bytes = base64.b64decode(_raw_image, validate=True)
            if not _img_bytes or len(_img_bytes) > 6_000_000:
                raise ValueError("image_too_large_or_empty")
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=400, detail="Invalid or oversized image_data") from None
    if req.image_url and _img_bytes is None:
        try:
            _img_bytes = await asyncio.to_thread(_safe_fetch_url, req.image_url)
        except ValueError:
            # SSRF/LFI policy violation Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â reject with 400 (do NOT echo URL).
            logger.warning("[V104.45 #CP] /ask image_url rejected by _safe_fetch_url policy")
            raise HTTPException(status_code=400, detail="Invalid or disallowed image_url") from None
        except Exception as e:
            logger.debug(f"[V104.45 #CP] Image fetch error: {e}")
            _img_bytes = None
        if _img_bytes:
            try:
                _img_result = _image_detector.detect(image_bytes=_img_bytes)
                if _img_result and _img_result.jailbreak_detected:
                    logger.warning("[V104.45 #CP] Image jailbreak detected on /ask")
                    _multimodal_block = True
            except Exception as e:
                logger.debug(f"[V104.45 #CP] Image detect error: {e}")

    if req.voice_url:
        try:
            _voice_bytes = await asyncio.to_thread(_safe_fetch_url, req.voice_url)
        except ValueError:
            logger.warning("[V104.45 #CP] /ask voice_url rejected by _safe_fetch_url policy")
            raise HTTPException(status_code=400, detail="Invalid or disallowed voice_url") from None
        except Exception as e:
            logger.debug(f"[V104.45 #CP] Voice fetch error: {e}")
            _voice_bytes = None
        if _voice_bytes:
            try:
                _voice_result = _voice_detector.detect(audio_bytes=_voice_bytes)
                if _voice_result and _voice_result.jailbreak_detected:
                    logger.warning("[V104.45 #CP] Voice jailbreak detected on /ask")
                    _multimodal_block = True
            except Exception as e:
                logger.debug(f"[V104.45 #CP] Voice detect error: {e}")

    if _multimodal_block:
        return AskResponse(
            verdict="FAIL",
            final_answer="[SCP: Answer withheld Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â multimodal jailbreak detected]",
            confidence=0.0,
            domain="security",
            elapsed_ms=0,
            session_id=v98_context["session_id"],
        )

    # [CHATBOT-FIX] NÄ‚Â¡Ă‚ÂºĂ‚Â¿u user khĂ„â€Ă‚Â´ng cung cÄ‚Â¡Ă‚ÂºĂ‚Â¥p ai_answer Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ gÄ‚Â¡Ă‚Â»Ă‚Âi Ollama sinh cĂ„â€Ă‚Â¢u trÄ‚Â¡Ă‚ÂºĂ‚Â£ lÄ‚Â¡Ă‚Â»Ă‚Âi
    # TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: SCP thiÄ‚Â¡Ă‚ÂºĂ‚Â¿t kÄ‚Â¡Ă‚ÂºĂ‚Â¿ Ä‚â€Ă¢â‚¬ËœÄ‚Â¡Ă‚Â»Ă†â€™ verify AI answer, nhÄ‚â€ Ă‚Â°ng chat UI chÄ‚Â¡Ă‚Â»Ă¢â‚¬Â° gÄ‚Â¡Ă‚Â»Ă‚Â­i question (khĂ„â€Ă‚Â´ng ai_answer)
    # Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ SLM khĂ„â€Ă‚Â´ng cĂ„â€Ă‚Â³ gĂ„â€Ă‚Â¬ verify Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ UNKNOWN/KILL
    # Fix: GÄ‚Â¡Ă‚Â»Ă‚Âi Ollama local (llama3.2) sinh cĂ„â€Ă‚Â¢u trÄ‚Â¡Ă‚ÂºĂ‚Â£ lÄ‚Â¡Ă‚Â»Ă‚Âi nhÄ‚â€ Ă‚Â° chatbot, rÄ‚Â¡Ă‚Â»Ă¢â‚¬Å“i SCP verify
    # [ROOT-FIX 44-A] task="chat" Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ routes to llama3.2 (fastest Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â 3B model, low latency
    # for chat UI responsiveness).
    # [SCP-DNA-FIX 4-a-016] TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: previously `if req is not None: _ai_answer = req.ai_answer
    # else: _ai_answer = None`. FastAPI's `req: AskRequest` parameter is ALWAYS a valid
    # AskRequest Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Pydantic 422s on invalid body before the handler runs. So `req is None`
    # is impossible Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ the else branch was dead code (DNA #22: PASSÄ‚Â¢Ă¢â‚¬Â°Ă‚Â TRUE Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â code suggested
    # null handling but the branch was unreachable). Fix: inline the assignment.
    _ai_answer = req.ai_answer
    if not _ai_answer or not _ai_answer.strip():
        try:
            # R9-4: was `from scp.llm_gateway import chat_sync; chat_sync(...)`.
            # chat_sync() detects it's inside an async context (event loop
            # running) and uses ThreadPoolExecutor + future.result(timeout=90)
            # Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â a SYNCHRONOUS BLOCKING CALL on the event loop thread. While
            # Ollama generates the response (60-90s) the entire event loop
            # is frozen Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â /health, /ask, WebSocket all hang. Fix: call the
            # async chat() method directly with `await` (httpx.AsyncClient
            # internally Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â true non-blocking I/O).
            from scp.llm_gateway import get_gateway
            _gateway = get_gateway()
            _ollama_answer, _provider = await _gateway.chat(
                    req.question,
                    context=("Lá»‹ch sá»­ gáº§n Ä‘Ă¢y (chá»‰ Ä‘á»ƒ tham kháº£o):\n" + "\n".join(
                        f"{t['role']}: {t['content']}" for t in _history
                    )) if _history else "",
                    system_prompt=(
                        "Báº¡n lĂ  SCP â€” má»™t trá»£ lĂ½ AI thĂ´ng minh. Tráº£ lá»i ngáº¯n gá»n, chĂ­nh xĂ¡c, báº±ng tiáº¿ng Viá»‡t. "
                        "Chá»‰ tráº£ lá»i cĂ¢u há»i HIá»†N Táº I á»Ÿ cuá»‘i yĂªu cáº§u. KhĂ´ng tiáº¿p tá»¥c chá»§ Ä‘á» cÅ© náº¿u cĂ¢u há»i má»›i Ä‘á»•i chá»§ Ä‘á». "
                        "Náº¿u thiáº¿u dá»¯ liá»‡u, nĂ³i rĂµ chÆ°a Ä‘á»§ dá»¯ liá»‡u thay vĂ¬ Ä‘oĂ¡n."
                    ),
                    task="chat",

            )
            if _ollama_answer:
                _ai_answer = _ollama_answer
                logger.info(f"[CHATBOT] Ollama ({_provider}) generated answer: {_ollama_answer[:80]}...")
        except Exception as _ollama_err:
            logger.warning(f"[CHATBOT] Ollama call failed: {_ollama_err}")
            # A model/API timeout is not a reason to stop evidence retrieval.
            # This fallback is retrieval-only: public snippets are untrusted
            # data, never executable instructions and never treated as truth.
            if os.environ.get("SCP_WEB_FALLBACK", "1") == "1":
                try:
                    _web_timeout = min(float(os.environ.get("SCP_WEB_FALLBACK_TIMEOUT", "8")), 12.0)
                    _web_search = InternetSearch(timeout=min(_web_timeout / 2.0, 4.0))
                    _web_fallback = await asyncio.wait_for(
                        _web_search.search(req.question, max_results=6),
                        timeout=_web_timeout,
                    )
                    _web_fallback_used = bool(_web_fallback.get("success"))
                    _web_fallback["trigger"] = "llm_timeout_or_error"
                    _web_fallback["llm_error"] = str(_ollama_err)[:240]
                    if _web_fallback_used:
                        _snippets = []
                        for _item in _web_fallback.get("results", [])[:6]:
                            _title = str(_item.get("title", "")).strip()
                            _snippet = str(_item.get("snippet", "")).strip()
                            _url = str(_item.get("url", "")).strip()
                            _snippets.append(f"- {_title}: {_snippet} ({_url})")
                        _ai_answer = (
                            "[SCP public-web evidence; untrusted, requires verification]\n"
                            + "\n".join(_snippets)
                        )
                        v98_context["web_fallback"] = _web_fallback
                    else:
                        logger.warning("[CHATBOT] Public web fallback returned no result: %s", _web_fallback.get("errors"))
                except Exception as _web_err:
                    _web_fallback = {"success": False, "method": "public-search", "error": str(_web_err)[:240]}
                    logger.warning("[CHATBOT] Public web fallback failed: %s", _web_err)
            # Fallback: khĂ„â€Ă‚Â´ng cĂ„â€Ă‚Â³ ai_answer Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ SCP chÄ‚Â¡Ă‚ÂºĂ‚Â¡y SLM-only (old behavior)

    # [Task 34-A / OPT-22] AsyncMultiSourceVerifier Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â pre-judge fact check.
    # TĂ„â€Ă‚ÂI SAO: Task 33-A created AsyncMultiSourceVerifier but it was NOT used
    # in /ask. The verifier was tested in isolation but never wired into the
    # production hot path. DNA SCP #1 (Reality > Model) + #6 (Evidence)
    # violated: when a user asks "is X true?", the judge ran without first
    # checking what independent fact-check sources (Google Fact Check API,
    # 100+ publishers) had already concluded.
    #
    # Fix (additive Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â only triggers for fact-check questions):
    #   1. Detect fact-check intent via keyword match (en + vi).
    #   2. Pull sources from DataSourceRegistry that can_handle("fact_check").
    #   3. Run AsyncMultiSourceVerifier.verify_async() in PARALLEL Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â N sources
    #      Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ ~1Ă„â€Ă¢â‚¬â€ latency instead of NĂ„â€Ă¢â‚¬â€.
    #   4. Interpret each source's verdict (GoogleFactCheck returns
    #      metadata.consensus="FALSE"/"TRUE"/"MIXED" Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â translated to
    #      contradicted/verified so the aggregator's consensus reflects it).
    #   5. If consensus == "contradicted" Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ pass fact_check_hint to judge
    #      via v98_context (judge can use it to downgrade confidence /
    #      override verdict Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â additive, judge remains in charge).
    #
    # Backward compat: any exception Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ silently fall through to judge (the
    # existing path is unchanged). No new dependency on a specific source
    # being enabled Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â if no fact-check sources can handle the question,
    # verify_async() returns consensus="unclear" and the hint is not set.
    _q_lower = req.question.lower() if req.question else ""
    _FACT_CHECK_KEYWORDS = (
        "true or false", "fact check", "is it true", "fact-check",
        "cĂ„â€Ă‚Â³ thÄ‚Â¡Ă‚ÂºĂ‚Â­t", "Ä‚â€Ă¢â‚¬ËœĂ„â€Ă‚Âºng khĂ„â€Ă‚Â´ng", "cĂ„â€Ă‚Â³ thÄ‚Â¡Ă‚ÂºĂ‚Â­t khĂ„â€Ă‚Â´ng", "kiÄ‚Â¡Ă‚Â»Ă†â€™m chÄ‚Â¡Ă‚Â»Ă‚Â©ng",
        "real or fake", "verify this claim",
    )
    if any(kw in _q_lower for kw in _FACT_CHECK_KEYWORDS):
        try:
            from scp.core.multi_source_verifier import AsyncMultiSourceVerifier
            from scp.data_sources import get_registry

            # Pull sources that self-report fact-check capability. Each source's
            # `can_handle(intent="fact_check")` decides Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â disabled sources
            # (e.g. GoogleFactCheck without API key) return False and are skipped.
            # Use the registry's public API (`get_sources_for_intent`) plus a
            # final can_handle() guard so disabled sources don't waste a slot.
            _fc_sources = []
            try:
                _registry = get_registry()
                _candidates = []
                try:
                    _candidates = _registry.get_sources_for_intent("fact_check") or []
                except Exception:
                    # Older registries without get_sources_for_intent Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â fall back
                    # to iterating the internal dict (mirrors SourceWatchlist
                    # pattern in judge.py:345).
                    _candidates = list(getattr(_registry, "_sources", {}).values())
                for _src in _candidates:
                    try:
                        if _src.can_handle("fact_check"):
                            _fc_sources.append(_src)
                    except Exception:  # noqa: S112
                        continue
            except Exception as _reg_err:
                logger.debug(f"[OPT-22] registry lookup failed: {_reg_err}")

            async_verifier = AsyncMultiSourceVerifier()
            fact_result = await async_verifier.verify_async(
                req.question, sources=_fc_sources or None
            )

            # [OPT-22b] Translate per-source verdicts (GoogleFactCheck returns
            # metadata.consensus="FALSE"/"TRUE"/"MIXED" Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â the aggregator only
            # counts `verified`/`contradicted` keys, so consensus is "unclear"
            # unless we synthesize these keys). Map FALSE Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ contradicted,
            # TRUE Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ verified, then recompute consensus.
            _extra_verified = 0
            _extra_contradicted = 0
            for _raw in fact_result.get("results", []) or []:
                try:
                    _meta = _raw.get("metadata", {}) if isinstance(_raw, dict) else {}
                    _verdict = (str(_meta.get("consensus", "")).upper()
                                if _meta else "")
                    if _verdict == "FALSE":
                        _extra_contradicted += 1
                    elif _verdict == "TRUE":
                        _extra_verified += 1
                except Exception:  # noqa: S112
                    continue
            if _extra_verified or _extra_contradicted:
                fact_result["verified"] = fact_result.get("verified", 0) + _extra_verified
                fact_result["contradicted"] = fact_result.get("contradicted", 0) + _extra_contradicted
                if fact_result["contradicted"] > fact_result["verified"]:
                    fact_result["consensus"] = "contradicted"
                elif fact_result["verified"] > fact_result["contradicted"]:
                    fact_result["consensus"] = "verified"
                # else: keep "unclear" (tie)

            if fact_result.get("consensus") == "contradicted":
                logger.info(
                    f"[OPT-22] Pre-judge fact check: claim contradicted by "
                    f"{fact_result.get('contradicted', 0)} sources "
                    f"(sources_checked={fact_result.get('sources_checked', 0)})"
                )
                v98_context["fact_check_hint"] = fact_result
            elif fact_result.get("consensus") == "verified":
                logger.info(
                    f"[OPT-22] Pre-judge fact check: claim verified by "
                    f"{fact_result.get('verified', 0)} sources "
                    f"(sources_checked={fact_result.get('sources_checked', 0)})"
                )
                v98_context["fact_check_hint"] = fact_result
        except Exception as e:
            logger.debug(f"[OPT-22] async fact check failed: {e}")

    # [OPT-8/9] Use async judge with ReActAgent fallback.
    # Was: asyncio.to_thread(judge.judge, ...) Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â blocked event loop thread.
    # Now: judge_with_react_fallback() Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â async LLM call + ReActAgent when
    # SmartClassifier confidence < 0.5. Falls back to sync judge() on error.
    stage_request(request, "verifier_started")
    if hasattr(judge, "judge_with_react_fallback"):
        v = await judge.judge_with_react_fallback(
            question=req.question,
            ai_answer=_ai_answer,
            cycle_count=0,
            source=req.source,
            v98_context=v98_context,
        )
    else:
        # Fallback for older judge instances without async method
        v = await asyncio.to_thread(
            judge.judge,
            question=req.question,
            ai_answer=_ai_answer,
            cycle_count=0,
            source=req.source,
            v98_context=v98_context,
        )
    stage_request(request, "verifier_completed", verdict=v.verdict, governance_decision=v.evidence.get("governance_decision", ""))

    # [V104.41 #AC] TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: DoS record_verdict never called Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ verdict-quality circuit dead.
    # Fix: record verdict after judge completes (same as OpenAI path).
    if hasattr(judge, 'dos_protection') and judge.dos_protection:
        try:
            judge.dos_protection.record_verdict(v.verdict)
        except Exception as e:
            logger.debug(f"[V104.41 #AC] DoS record_verdict error: {e}")

    # [FIX-CRIT-46 BUG 2] TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: observe() was called with wrong kwargs
    # (response=, verdict=, confidence=, domain=) but ResponseMonitor.observe
    # signature is (prompt, response, latency_ms). TypeError was swallowed by
    # `except Exception` Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ behavioral detection stayed dead even after BUG 1
    # init fix. Fix: match actual signature Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â pass the prompt + latency_ms.
    elapsed_ms = (time.time() - t0) * 1000
    if hasattr(judge, 'response_monitor') and judge.response_monitor:
        try:
            judge.response_monitor.observe(
                prompt=req.question,
                response=v.final_answer or "",
                latency_ms=elapsed_ms,
            )
        except Exception as e:
            logger.debug(f"[V104.41 #AD] ResponseMonitor observe error: {e}")

    # Build SLM trace Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â which SLMs ran, their answers, timing
    slm_trace = []
    for r in v.slm_responses:
        slm_trace.append({
            "domain": r.get("domain", "?"),
            "slm_name": r.get("slm_name", r.get("domain", "?")),
            "answer": str(r.get("answer", ""))[:200],
            "confidence": r.get("confidence", 0),
            "source": r.get("evidence", {}).get("source", "?") if isinstance(r.get("evidence"), dict) else "?",
            "evidence": r.get("evidence", {}) if isinstance(r.get("evidence"), dict) else {},
            "processing_time_ms": r.get("processing_time", 0),
        })

    # Extract phase timings
    phase_timings = v.evidence.get("v100_phase_timings", {})

    # ===== V104 FIX: Multi-turn tracking (0.1ms, sync, OK trong pipeline) =====
    mt_result = None
    _mt_session = req.session_id or v98_context.get("session_id", "")
    if _mt_session:
        mt_result = _multi_turn_tracker.track(_mt_session, req.question, v.verdict)
        if mt_result.suspicious:
            # [V104.17 #6 FIX] Flag all verdicts (was: only PASS)
            if v.verdict in ("PASS", "FAIL", "UNKNOWN", "PARTIAL"):
                v.verdict = "FLAGGED"
                v.confidence *= 0.5
                if v.reasoning:
                    v.reasoning += f" [V104 Multi-turn: {mt_result.pattern_type}]"
            logger.warning(
                f"V104 Multi-turn attack: session={_mt_session}, "
                f"pattern={mt_result.pattern_type}, reason={mt_result.reason}"
            )
            v98_context["v104_multi_turn"] = mt_result.__dict__

    # ===== V104 FIX: Simple explanation (0.1ms, sync, OK) =====
    has_attack = bool(v98_context.get("v99_vietnamese_attack"))
    has_bypass = bool(v.evidence.get("v100_bypass_detected"))
    has_human_review = bool(v.evidence.get("v102_human_review_pending"))
    source_count = len([r for r in v.slm_responses if r.get("answer")])
    _simple_explainer.explain(
        verdict=v.verdict,
        confidence=v.confidence,
        domain=v.domain or "",
        sources=source_count,
        has_attack=has_attack,
        has_bypass=has_bypass,
        has_human_review=has_human_review,
        lineage_overlap=0.0,
        reliability_factor=v.evidence.get("v102_reliability_factor", 1.0),
    )

    # ===== V104.41 #X: Enforce KILL/FAIL/FLAGGED at API boundary =====
    # TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: was always returning v.final_answer regardless of verdict.
    # Constitution: "abstain rather than fabricate". OpenAI path already had
    # "I cannot comply" for FAIL, but /ask returned full content.
    # Fix: clear answer for FAIL/FLAGGED/KILL; warn for UNKNOWN.
    _api_final_answer = v.final_answer
    _gov_decision = v.evidence.get("governance_decision", "")
    # [FIX-CRIT-27 BUG 6] Previously only `final_answer` was cleared on abstain Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â
    # but `slm_responses`, `slm_trace`, `reasoning`, `v100_claims`, `v103_antibodies`,
    # `speculative_mode`, and `v98_canary_token` still leaked the same content via
    # other fields. The abstain was cosmetic. Now: clear ALL leak fields on
    # FAIL/KILL/FLAGGED.
    _api_slm_responses = [{k: str(v2)[:200] for k, v2 in r.items()} for r in v.slm_responses]
    _api_slm_trace = slm_trace
    _api_reasoning = v.reasoning[:500] if v.reasoning else None
    _api_v100_claims = v.evidence.get("v100_claims")
    _api_v103_antibodies = v.evidence.get("v103_antibodies")
    _api_speculative_mode = v.evidence.get("speculative_mode")
    _api_v98_canary_token = v.evidence.get("v98_canary_token")
    _api_v98_guard = v.evidence.get("v98_guard_verdict") or v.evidence.get("v98_guard")
    _api_v98_classification = v.evidence.get("v98_classification")
    _api_v98_attack_policy = v.evidence.get("v98_attack_policy")
    _api_v98_counter_executed = v.evidence.get("v98_counter_executed")
    _api_v98_bypass_recorded = v.evidence.get("v98_bypass_recorded")
    _api_falsification_status = v.evidence.get("falsification_status")
    if _gov_decision == "KILL" or v.verdict in ("FAIL", "FLAGGED"):
        # [V104.41 #X] Don't return killed/failed content to client
        _api_final_answer = f"[SCP: Answer withheld Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â verdict: {v.verdict}]"
        if _gov_decision == "KILL":
            _api_final_answer = "[SCP: Answer withheld Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Governance KILL]"
        # [FIX-CRIT-27 BUG 6] Clear ALL leak fields Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â abstain must be total.
        _api_slm_responses = []
        _api_slm_trace = []
        _api_reasoning = "[SCP: Answer withheld]"
        _api_v100_claims = None
        _api_v103_antibodies = None
        _api_speculative_mode = None
        _api_v98_canary_token = None  # honeypot Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â must not leak
        _api_v98_guard = None
        _api_v98_classification = None
        _api_v98_attack_policy = None
        _api_v98_counter_executed = None
        _api_v98_bypass_recorded = None
        _api_falsification_status = None
        logger.info(f"[V104.41 #X] API boundary enforcing abstain (all fields cleared): verdict={v.verdict}, gov={_gov_decision}")
    elif v.verdict == "UNKNOWN" and v.evidence.get("why_gate", {}).get("decision") == "REJECT":
        # [FIX-1] WHY Gate blocked PASS Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ UNKNOWN. Treat like FAIL/KILL:
        # withhold answer + clear all leak fields. Without this the WHY block
        # in judge.py was cosmetic Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â final_answer still shipped to client.
        _api_final_answer = "[SCP: Answer withheld Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â WHY Gate blocked]"
        _api_slm_responses = []
        _api_slm_trace = []
        _api_reasoning = "[SCP: WHY Gate blocked]"
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
        logger.info(f"[FIX-1] API boundary enforcing WHY Gate block (all fields cleared): verdict={v.verdict}")
    elif v.verdict == "UNKNOWN":
        # [V104.41 #X] For UNKNOWN, append warning but keep answer (low-risk)
        if _api_final_answer and "[SCP: unverified]" not in _api_final_answer:
            # [CHATBOT-FIX] ThĂ„â€Ă‚Âªm explanation chi tiÄ‚Â¡Ă‚ÂºĂ‚Â¿t cho chatbot
            _sources = []
            for r in v.slm_responses:
                if r.get("answer"):
                    _sources.append(f"  Ä‚Â¢Ă¢â€Â¬Ă‚Â¢ {r.get('slm_name','?')}: {str(r.get('answer',''))[:60]}")
            _source_text = "\n".join(_sources) if _sources else "  (khĂ„â€Ă‚Â´ng cĂ„â€Ă‚Â³ SLM nĂ„â€Ă‚Â o trÄ‚Â¡Ă‚ÂºĂ‚Â£ lÄ‚Â¡Ă‚Â»Ă‚Âi)"
            _api_final_answer = str(_api_final_answer) + str(f"\n\nĂ„â€˜Ă…Â¸Ă¢â‚¬â„¢Ă‚Â¡ SCP Ä‚â€Ă¢â‚¬ËœĂ„â€Ă‚Â£ kiÄ‚Â¡Ă‚Â»Ă†â€™m tra:\n{_source_text}\nĂ„â€˜Ă…Â¸Ă¢â‚¬Å“Ă‚Â Confidence: {v.confidence:.0%} Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â chÄ‚â€ Ă‚Â°a Ä‚â€Ă¢â‚¬ËœÄ‚Â¡Ă‚Â»Ă‚Â§ ngÄ‚â€ Ă‚Â°Ä‚Â¡Ă‚Â»Ă‚Â¡ng (cÄ‚Â¡Ă‚ÂºĂ‚Â§n Ä‚Â¢Ă¢â‚¬Â°Ă‚Â¥70%)")

    # ===== V104 FIX: Fact-check ASYNC (background, KHĂ„â€Ă¢â‚¬ÂNG block /ask) =====
    # [V104.41 #Z] Only fact-check if we're actually returning an answer (not abstained)
    if v.verdict == "PASS" and _api_final_answer and len(_api_final_answer) > 20:
        try:
            # [SCP-DNA-FIX / RUF006] Hold a strong reference so the GC cannot
            # collect the task before it completes. The done-callback discards
            # the ref once the task finishes (success or exception), so the set
            # does not grow without bound.
            _fc_task = asyncio.create_task(
                _async_fact_check(_api_final_answer, req.question, v98_context.get("session_id", ""))
            )
            _async_factcheck_tasks.add(_fc_task)
            _fc_task.add_done_callback(_async_factcheck_tasks.discard)
        except Exception as e:
            logger.debug(f"[V104.37] api_server.py: e={e}")

    stage_request(request, "response_boundary", verdict=v.verdict, governance_decision=_gov_decision)
    if _web_fallback_used:
        _api_slm_trace.append({
            "domain": v.domain,
            "slm_name": "public_web_search",
            "answer": "retrieved public snippets",
            "time_ms": None,
            "source": "public-search",
            "evidence": _web_fallback,
        })
    return AskResponse(
        verdict=v.verdict,
        final_answer=_api_final_answer,  # [V104.41 #X] enforced answer
        confidence=v.confidence,
        domain=v.domain,
        falsification_status=_api_falsification_status,
        governance_decision=v.evidence.get("governance_decision"),
        v98_guard=_api_v98_guard,
        v98_classification=_api_v98_classification,
        v98_attack_policy=_api_v98_attack_policy,
        v98_counter_executed=_api_v98_counter_executed,
        v98_canary_token=_api_v98_canary_token,
        v98_bypass_recorded=_api_v98_bypass_recorded,
        elapsed_ms=round(elapsed_ms, 1),
        session_id=v98_context["session_id"],
        # V105: Full pipeline trace
        slm_trace=_api_slm_trace,
        phase_timings=phase_timings,
        reasoning=_api_reasoning,
        slm_responses=_api_slm_responses,
        v100_claims=_api_v100_claims,
        v103_antibodies=_api_v103_antibodies,
        speculative_mode=_api_speculative_mode,
        web_fallback_used=_web_fallback_used,
        web_fallback=(_web_fallback or None),
    )


# ===== V104: Async fact-check helper (background, khĂ„â€Ă‚Â´ng block /ask) =====
# [V104.45 #Z] TÄ‚Â¡Ă‚ÂºĂ‚Â I SAO: fact-check was post-hoc only Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â FALSE claims logged but
# answer already sent to client. Fix: retract queue Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â if FALSE claims found,
# mark the answer as retracted in a queue that clients can poll.
_fact_check_retract_queue: deque[dict] = deque(maxlen=1000)  # in-memory retract queue (cap 1000) Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Fix 4-a-018


async def _async_fact_check(answer: str, question: str, session_id: str = ""):
    """Run fact-check in background Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â update stats + queue retract if FALSE."""
    try:
        results = await _fact_checker.check_text(answer[:500], question)
        if results:
            false_claims = [r for r in results if r.verdict == "FALSE"]
            if false_claims:
                logger.warning(
                    f"[V104.45 #Z] FactCheck: {len(false_claims)} FALSE claims found "
                    f"in answer to '{question[:50]}' Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â queuing retract"
                )
                # [V104.45 #Z] Add to retract queue
                # [Fix 4-a-018] deque(maxlen=1000) auto-drops the oldest entry
                # when the queue is full Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â no need for separate len check +
                # pop(0). The old pop(0) was O(N) per call (copies every
                # element after the popped index). deque.popleft is O(1),
                # but with maxlen=1000 we don't even need to call popleft
                # explicitly Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â append() auto-evicts the oldest entry.
                _fact_check_retract_queue.append({
                    "question": question[:200],
                    "answer": answer[:200],
                    "false_claims": len(false_claims),
                    "session_id": session_id,
                    "timestamp": time.time(),
                })
                # Cap queue at 1000 Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â handled by deque(maxlen=1000) above.
    except Exception as e:
        logger.debug(f"V104 async fact-check error: {e}")


# ============================================================
# POST /v1/chat/completions Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â OpenAI-compatible (for PyRIT/garak)
# ============================================================




# ============================================================
# V102+V103 ENDPOINTS (V98 + V100 routes extracted to api/routes/ Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Task 7-A)
# ============================================================











# ============================================================
# IMPORT Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Excel/JSONL file upload
# ============================================================







# ============================================================
# Dashboard + Health + Root
# ============================================================
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """HTML dashboard Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â real-time V98 stats."""
    return HTMLResponse(DASHBOARD_HTML)


# ============================================================
# V103 NEW: Attack Crawler endpoints
# ============================================================






@app.get("/health")
async def health():
    # [R17-ROOT-FIX-9] /health MUST return 200 immediately when server binds port.
    # BEFORE: /health called get_judge() which triggers full init (FastLearning,
    #   LLM calls, etc.) Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ if OpenRouter 429 Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ init hangs Ä‚Â¢Ă¢â‚¬Â Ă¢â‚¬â„¢ /health 503 forever.
    #   Benchmark cannot connect even though server process is alive.
    # AFTER: /health returns 200 immediately with minimal info. Detailed status
    #   available via /health/detailed (which CAN call get_judge).
    # DNA #7 (Autofix safe) + #26 (Reality > Model): server alive = 200, not
    #   "wait for all subsystems to be perfect".
    import os as _os
    return {
        "status": "ok",
        "service_identity": _scp_service_identity(),
        "version": _SCP_VERSION,
        "release": public_release_metadata(),
        "routes": len(app.routes),
        "modules": "136+ Python files",
        "note": "minimal health Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â use /health/detailed for full status",
    }


@app.get("/health/detailed")
async def health_detailed():
    """Detailed health check Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â calls get_judge() (may be slow if init in progress)."""
    try:
        judge = get_judge()
        import os as _os
        data_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "data")
        db_size = 0
        if _os.path.exists(data_dir):
            for f in _os.listdir(data_dir):
                fp = _os.path.join(data_dir, f)
                if _os.path.isfile(fp):
                    db_size += _os.path.getsize(fp)
        # [4-a-001] Expose background_scheduler_started flag Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â operators MUST be
        # able to verify ThreatSimulator (6h) + IntelCrawler (12h) actually
        # started. DNA #22 (PASSÄ‚Â¢Ă¢â‚¬Â°Ă‚Â TRUE): prior code logged "started" but the
        # scheduler never ran (NameError swallowed). Now /health/detailed is
        # the reality check.
        _sched_started = getattr(app.state, "background_scheduler_started", False)
        return {
            "status": "ok",
            "version": _SCP_VERSION,
            "release": public_release_metadata(),
            "domain_experts": len(judge.domain_experts),
            "slms": len(judge.domain_experts),
            "v98_modules": sum(1 for v in judge.get_v98_status().values() if v != "inactive"),
            "routes": len(app.routes),
            "modules": "136+ Python files",
            "data_size_mb": round(db_size / (1024*1024), 2),
            "multi_turn_tracker": _multi_turn_tracker.stats(),
            "cross_language": _cross_language_learner.stats(),
            "fact_checker": _fact_checker.stats(),
            "runtime_routing": {
                "math_probe_route": list(judge._route_question("2+2")),
                "domain_expert_loaded": "math" in judge.domain_experts,
                "math_slm_loaded": "math" in judge.slms,
            },
            "background_scheduler_started": _sched_started,
        }
    except Exception as e:
        # If get_judge() fails (init in progress), still return 200 with error detail
        _sched_started = getattr(app.state, "background_scheduler_started", False)
        return {
            "status": "initializing",
            "version": _SCP_VERSION,
            "routes": len(app.routes),
            "error": str(e)[:200],
            "background_scheduler_started": _sched_started,
            "note": "judge init in progress Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â /health returns ok, /ask may be slow",
        }


# ============================================================
# V104 NEW: Multi-turn + Image/Voice + Cross-language + SSE + Explain
# ============================================================




























# ============================================================
# V104.2 NEW: Fast Learning (Parallel + Skip-Known + Compounding)
# ============================================================







@app.get("/")
async def root():
    return {
        "name": "SCP",
        "version": _SCP_VERSION,  # [FIX-12] single source
        "description": "Self-Correcting Pipeline with V98 security",
        "endpoints": [
            "POST /ask",
            "POST /v1/chat/completions",
            "GET  /v1/models",
            "POST /v98/analyze-session",
            "POST /v98/run-simulation",
            "POST /v98/run-intel-crawl",
            "GET  /v98/status",
            "GET  /v98/counter/stats",
            "GET  /v98/canary/triggers",
            "GET  /v98/error-store/stats",
            "GET  /v98/attack-memory/stats",
            "GET  /dashboard",
            "GET  /health",
        ],
    }


# ============================================================
# Dashboard HTML
# ============================================================


# ============================================================
# [ARCH-2] AutoFix Permission Management Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â human reviews logic bug fixes
# ============================================================












# ============================================================
# Entry point Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â direct execution (python3 scp/api_server.py)
# For normal use, prefer: python3 -m scp [port]
# (scp/__main__.py reads SCP_PORT/SCP_HOST env vars)
# ============================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "scp.api_server:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )
# SCP Hands v3.2 Ă„â€Ă‚Â¢Ä‚Â¢Ă¢â‚¬ÂĂ‚Â¬Ä‚Â¢Ă¢â€Â¬Ă‚Â action fabric
try:
    from scp.api.routes.hands_routes import router as hands_router
    app.include_router(hands_router)
    from scp.api.routes.batch_benchmark_routes import router as batch_benchmark_router
    app.include_router(batch_benchmark_router)
    _HANDS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"[SCP Hands v3.2] Hands router unavailable: {e}")
    _HANDS_AVAILABLE = False

# SCP Agent Orchestrator: proposal-only planning, bounded tool execution and
# approval resume. The router is local-only by default and does not replace the
# legacy chat/judge path until its reality contract is verified.
try:
    from scp.api.routes.agent_routes import router as agent_router
    app.include_router(agent_router)
    _AGENT_ORCHESTRATOR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"[SCP Agent] Agent orchestrator router unavailable: {e}")
    _AGENT_ORCHESTRATOR_AVAILABLE = False

# SCP local WebRTC signaling: relay-only, bounded, no media storage.
try:
    from scp.api.routes.call_routes import router as call_router
    app.include_router(call_router)
    _CALL_SIGNALING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"[SCP Call] Call signaling router unavailable: {e}")
    _CALL_SIGNALING_AVAILABLE = False

# Optional OpenTelemetry HTTP traces. Disabled unless explicitly configured.
try:
    from scp.observability.otel import configure_fastapi_otel
    _OTEL_STATUS = configure_fastapi_otel(app)
    if _OTEL_STATUS.get("enabled"):
        logger.info("[OTel] FastAPI tracing enabled without request-body/header capture")
    else:
        logger.info("[OTel] tracing disabled: %s", _OTEL_STATUS.get("reason", "not configured"))
except Exception as e:
    _OTEL_STATUS = {"enabled": False, "reason": type(e).__name__}
    logger.warning("[OTel] optional instrumentation unavailable: %s", type(e).__name__)
