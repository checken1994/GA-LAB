# -*- coding: utf-8 -*-
"""Step 2: Automatic fallback-map watcher (6 h daemon).

Refreshes OPENROUTER_FREE_MODELS every SCP_FALLBACK_WATCH_INTERVAL seconds.
If OPENROUTER_MODEL_AUTO=1, also updates TASK_FREE_FALLBACK_MAP with the
best available free model (highest context_length, then alpha id).
"""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger("scp.llm_gateway.fallback_watcher")

_watcher_started = False
_watcher_lock = threading.Lock()
_INTERVAL = int(os.environ.get("SCP_FALLBACK_WATCH_INTERVAL", str(6 * 3600)))


def _auto_select_model(free_models: list) -> str | None:
    if not free_models:
        return None
    best = max(free_models, key=lambda m: (int(m.get("context_length", 0) or 0), -len(m.get("id", ""))))
    return best["id"]


def _update_fallback_map(free_models: list) -> None:
    if os.environ.get("OPENROUTER_MODEL_AUTO", "0") != "1":
        return
    from scp.llm_gateway import client as _client
    best = _auto_select_model(free_models)
    if not best:
        logger.warning("[fallback_watcher] AUTO: no best model found — map unchanged")
        return
    for task in list(_client.OpenRouterProvider.TASK_FREE_FALLBACK_MAP.keys()):
        _client.OpenRouterProvider.TASK_FREE_FALLBACK_MAP[task] = best
    logger.info("[fallback_watcher] AUTO: updated all task fallbacks -> %s", best)


def _run_once() -> None:
    try:
        from scp.llm_gateway.free_catalog import _fetch_free_models, _sort_free_models, _text_capable
        from scp.llm_gateway import client as _client
        catalog = _fetch_free_models()
        if not catalog:
            logger.warning("[fallback_watcher] catalog empty — skipping")
            return
        usable = [m for m in _sort_free_models(catalog) if _text_capable(m)]
        if not usable:
            logger.warning("[fallback_watcher] no text-capable models — skipping")
            return
        _client.OPENROUTER_FREE_MODELS = [m["id"] for m in usable]
        logger.info("[fallback_watcher] refreshed %d free models", len(usable))
        _update_fallback_map(usable)
    except Exception:
        logger.exception("[fallback_watcher] refresh failed — existing lists unchanged")


def start_fallback_watcher() -> None:
    """Start background watcher (idempotent)."""
    global _watcher_started
    with _watcher_lock:
        if _watcher_started:
            return
        _watcher_started = True

    def _loop() -> None:
        while True:
            time.sleep(_INTERVAL)
            _run_once()

    t = threading.Thread(target=_loop, daemon=True, name="scp-fallback-watcher")
    t.start()
    logger.info("[fallback_watcher] started (interval=%ds)", _INTERVAL)