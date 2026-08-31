# -*- coding: utf-8 -*-
"""Shared free-model catalog refresh for the LLM gateway (P0/P1).

One module-level mechanism replaces the two duplicated per-class
_init_dynamic_models methods that used to fire a blocking requests.get
on the hot path. Design rules:
  1. Fetch at most once per process (guarded by _free_catalog_fetched).
  2. Uses httpx (already the project's async-first dependency), no new
     sync 'requests' import.

  3. Small timeout (1s) so a stalled catalog can never block inference;
     failure keeps the hardcoded allowlist (fail-closed.
.
  4. Never mutates TASK_FREE_FALLBACK_MAP - it stays the curated whitelist
     (P0: no heuristic task inference from model names)..
  5. Background daemon refreshes the allowlist every 6h WITHOUT touching
     the task map (keeps the free list fresh off the hot path).
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

logger = logging.getLogger("scp.llm_gateway.free_catalog")

OPENROUTER_CATALOG_URL = "https://openrouter.ai/api/v1/models"
FREE_CATALOG_TIMEOUT_SEC = 1
FREE_CATALOG_REFRESH_SEC = 21600  # 6h background refresh

_lock = threading.Lock()
_fetched = False
_last_ok: float | None = None
_refresh_thread_started = False


def _fetch_free_models(timeout: float = FREE_CATALOG_TIMEOUT_SEC) -> list | None:
    """Crawl OpenRouter catalog, keep zero-price (free) models.



    Returns [] when the catalog was fetched but no free models found,
    None when the fetch failed (caller keeps the hardcoded allowlist)."""
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(OPENROUTER_CATALOG_URL)
            if resp.status_code != 200:
                return None
            models = resp.json().get("data", [])
            out = []
            for m in models:
                pricing = m.get("pricing", {})
                if float(pricing.get("prompt", 1)) == 0 and float(pricing.get("completion", 1)) == 0:
                    out.append(m)
            return out
    except Exception:
        return None


def _text_capable(m: dict) -> bool:
    """P0: reject models whose OUTPUT modality is audio/video (they cannot
    be used for text chat/learning/vision). Absent modality fields treat as text."""
    modalities = m.get("output_modalities") or []
    if isinstance(modalities, list):
        for x in modalities:
            if any(k in str(x).lower() for k in ("audio", "video")):
                return False
    return True


def _sort_free_models(free_models: list) -> list:
    """Stable + deterministic tie-break: context length desc, then id asc."""
    return sorted(
        free_models,
        key=lambda m: (-int(m.get("context_length", 0) or 0), m.get("id", "")),
    )


def refresh_free_catalog() -> bool:
    """Fetch the fresh free-model allowlist at most ONCE per process. Never
    mutates TASK_FREE_FALLBACK_MAP. Returns True whenthel catalog replaced;
    False when hardcoded allowlist kept."""
    global _fetched, _last_ok
    with _lock:
        if _fetched:
            return bool(_last_ok)
        _fetched = True
    catalog = _fetch_free_models()
    if not catalog:
        logger.warning("[free_catalog] fetch returned nothing - keep hardcoded allowlist")
        return False
    usable = [m for m in _sort_free_models(catalog) if _text_capable(m)]
    if not usable:
        logger.warning("[free_catalog] no text-capable free models - keep hardcoded allowlist")
        return False
    global OPENROUTER_FREE_MODELS
    OPENROUTER_FREE_MODELS = [m["id"] for m in usable]
    _last_ok = time.time()
    logger.info("[free_catalog] refreshed allowlist: %d text-capable models", len(usable))
    return True


def start_background_refresh() -> None:
    """Daemon refresh every 6h - off the hot path, never touches task map."""
    global _refresh_thread_started
    with _lock:
        if _refresh_thread_started:
            return
        _refresh_thread_started = True


    def loop() -> None:
        while True:
            time.sleep(FREE_CATALOG_REFRESH_SEC)
            try:
                refresh_free_catalog(force=True)
            except Exception:
                logger.exception("[free_catalog] background refresh failed")


    threading.Thread(target=loop, daemon=True, name="llm-gateway-free-catalog-refresh").start()