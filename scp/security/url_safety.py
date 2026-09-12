"""
URL Safety Helper — B310 fix.

Validates URL scheme + blocks internal/private IPs before calling urllib.urlopen.
Use this instead of urllib.request.urlopen() to satisfy B310 (CWE-22).  # nosec B310 — URL validated by SCP

[EE egress enforcement — closes M13 G1]
This module is the single EGRESS CHOKE POINT for outbound HTTP fetches.
`enforce_egress_policy` reads SCP_EGRESS_MODE and fails closed:
  - deny/offline/disabled  → only loopback hosts (self-probe/internal services)
  - allowlist              → only loopback + hosts in SCP_EGRESS_ALLOWLIST
  - unset                  → no new restriction (historical dev behavior)
  - unknown value          → dev: no new restriction; production
                             (SCP_PRODUCTION_MODE) → deny (fail-closed)
`safe_urlopen` enforces it before the SSRF validation. The two other
canonical fetchers (`scp.core.url_fetcher._safe_fetch_url` and
`scp.core.api_utils.fetch_with_retry`) call the same idempotent gate.
Do NOT add a new raw HTTP call-site — the static regression gate in
tests/T03_capability/test_egress_enforcement.py fails on raw
urllib/requests/httpx calls outside the gated modules.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# Allowed URL schemes for outbound HTTP requests
ALLOWED_SCHEMES = frozenset({"http", "https"})

# [EE] Egress modes — mirror scp/llm_gateway/egress_policy.py _DENY_MODES so
# gateway and generic fetchers share one vocabulary. Deviation from the
# gateway: an UNKNOWN mode is only fail-closed here when production mode is
# explicitly declared (task contract: dev behavior must not be tightened).
_EGRESS_DENY_MODES = frozenset({"deny", "offline", "disabled"})
_EGRESS_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})  # mirrors production_guard._TRUE


class EgressDeniedError(PermissionError, ValueError):
    """Raised when SCP_EGRESS_MODE forbids contacting a URL.

    Inherits BOTH base classes on purpose:
      - PermissionError — capability semantics: callers may treat egress
        denial like a denied permission (task contract, EE agent).
      - ValueError — the canonical fetchers (`url_fetcher._safe_fetch_url`,
        `api_utils.fetch_with_retry`) document "policy violation raises
        ValueError"; keeping that contract means every existing
        `except ValueError` fail path (graceful skip, no retry) keeps
        working — no behavior change for denial-unaware callers.
    """

    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"egress denied for {url!r}: {reason}")


def _normalize_egress_host(hostname: str | None) -> str:
    """Lower-case, strip brackets/port remnants and trailing root dot."""
    return (hostname or "").strip().strip("[]").lower().rstrip(".")


def _is_loopback_host(hostname: str | None) -> bool:
    """True only for literal loopback: name in the loopback set or an IP
    literal whose ipaddress.is_loopback is True (covers 127.1, [::1] and
    integer spellings). Hostnames are intentionally NOT DNS-resolved here —
    resolution-based SSRF blocking stays in validate_url/_is_private_ip."""
    host = _normalize_egress_host(hostname)
    if not host:
        return False
    if host in _EGRESS_LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _egress_allowlist_hosts() -> frozenset[str]:
    raw = os.environ.get("SCP_EGRESS_ALLOWLIST", "")
    return frozenset(
        _normalize_egress_host(item) for item in raw.split(",") if item.strip()
    )


def _production_mode_declared() -> bool:
    return os.environ.get("SCP_PRODUCTION_MODE", "0").strip().lower() in _TRUE_VALUES


def enforce_egress_policy(url: str | urllib.request.Request) -> None:
    """Fail-closed egress gate driven by SCP_EGRESS_MODE. Idempotent: this is
    a pure check, calling it twice (e.g. `fetch_with_retry` →
    `_safe_fetch_url` → `safe_urlopen`) is harmless.

    Raises EgressDeniedError when the configured mode forbids contacting
    `url`. Loopback (127.0.0.1/::1/localhost and IP-literal loopback) is
    always allowed in every mode so internal services and self-probes keep
    working. Non-HTTP(S) schemes are left to validate_url's scheme
    allowlist — this gate only decides network egress.
    """
    url_str = url.full_url if isinstance(url, urllib.request.Request) else str(url)
    mode = os.environ.get("SCP_EGRESS_MODE", "").strip().lower()
    if not mode and not _production_mode_declared():
        return  # dev default: no restriction beyond the SSRF checks
    try:
        parsed = urllib.parse.urlparse(url_str)
    except Exception:  # unparseable under an explicit mode → fail closed
        raise EgressDeniedError(url_str, f"unparseable URL (SCP_EGRESS_MODE={mode!r})") from None
    scheme = (parsed.scheme or "").lower()
    hostname = _normalize_egress_host(parsed.hostname)
    if scheme not in ALLOWED_SCHEMES:
        return  # not an HTTP(S) egress decision; validate_url rejects the scheme
    if _is_loopback_host(hostname):
        return
    if mode in _EGRESS_DENY_MODES:
        raise EgressDeniedError(
            url_str, f"SCP_EGRESS_MODE={mode} blocks all non-loopback hosts"
        )
    if mode == "allowlist":
        if hostname and hostname in _egress_allowlist_hosts():
            return
        raise EgressDeniedError(
            url_str, f"host {hostname!r} not in SCP_EGRESS_ALLOWLIST (mode=allowlist)"
        )
    if _production_mode_declared():
        raise EgressDeniedError(
            url_str,
            f"SCP_EGRESS_MODE={mode!r} is not deny/allowlist — fail closed in production",
        )
    # Unknown mode + dev → keep historical behavior (no new restriction).

# Disallowed IP ranges (RFC1918 + loopback + link-local + multicast + reserved)
def _is_private_ip(host: str) -> bool:
    """Return True if host resolves to / is a private or loopback IP."""
    if not host:
        return True
    # Strip port
    if ":" in host and not host.startswith("["):
        host = host.rsplit(":", 1)[0]
    host = host.strip("[]")
    try:
        # Already an IP literal?
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
        except ValueError as e:
            logger.warning(f"Silent except: {e}")
        # Resolve hostname
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            logger.debug('_is_private_ip: socket.gaierror ignored', exc_info=True)
            return True  # unresolvable = treat as unsafe
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return True
        return False
    except Exception:
        logger.warning('_is_private_ip: Exception not handled', exc_info=True)
        return True


def validate_url(url: str, *, allow_internal: bool = False) -> urllib.parse.ParseResult:
    """Validate URL scheme + (optionally) internal IP. Raises ValueError on disallowed."""
    if not isinstance(url, str) or not url:
        raise ValueError("URL must be a non-empty string")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme '{parsed.scheme}' not in allowlist {sorted(ALLOWED_SCHEMES)}")
    if not parsed.hostname:
        raise ValueError("URL missing hostname")
    if not allow_internal and _is_private_ip(parsed.hostname):
        raise ValueError(f"URL host '{parsed.hostname}' resolves to internal/private IP — blocked")
    return parsed


def safe_urlopen(url: str | urllib.request.Request, *, timeout: float = 30, allow_internal: bool = False, **kwargs: Any):
    """Drop-in replacement for urllib.request.urlopen() that enforces B310 safety.  # nosec B310 — URL validated by SCP

    Args:
        url: URL string or Request object.
        timeout: Request timeout.
        allow_internal: Set True to allow internal/private IPs (e.g. for Ollama at 127.0.0.1).
        **kwargs: Forwarded to urllib.request.urlopen.  # nosec B310 — URL validated by SCP

    Returns:
        HTTP response object (same as urllib.request.urlopen).  # nosec B310 — URL validated by SCP
    """
    if isinstance(url, urllib.request.Request):
        url_str = url.full_url
    else:
        url_str = str(url)
    # [EE] Egress gate FIRST: deterministic EgressDeniedError (a ValueError)
    # under explicit SCP_EGRESS_MODE, before any DNS resolution/SSRF check.
    enforce_egress_policy(url)
    validate_url(url_str, allow_internal=allow_internal)
    if isinstance(url, urllib.request.Request):
        return urllib.request.urlopen(url, timeout=timeout, **kwargs)  # already validated above  # nosec B310  # noqa: S310
    return urllib.request.urlopen(url, timeout=timeout, **kwargs)  # already validated above  # nosec B310  # noqa: S310
