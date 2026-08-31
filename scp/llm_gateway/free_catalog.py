# -*- coding: utf-8 -*-
"""Shared free-model catalog refresh for the LLM gateway (P0/P1).

The catalog is advisory only. In deny-egress mode SCP must not create a
network side effect merely to refresh model metadata; the curated hardcoded
allowlist remains the fallback in that mode.
"""
from __future__ import annotations

import logging
import os
import threading
import time

import httpx

logger = logging.getLogger("scp.llm_gateway.free_catalog")

OPENROUTER_CATALOG_URL = "https://openrouter.ai/api/v1/models"
FREE_CATALOG_TIMEOUT_SEC = 5
FREE_CATALOG_REFRESH_SEC = 21600  # 6h background refresh

_lock = threading.Lock()
_fetched = False
_last_ok: float | None = None
_refresh_thread_started = False


def _external_egress_allowed() -> bool:
    """Return False when the runtime explicitly denies external egress."""
    return os.environ.get("SCP_EGRESS_MODE", "allow").strip().lower() not in {
        "deny",
        "disabled",
        "off",
        "none",
    }


def _fetch_free_models(timeout: float = FREE_CATALOG_TIMEOUT_SEC) -> list | None:
    """Fetch the OpenRouter catalog when external egress is allowed.

    Returns ``None`` for denied/failed fetches so callers keep the curated
    hardcoded allowlist.  Denied egress is a policy decision, not a degraded
    success that should attempt the network anyway.
    """
    if not _external_egress_allowed():
        logger.info("[free_catalog] external egress denied - keep hardcoded allowlist")
        return None
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(OPENROUTER_CATALOG_URL)
            if resp.status_code != 200:
                return None
            models = resp.json().get("data", [])
            out = []
            for model in models:
                pricing = model.get("pricing", {})
                if float(pricing.get("prompt", 1)) == 0 and float(pricing.get("completion", 1)) == 0:
                    out.append(model)
            return out
    except Exception:
        return None


def _text_capable(model: dict) -> bool:
    """Return True only for models that can produce textual output."""
    modalities = model.get("output_modalities")
    if modalities is None:
        modalities = model.get("architecture", {}).get("output_modalities")
    if not isinstance(modalities, list):
        modalities = []
    return not any("audio" in str(item).lower() or "video" in str(item).lower() for item in modalities)


def _sort_free_models(free_models: list) -> list:
    """Stable deterministic tie-break: context length desc, then id asc."""
    return sorted(
        free_models,
        key=lambda model: (-int(model.get("context_length", 0) or 0), model.get("id", "")),
    )


def refresh_free_catalog(force: bool = False) -> bool:
    """Refresh the free-model allowlist without changing task routing."""
    global _fetched, _last_ok
    with _lock:
        if _fetched and not force:
            return bool(_last_ok)
        _fetched = True
    catalog = _fetch_free_models()
    if not catalog:
        logger.warning("[free_catalog] fetch unavailable - keep hardcoded allowlist")
        return False
    usable = [model for model in _sort_free_models(catalog) if _text_capable(model)]
    if not usable:
        logger.warning("[free_catalog] no text-capable free models - keep hardcoded allowlist")
        return False
    from scp.llm_gateway import client as _client

    _client.OPENROUTER_FREE_MODELS = [model["id"] for model in usable]
    _last_ok = time.time()
    logger.info("[free_catalog] refreshed allowlist: %d text-capable models", len(usable))
    return True


def start_background_refresh() -> None:
    """Daemon refresh every 6h; deny-egress remains authoritative each cycle."""
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
