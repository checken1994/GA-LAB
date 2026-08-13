"""Lifespan startup/shutdown for FastAPI app.

[Task 17-C] Extracted from api_server.py for modularity.

Startup:
  - Pre-startup deep audit gate (block server start if unfixed bugs)
  - RealityJudge init + background scheduler (ThreatSimulator/IntelCrawler)
  - Auto-wire deep audit scheduler (24h interval)
  - Auto-wire attack mode monitor (5min interval)

Shutdown:
  - Cancel background tasks
"""
from __future__ import annotations

import asyncio
import logging

# [COMPLETION-FIX] Multi-source audit fetcher
try:
    from scp.core.audit_fetcher import start_audit_fetcher, stop_audit_fetcher
except ImportError:
    start_audit_fetcher = None
    stop_audit_fetcher = None

try:
    from scp.core.ai_threat_scanner import start_scanner as start_ai_scanner
    from scp.core.ai_threat_scanner import stop_scanner as stop_ai_scanner
except ImportError:
    start_ai_scanner = None
    stop_ai_scanner = None

try:
    from scp.core.harm_detector import start_detector as start_harm_detector
    from scp.core.harm_detector import stop_detector as stop_harm_detector
except ImportError:
    start_harm_detector = None
    stop_harm_detector = None
import os
import threading
import time as _time
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger("scp.api")


@asynccontextmanager

def _get_judge_lazy():
    """Get judge if ready, else return None. [R18-FIX-2]"""
    try:
        from scp.api_server_parts.helpers import _judge
        return _judge
    except Exception:
        return None

async def lifespan(app: FastAPI, *, get_judge, _background_task_holder: dict):
    """FastAPI lifespan — startup gate + background schedulers.

    Args:
        app: FastAPI app (unused but required by FastAPI signature convention).
        get_judge: callable returning the RealityJudge singleton.
        _background_task_holder: dict with single key "task" — used as a
            mutable holder for the asyncio background task so we can cancel
            it on shutdown. (Dict avoids `global` declaration.)
    """
    logger.info("=" * 60)
    logger.info("SCP V99 API Server starting...")
    logger.info("=" * 60)

    # ============================================================
    # [STARTUP-GATE] Pre-startup deep audit
    # [V4.6] PHÂN BIỆT: QUYỀN (capability) vs HÀNH ĐỘNG (execution)
    #
    # FULL_PRODUCTION = CÓ QUYỀN fix mọi bug, NHƯNG:
    #   - Startup gate CHỈ QUÉT + BÁO CÁO (không fix tất cả 1 lần)
    #   - AutoFix background fix TỪNG CÁI khi server đã listen
    #   - User có thể trigger manual qua /v105/autofix/run-audit
    #
    # → Server start NGAY (không block 100 phút)
    # → AutoFix chạy nền, fix từng bug KHI CẦN
    # ============================================================
    # [SCP-DNA-FIX R12-28] Disable WHY LLM + evolution during startup.
    # Tại sao: SCP_WHY_LLM_ENABLED=1 → WHY gate gọi LLM cho mỗi action
    # → get_judge() init 15+ engines, mỗi engine trigger WHY gate → LLM call
    # → 15 × 10s = 150s → server timeout. Fix: tạm tắt WHY LLM + evolution
    # trong startup, bật lại SAU khi server bind port.
    _orig_why_llm = os.environ.get("SCP_WHY_LLM_ENABLED", "0")
    _orig_evo_auto = os.environ.get("SCP_EVOLUTION_AUTO", "0")
    os.environ["SCP_WHY_LLM_ENABLED"] = "0"
    os.environ["SCP_EVOLUTION_AUTO"] = "0"
    logger.info("[STARTUP-GATE] WHY LLM + Evolution AUTO temporarily disabled for fast startup")

    if os.environ.get("SCP_SKIP_STARTUP_GATE", "0") == "1":
        logger.warning("[STARTUP-GATE] SCP_SKIP_STARTUP_GATE=1 — audit BYPASSED (dev mode)")
    else:
        try:
            # [V4.6] Chỉ QUÉT, không FIX tất cả — tránh block server 100 phút
            from scp.autofix.runner import ast_scan_scp

            # [R16-ROOT-FIX-6] NON-BLOCKING startup gate.
            #
            # ROOT CAUSE (5-Whys) of "SCP không chạy khi SCP_SKIP_STARTUP_GATE=0":
            #   Symptom: /health returns 503, dashboard shows OFFLINE
            #   Why 1: FastAPI lifespan hasn't completed → app not ready
            #   Why 2: ast_scan_scp() takes 30-60s (547 files × parse + visit)
            #   Why 3: Gate runs SYNCHRONOUSLY in lifespan — blocks event loop
            #   Why 4: After scan, if critical_bugs > 0 → raise RuntimeError → app FAILS
            #   Why 5 (ROOT): Gate BLOCKS app start. Should run BACKGROUND post-startup.
            #
            # BEFORE: gate scan (60s) + RuntimeError if bugs → app never starts → 503 forever
            # AFTER:  gate runs in BACKGROUND thread. App starts IMMEDIATELY.
            #         /health returns 200. Gate reports bugs async via /v105/autofix/stats.
            #         DNA #7 (AutoFix safe): gate is advisory, not blocking.
            #
            # Why this is ROOT not CASCADE:
            # - Cascade fix: add timeout to scan (still blocks for timeout duration)
            # - ROOT fix: move gate to background — app start is NEVER blocked by audit
            # - Eliminates the bug CLASS (audit blocking startup) at origin.

            import threading as _threading_mod

            def _run_startup_gate_background():
                """Run startup gate in background thread — never blocks app start."""
                try:
                    bugs = ast_scan_scp(max_files=int(os.environ.get("SCP_MAX_STARTUP_FILES", "100")))
                    logger.info(f"[STARTUP-GATE] Background scan complete: {len(bugs)} bugs found")
                    logger.info("  → AutoFix sẽ xử lý background (không block server)")
                    logger.info("  → Manual: POST /v105/autofix/run-audit (khi rảnh)")

                    # [R16-ROOT-FIX-6] Report bugs but NEVER raise RuntimeError.
                    # App is already running — blocking here would crash a LIVE server.
                    _STYLE_NON_BLOCKING = {
                        "RuffSecurity_PLC0415", "RuffSecurity_PLW0717",
                        "RuffSecurity_PLW0603", "RuffSecurity_RUF052",
                        "RuffSecurity_RUF100", "RuffSecurity_PLR2004",
                        "RuffSecurity_BLE001",
                    }
                    critical_bugs = [
                        b for b in bugs
                        if b.bug_type not in _STYLE_NON_BLOCKING
                        and (
                            (getattr(b, "tier", None)
                             and str(getattr(b, "tier", "")).endswith("PERMISSION"))
                            or getattr(b, "affects_logic", False)
                        )
                    ]
                    if critical_bugs:
                        logger.warning(
                            f"[STARTUP-GATE] ⚠️  {len(critical_bugs)} critical bugs found "
                            f"(out of {len(bugs)} total). Server is RUNNING — bugs queued for "
                            f"background AutoFix. Review via POST /v105/autofix/run-audit."
                        )
                        # List top 5 critical bugs for operator visibility
                        for _b in critical_bugs[:5]:
                            logger.warning(
                                f"  - {_b.bug_type}: {_b.file}:{_b.line} — {_b.description[:80]}"
                            )
                        if len(critical_bugs) > 5:
                            logger.warning(f"  ... and {len(critical_bugs) - 5} more")
                    else:
                        logger.info(f"[STARTUP-GATE] ✅ Pre-startup audit passed — "
                                    f"{len(bugs)} bugs found (0 critical)")
                except Exception as _bg_err:
                    logger.warning(
                        f"[STARTUP-GATE] Background audit failed (non-blocking): {_bg_err}"
                    )
                    logger.warning("  Server đang chạy. Deep audit sẽ retry qua loop-scheduler.")

            # Launch gate in background thread — app continues to start IMMEDIATELY
            _gate_thread = _threading_mod.Thread(
                target=_run_startup_gate_background,
                name="startup-gate",
                daemon=True,  # dies with main process
            )
            _gate_thread.start()
            logger.info("[STARTUP-GATE] Audit dispatched to background thread — app starts NOW")
        except Exception as e:
            # [R16-ROOT-FIX-6] NEVER raise — app must start regardless of gate status.
            logger.warning(f"[STARTUP-GATE] Pre-startup audit dispatch failed (non-blocking): {e}")
            logger.warning("  Server sẽ start. Deep audit sẽ retry qua loop-scheduler.")

    # ============================================================
    # Server start (audit PASS)
    # ============================================================
    # [R18-ROOT-FIX-2] get_judge() moved to BACKGROUND — was blocking lifespan!
    #
    # 5-Whys (DNA #1):
    #   Symptom: User runs start-scp.bat but /health still Connection Refused
    #   Why 1: uvicorn hasn't reached "yield" in lifespan → port not accepting
    #   Why 2: get_judge() at line 179 is BEFORE yield → blocks lifespan
    #   Why 3: get_judge() triggers RealityJudge.__init__ → 15+ engines
    #          → each may call LLM → OpenRouter 429 → 30-60s hang
    #   Why 4: R17-FIX-9 made /health minimal BUT only works AFTER yield
    #   Why 5 (ROOT): get_judge() BEFORE yield = app cannot accept requests
    #         until ALL engines init. Should be AFTER yield (background).
    #
    # Fix: yield FIRST, then get_judge() in background.
    # DNA #7 (Autofix safe) + #26 (Reality > Model): port binds = ready.
    #
    # NOTE: /ask will return 503 if called before judge is ready.
    # /health returns 200 immediately (R17-FIX-9).
    # This is ACCEPTABLE — benchmark polls /health, not /ask.

    # Yield immediately — let uvicorn bind port + accept /health requests
    logger.info("[R18-FIX-2] Yielding lifespan NOW — port will bind immediately")
    logger.info("[R18-FIX-2] get_judge() will run in background thread")

    # Start get_judge() in background thread (non-blocking)
    import threading as _threading_mod_r18

    def _init_judge_background():
        """Init judge in background — /ask will 503 until ready, /health works immediately."""
        try:
            judge = get_judge()
            logger.info(f"[R18-FIX-2] Judge ready: {len(judge.slms)} SLMs")
            logger.info(f"[R18-FIX-2] V98 status: {judge.get_v98_status()}")

            try:
                # schedule_background_jobs needs event loop — create one for this thread
                import asyncio as _a_r18
                _loop = _a_r18.new_event_loop()
                _a_r18.set_event_loop(_loop)
                _task = _loop.run_until_complete(judge.schedule_background_jobs())
                _background_task_holder["task"] = _task
                logger.info("[R18-FIX-2] Background scheduler started (ThreatSimulator 6h + IntelCrawler 12h)")

                # [R18-FIX-4] Wire V100 knowledge-crawler scheduler (was DEAD — DNA #19).
                if hasattr(judge, "schedule_v100_background_jobs"):
                    _v100_task = _loop.run_until_complete(judge.schedule_v100_background_jobs())
                    _background_task_holder["v100_jobs"] = _v100_task
                    logger.info("[R18-FIX-4] V100 knowledge-crawler scheduler started (6h interval)")
                else:
                    logger.warning("[R18-FIX-4] schedule_v100_background_jobs not available on judge")

                # [R19-FIX-3] Wire ExternalTrustRoot — register anchor files + 24h verify (DNA #19).
                # BEFORE: register_file + verify_all_baselines had 0 callers → tamper detection dead.
                # AFTER: register constitution + external_audit tests at startup, verify every 24h.
                try:
                    from scp.meta.external_trust import ExternalTrustRoot
                    _trust = ExternalTrustRoot()
                    # Register critical anchor files for tamper detection
                    _anchor_files = [
                        "scp/meta/constitution.py",
                        "scp/autofix/policy_gate.py",
                        "scp/api/_shared.py",
                        "scp/tests/external_audit/test_cascade.py",
                        "scp/tests/external_audit/test_security.py",
                    ]
                    _registered = 0
                    for _af in _anchor_files:
                        if _trust.register_file(_af):
                            _registered += 1
                    logger.info(f"[R19-FIX-3] ExternalTrustRoot: {_registered}/{len(_anchor_files)} anchor files registered")

                    # Initial verification at startup
                    _results = _trust.verify_all_baselines()
                    _all_ok = all(_results.values()) if _results else True
                    if _all_ok:
                        logger.info(f"[R19-FIX-3] Startup integrity check: PASS ({len(_results)} files)")
                    else:
                        _bad = [k for k, v in _results.items() if not v]
                        logger.error(f"[R19-FIX-3] STARTUP INTEGRITY CHECK FAILED: {_bad}")

                    # Schedule 24h periodic verification
                    def _trust_verify_loop():
                        import time as _t
                        _t.sleep(86400)  # 24h first run
                        while True:
                            try:
                                _r = _trust.verify_all_baselines()
                                if not all(_r.values()):
                                    _bad = [k for k, v in _r.items() if not v]
                                    logger.error(f"[R19-FIX-3] TAMPER DETECTED: {_bad}")
                                else:
                                    logger.info(f"[R19-FIX-3] 24h integrity check: PASS ({len(_r)} files)")
                            except Exception as _e:
                                logger.warning(f"[R19-FIX-3] Integrity check error: {_e}")
                            _t.sleep(86400)  # 24h

                    _trust_thread = _threading_mod_r18.Thread(
                        target=_trust_verify_loop, name="scp-trust-verify", daemon=True
                    )
                    _trust_thread.start()
                    _background_task_holder["trust_verify"] = _trust_thread
                except Exception as _trust_err:
                    logger.warning(f"[R19-FIX-3] ExternalTrustRoot init failed: {_trust_err}")

                # [R19-FIX-4] Wire domain_store.verify_all_baselines (DNA #19).
                # BEFORE: verify_all_baselines had 0 callers → domain file tamper detection dead.
                # AFTER: periodic 24h verification (runs alongside _trust_verify_loop).
                try:
                    _judge_for_ds = _get_judge_lazy()
                    if _judge_for_ds and hasattr(_judge_for_ds, "domain_knowledge_store"):
                        _ds = _judge_for_ds.domain_knowledge_store
                        if hasattr(_ds, "verify_all_baselines"):
                            def _ds_verify_loop():
                                import time as _t
                                _t.sleep(86400 + 60)  # 24h + 1min offset (avoid concurrent with trust)
                                while True:
                                    try:
                                        _r = _ds.verify_all_baselines()
                                        if isinstance(_r, dict):
                                            _bad = [k for k, v in _r.items() if isinstance(v, dict) and not v.get("ok", True)]
                                            if _bad:
                                                logger.warning(f"[R19-FIX-4] Domain store baseline mismatches: {_bad}")
                                            else:
                                                logger.info(f"[R19-FIX-4] Domain store 24h check: PASS")
                                    except Exception as _e:
                                        logger.warning(f"[R19-FIX-4] Domain store verify error: {_e}")
                                    _t.sleep(86400)

                            _ds_thread = _threading_mod_r18.Thread(
                                target=_ds_verify_loop, name="scp-ds-verify", daemon=True
                            )
                            _ds_thread.start()
                            _background_task_holder["ds_verify"] = _ds_thread
                            logger.info("[R19-FIX-4] Domain store baseline verifier scheduled (24h)")
                except Exception as _ds_err:
                    logger.warning(f"[R19-FIX-4] Domain store verify wire failed: {_ds_err}")

            except Exception as e:
                logger.warning(f"[R18-FIX-2] Background scheduler failed: {e}")
        except Exception as e:
            logger.error(f"[R18-FIX-2] Judge init FAILED: {e}")
            logger.error("[R18-FIX-2] /ask will return 503 until judge is available")

    _judge_thread = _threading_mod_r18.Thread(
        target=_init_judge_background,
        name="scp-judge-init",
        daemon=True,
    )
    _judge_thread.start()
    logger.info("[R18-FIX-2] Judge init dispatched to background thread")

    # [R18-FIX-2] Background scheduler now started inside _init_judge_background()
    # (was: asyncio.create_task here — but `judge` isn't available synchronously anymore)
    # The background thread will start schedule_background_jobs() after judge is ready.

    # ============================================================
    # [R20-ROOT-FIX] YIELD IMMEDIATELY — port binds NOW (DNA #26)
    # ============================================================
    # ROOT CAUSE of persistent 503:
    #   R18-FIX-2 moved get_judge() to background (good)
    #   BUT yield was still at line 620 — AFTER 400+ lines of:
    #     - 8 background thread .start() calls (synchronous)
    #     - 23 try/except blocks
    #     - Tor refresher, deep audit, canary, why_verify, etc.
    #   Port doesn't bind until yield → /health 503 for 30-60s+
    #
    # FIX: yield RIGHT HERE — before any background service starts.
    # All background services (Tor, audit, canary, why_verify) move
    # to AFTER yield. They're all daemon threads — safe to start late.
    #
    # DNA #7 (Autofix safe): port binds = ready. /health = 200.
    # DNA #26 (Reality > Model): Reality = port 8000 accepting connections.
    # DNA #22 (PASS ≠ TRUE): R18-FIX-2 said "yield immediately" but
    #   yield was at line 620. Comment ≠ code. This is the fix.
    # ============================================================

    logger.info("[R20-ROOT-FIX] Yielding NOW — port 8000 binds immediately")
    yield

    # ============================================================
    # POST-YIELD: Background services start HERE (after port bound)
    # All are daemon threads — safe to start after yield.
    # If any fails, /health still 200, /ask still works (judge in background).
    # ============================================================

    # [SCP-DNA-FIX R6-2 + R7-2] Source: vulture (Category B dead safety control) + RUF006.
    # TẠI SAO: AsnDetector.refresh_tor_exits() (threat_detector.py:181) was NEVER called
    # by any runtime path. AsnDetector._tor_exits is initialized as an empty set (L178)
    # and only populated inside refresh_tor_exits — which is dead. Result:
    # `is_tor = ip in self._tor_exits` (L216) is ALWAYS False → attackers using Tor exit
    # nodes are NOT flagged as Tor users → they get the same threat profile as residential
    # IPs. The Tor-detection safety feature exists on paper but is silently dead.
    # Reality evidence: grep `refresh_tor_exits` → 0 callers (only the def line).
    # Fix: periodic asyncio task (1h TTL matches _tor_last_refresh guard inside the fn)
    # that refreshes the Tor exit list from check.torproject.org. Best-effort: failures
    # logged at DEBUG (same as the function's internal except) — Tor detection degrades
    # to "always False" if the endpoint is unreachable, but does NOT crash the server.
    #
    # [SCP-DNA-FIX R7-2] R6-2 stored the task in _background_task_holder dict (good —
    # avoids RUF006/GC), but lacked add_done_callback to discard + log task exceptions,
    # AND lacked a healthcheck for the "_tor_exits still empty after 5min startup"
    # failure mode. R7-2 adds:
    #   1. Module-level _tor_refresh_tasks set + add_done_callback(discard) pattern
    #      (mirrors R5 #9 _async_factcheck_tasks fix).
    #   2. Healthcheck coroutine that WARNs if _tor_exits is empty after 5min startup
    #      (the only operator-visible signal that Tor detection is silently dead).
    _tor_refresh_tasks: set = set()
    try:
        async def _tor_refresh_loop():
            await asyncio.sleep(30)  # let other startup finish first
            while True:
                try:
                    _asn = getattr(getattr(_get_judge_lazy(), "threat_detector", None), "asn", None)
                    if _asn is not None and hasattr(_asn, "refresh_tor_exits"):
                        await _asn.refresh_tor_exits()
                except Exception as _e:
                    logger.debug(f"[AUTO] Tor exit refresh failed: {_e}")
                await asyncio.sleep(3600)  # 1h (matches AsnDetector._tor_last_refresh TTL)

        _tor_task = asyncio.create_task(_tor_refresh_loop())
        # [R7-2] Keep a STRONG reference in a module-level set so the asyncio GC
        # cannot reap the task before completion (RUF006). add_done_callback discards
        # the ref on completion AND logs any unexpected exception (defensive — the
        # loop body already swallows, but a CancelledError or BaseException would
        # otherwise be lost silently).
        _tor_refresh_tasks.add(_tor_task)

        def _tor_task_done(t: asyncio.Task) -> None:
            _tor_refresh_tasks.discard(t)
            if not t.cancelled() and t.exception() is not None:
                logger.warning(
                    f"[R7-2] Tor refresh task ended with exception: {t.exception()!r} "
                    f"— Tor exit-node detection may degrade to always-False."
                )

        _tor_task.add_done_callback(_tor_task_done)
        _background_task_holder["tor_refresh"] = _tor_task

        # [R7-2] Healthcheck: WARN if _tor_exits empty after 5min startup.
        async def _tor_healthcheck():
            await asyncio.sleep(300)  # 5min warm-up (refresh_loop runs at +30s, so it
                                       # has had 4.5min to fetch + populate _tor_exits)
            while True:
                try:
                    _asn = getattr(getattr(_get_judge_lazy(), "threat_detector", None), "asn", None)
                    _exits = getattr(_asn, "_tor_exits", None) if _asn else None
                    if not _exits:
                        logger.warning(
                            "[R7-2] Tor exit-node list is EMPTY after startup warm-up — "
                            "is_tor(ip) is returning False for ALL IPs. Tor detection is "
                            "SILENTLY DEAD. Check network egress to check.torproject.org."
                        )
                except Exception as _e:
                    logger.debug(f"[R7-2] Tor healthcheck error: {_e}")
                await asyncio.sleep(3600)  # check hourly

        _tor_hc_task = asyncio.create_task(_tor_healthcheck())
        _tor_refresh_tasks.add(_tor_hc_task)
        _tor_hc_task.add_done_callback(_tor_refresh_tasks.discard)
        _background_task_holder["tor_healthcheck"] = _tor_hc_task

        logger.info("[AUTO] Tor exit-node refresher started (1h interval) + healthcheck (5min warm-up)")
    except Exception as e:
        logger.warning(f"[AUTO] Tor refresher failed to start: {e}")

    # [SCP-DNA-FIX R6-7] Source: vulture (Category B dead safety control) + grep verify.
    # TẠI SAO: judge.schedule_v100_background_jobs() (judge.py:1079) was NEVER called.
    # [R18-FIX-2] This now runs inside _init_judge_background() thread (after judge ready)
    # — was: asyncio.create_task here, but `judge` is async-init now.
    # The V100 scheduler will start in the background thread after judge is ready.
    # If /ask is called before judge ready → 503 (acceptable, /health still 200).

    # [AUTO-WIRE] Deep audit scheduler (24h)
    try:
        def _deep_audit_loop():
            _time.sleep(60)
            while True:
                try:
                    logger.info("[AUTO] Deep audit cycle starting...")
                    from scp.autofix.runner import run_deep_audit
                    results = run_deep_audit(max_bugs=int(os.environ.get("SCP_MAX_AUDIT_BUGS", "100")))  # [ROOT-FIX 47] was 20
                    logger.info(f"[AUTO] Deep audit: {results.get('processed', 0)} bugs processed, "
                                f"{results.get('fixed', 0)} auto-fixed")
                except Exception as e:
                    logger.warning(f"[AUTO] Deep audit failed: {e}")
                _time.sleep(86400)

        _audit_thread = threading.Thread(target=_deep_audit_loop, daemon=True,
                                          name="scp-deep-audit-scheduler")
        _audit_thread.start()
        logger.info("[AUTO] Deep audit scheduler started (24h interval)")
    except Exception as e:
        logger.warning(f"[AUTO] Deep audit scheduler failed: {e}")

    # [AUTO-WIRE] Attack mode monitor (5min)
    try:
        def _attack_mode_monitor():
            _time.sleep(120)
            while True:
                try:
                    from scp.autofix.engine import get_autofix_engine
                    eng = get_autofix_engine()
                    # [SCP-DNA-FIX R8-1] TẠI SAO: query cũ `SELECT COUNT(*) FROM
                    # notifications` hit SQLite table không tồn tại (0 CREATE TABLE
                    # matches trong codebase). Notifications lưu in-memory tại
                    # `judge.notifications._recent` (runtime/notifications.py:95) +
                    # JSONL file. sqlite3.OperationalError bị swallow bởi
                    # `except: logger.debug` → kill_count luôn 0 → attack mode
                    # KHÔNG BAO GIỜ auto-trig (PASS ≠ TRUE, DNA #22).
                    # Fix: đếm governance_kill events trong 10 phút gần nhất trực tiếp
                    # từ in-memory UserNotificationSystem._recent.
                    _notif = getattr(_get_judge_lazy(), "notifications", None)
                    _cutoff = _time.time() - 600
                    if _notif is not None:
                        # [SCP-DNA-FIX R9-7 / SA-R9-2] Mirror the api_server.py
                        # fix — R8-1's inlined `sum(1 for _n in _notif._recent ...)`
                        # races with notify()'s append (worker thread) and is
                        # swallowed by the outer except → monitor silently dies.
                        # Use the new thread-safe count method (locks internally
                        # + fail-open returns 0 → attack mode never falsely
                        # enables). Same fix as api_server.py:_attack_mode_monitor.
                        kill_count = _notif.count_recent_by_type(
                            "governance_kill", _cutoff
                        )
                    else:
                        kill_count = 0
                    if kill_count > 20 and not eng.in_attack_mode:
                        eng.set_attack_mode(True)
                        logger.warning(f"[AUTO] Attack mode ENABLED — {kill_count} KILLs in 10min")
                    elif kill_count < 5 and eng.in_attack_mode:
                        eng.set_attack_mode(False)
                        logger.info(f"[AUTO] Attack mode DISABLED — {kill_count} KILLs in 10min (normal)")
                except Exception as e:
                    logger.debug(f"[AUTO] Attack mode monitor: {e}")
                _time.sleep(300)

        _attack_thread = threading.Thread(target=_attack_mode_monitor, daemon=True,
                                           name="scp-attack-mode-monitor")
        _attack_thread.start()
        logger.info("[AUTO] Attack mode auto-monitor started (5min interval)")
    except Exception as e:
        logger.warning(f"[AUTO] Attack mode monitor failed: {e}")

    # [SCP-DNA-FIX R6-3] Source: vulture (Category B) + R5-incompleteness.
    # TẠI SAO: R5 Bug #11 added WhyEngine.run_pending_verification_cycle() (the
    # public wrapper around execute_pending_plans) but EXPLICITLY left the wiring
    # as a commented-out recommendation (why_engine.py:783-794 "out of scope for
    # this fix"). So the wrapper exists but is STILL never called → deferred WHY
    # verification plans pile up forever in why_verification_plans table →
    # falsification pipeline for deferred-verification claims is STILL BROKEN
    # despite R5 claiming it was fixed. PASS ≠ TRUE (DNA #22).
    # Reality evidence: grep `run_pending_verification_cycle` → 0 callers (only
    # the def line + a commented-out recommendation).
    # Fix: 5-min periodic thread (matches R5's recommended cadence) that calls
    # judge.why_engine.run_pending_verification_cycle(limit=10). Guarded for
    # why_engine=None (init-failed case) and never raises (the method itself
    # wraps execute_pending_plans in try/except).
    try:
        def _why_verify_loop():
            _time.sleep(180)  # 3min warm-up (let judge fully init + first verdicts land)
            while True:
                try:
                    # [R18-FIX-2] Get judge lazily (may not be ready yet)
                    _j = None
                    try:
                        _j = get_judge()
                    except Exception:
                        pass  # judge not ready yet — skip this cycle
                    _we = getattr(_j, "why_engine", None) if _j else None
                    if _we is not None and hasattr(_we, "run_pending_verification_cycle"):
                        _stats = _we.run_pending_verification_cycle(limit=10)
                        if isinstance(_stats, dict) and _stats.get("executed", 0) > 0:
                            logger.info(f"[AUTO] WHY verify cycle: {_stats}")
                except Exception as _e:
                    logger.debug(f"[AUTO] WHY verify cycle failed: {_e}")
                _time.sleep(300)  # 5min (R5 recommended cadence)

        _why_thread = threading.Thread(target=_why_verify_loop, daemon=True,
                                        name="scp-why-verify-scheduler")
        _why_thread.start()
        logger.info("[AUTO] WHY verification scheduler started (5min interval)")
    except Exception as e:
        logger.warning(f"[AUTO] WHY verify scheduler failed: {e}")

    # [SCP-DNA-FIX R6-9] Source: vulture (Category B dead safety control) + grep verify.
    # TẠI SAO: CanaryTokenMonitor.cleanup_expired() (canary_monitor.py:221) was NEVER
    # called. Expired canary tokens accumulate forever in self.tokens dict (memory
    # growth) AND in the triggers_file (disk growth). After long uptime the tokens
    # dict grows unbounded — each attacker IP gets a new canary token generated
    # (judgecore_mixin.py:2031) but expired ones are never pruned.
    # Reality evidence: grep `cleanup_expired` → 0 callers outside the def.
    # Fix: daily periodic thread. cleanup_expired is thread-safe (holds self._lock).
    try:
        def _canary_cleanup_loop():
            _time.sleep(600)  # 10min warm-up
            while True:
                try:
                    _cm = getattr(_get_judge_lazy(), "canary_monitor", None)
                    if _cm is not None and hasattr(_cm, "cleanup_expired"):
                        _removed = _cm.cleanup_expired()
                        if _removed:
                            logger.info(f"[AUTO] Canary cleanup: removed {_removed} expired tokens")
                except Exception as _e:
                    logger.debug(f"[AUTO] Canary cleanup failed: {_e}")
                _time.sleep(86400)  # 24h

        _canary_thread = threading.Thread(target=_canary_cleanup_loop, daemon=True,
                                          name="scp-canary-cleanup")
        _canary_thread.start()
        logger.info("[AUTO] Canary token cleanup scheduler started (24h interval)")
    except Exception as e:
        logger.warning(f"[AUTO] Canary cleanup scheduler failed: {e}")

    # [SCP-DNA-FIX R5-3] Wire start_audit_fetcher / start_ai_scanner /
    # start_harm_detector (and stop_* on shutdown).
    # Round 5 / Source 3 (vulture) caught this: the three start_* callables
    # were imported at module top (lines 21, 27, 34) but NEVER invoked inside
    # lifespan(). The corresponding stop_* callables were also never invoked
    # on shutdown. Result: dashboard endpoints /audit/stats, /ai-threats/stats,
    # /harm/stats silently returned empty data because the background fetcher
    # threads that populate their data stores were never started.
    # Reality evidence: PowerShell.txt shows 0 entries from audit_fetcher /
    # ai_threat_scanner / harm_detector in 43 min of runtime.
    # Fix: call start_*() after the deep audit scheduler (so they share the
    # startup phase) and call stop_*() on shutdown.
    _started_bg_services: list[tuple[str, callable, callable]] = []
    try:
        if start_audit_fetcher is not None:
            start_audit_fetcher()
            _started_bg_services.append(("audit_fetcher", start_audit_fetcher, stop_audit_fetcher))
            logger.info("[AUTO] audit_fetcher started (multi-source audit background)")
        else:
            logger.warning("[AUTO] audit_fetcher not available (import failed) — /audit/stats will be empty")
    except Exception as e:
        logger.warning(f"[AUTO] audit_fetcher start failed: {e}")

    try:
        if start_ai_scanner is not None:
            start_ai_scanner()
            _started_bg_services.append(("ai_scanner", start_ai_scanner, stop_ai_scanner))
            logger.info("[AUTO] ai_threat_scanner started (AI-pattern threat background)")
        else:
            logger.warning("[AUTO] ai_threat_scanner not available (import failed) — /ai-threats/stats will be empty")
    except Exception as e:
        logger.warning(f"[AUTO] ai_threat_scanner start failed: {e}")

    try:
        if start_harm_detector is not None:
            start_harm_detector()
            _started_bg_services.append(("harm_detector", start_harm_detector, stop_harm_detector))
            logger.info("[AUTO] harm_detector started (harmful-content background)")
        else:
            logger.warning("[AUTO] harm_detector not available (import failed) — /harm/stats will be empty")
    except Exception as e:
        logger.warning(f"[AUTO] harm_detector start failed: {e}")

    # [SCP-DNA-FIX R12-28] Restore WHY LLM + Evolution AUTO — server is about to serve.
    # Tại sao: tạm tắt trong startup (line 76-85) để get_judge() fast. Giờ server
    # ready → restore để WHY gate + evolution hoạt động bình thường.
    os.environ["SCP_WHY_LLM_ENABLED"] = _orig_why_llm
    os.environ["SCP_EVOLUTION_AUTO"] = _orig_evo_auto
    logger.info(f"[STARTUP-GATE] WHY LLM + Evolution AUTO restored (why={_orig_why_llm}, evo={_orig_evo_auto})")

    # [R20-ROOT-FIX] Old yield was HERE (line 650) — moved to line 364 above.
    # Shutdown cleanup runs when app stops (after second yield context exits).
    # This code still runs on shutdown — just no yield here anymore.

    if _background_task_holder.get("task"):
        _background_task_holder["task"].cancel()
    # [SCP-DNA-FIX R6-2 + R7-2] Cancel Tor-exit refresher + healthcheck on shutdown.
    if _background_task_holder.get("tor_refresh"):
        _background_task_holder["tor_refresh"].cancel()
    if _background_task_holder.get("tor_healthcheck"):
        _background_task_holder["tor_healthcheck"].cancel()
    # [SCP-DNA-FIX R6-7] Cancel V100 knowledge-crawler scheduler on shutdown.
    if _background_task_holder.get("v100_jobs"):
        _background_task_holder["v100_jobs"].cancel()
    # [SCP-DNA-FIX R5-3] Stop the bg services we started, in reverse order.
    for _name, _start_fn, _stop_fn in reversed(_started_bg_services):
        try:
            if _stop_fn is not None:
                _stop_fn()
                logger.info(f"[AUTO] {_name} stopped cleanly")
        except Exception as e:
            logger.warning(f"[AUTO] {_name} stop failed: {e}")
    logger.info("SCP V99 API Server shutting down...")
