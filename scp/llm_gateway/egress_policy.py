"""Fail-closed outbound policy for LLM providers.

`SCP_EGRESS_MODE=deny` blocks every external LLM provider before an HTTP
client is touched. Loopback providers remain usable for deterministic/local
fixtures. `SCP_EGRESS_MODE=allowlist` requires the provider hostname to be
listed explicitly in `SCP_LLM_EGRESS_ALLOWLIST`.

The guard is installed at package import time so every existing import path
(`scp.llm_gateway` and `scp.llm_gateway.client`) receives the same policy
without duplicating transport logic across providers.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

import logging
logger = logging.getLogger(__name__)


_DENY_MODES = {"deny", "offline", "disabled"}
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _hostname(base_url: str) -> tuple[str, str]:
    try:
        parsed = urlparse(base_url)
    except Exception:
        logger.warning('_hostname: Exception not handled', exc_info=True)
        return "", ""
    return (parsed.scheme or "").lower(), (parsed.hostname or "").lower().rstrip(".")


def llm_egress_allowed(base_url: str) -> bool:
    """Return whether a provider endpoint may be contacted.

    External clear-text HTTP is never allowed. Unknown explicit egress modes
    fail closed. An unset mode keeps historical non-production behavior; in
    production `production_guard` already requires `deny` or `allowlist`.
    """
    scheme, host = _hostname(base_url)
    if not host:
        return False
    if host in _LOOPBACK_HOSTS:
        return scheme in {"http", "https"}
    if scheme != "https":
        return False

    mode = os.environ.get("SCP_EGRESS_MODE", "").strip().lower()
    if mode in _DENY_MODES:
        return False
    if mode == "allowlist":
        allowed = {
            item.strip().lower().rstrip(".")
            for item in os.environ.get("SCP_LLM_EGRESS_ALLOWLIST", "").split(",")
            if item.strip()
        }
        return host in allowed
    if mode == "":
        return True
    return False


def install_egress_guard(provider_cls) -> None:
    """Install one idempotent guard around the provider transport boundary."""
    if getattr(provider_cls, "_scp_egress_guard_installed", False):
        return

    original = provider_cls._call_model

    async def guarded(self, model, messages, api_key):
        if not llm_egress_allowed(self.base_url):
            return None, "egress_denied"
        return await original(self, model, messages, api_key)

    provider_cls._call_model = guarded
    provider_cls._scp_egress_guard_installed = True
