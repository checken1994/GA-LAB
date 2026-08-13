"""SCP canonical SSRF/LFI-safe URL fetcher.

[Fix 4-a-005 / Phase 3-A — DNA #5, #14, #19]
TẠI SAO this module exists:
  Before this fix, TWO divergent URL fetchers lived in the codebase:
    1. `scp.api_server_parts.helpers._safe_fetch_url` — had full SSRF defenses
       (scheme allowlist + IP/private-range check + safe-redirect handler +
       size cap + no-proxy opener). Used by /ask image_url/voice_url and
       /v104 image/voice check endpoints.
    2. `scp.core.api_utils.fetch_with_retry` — used urllib.request.urlopen
       directly with only a scheme check (`_validate_url_safe`), NO IP check,
       NO redirect policy (urllib follows 30x by default), NO size cap. Used
       by cross_verify, multi_source_verifier, crypto_verifier, predictive,
       weather/geo/numeric SLMs, etc.

  DNA #5 (ảo giác đồng thuận): scanners saw `_validate_url_safe` and assumed
  safety, missing the gap. DNA #14 (đồng thuận ≠ đúng): both fetchers were
  named "safe" but only one was. DNA #19 (tầng kiểm toán bằng chứng): no
  reality test enforced that any new fetcher must use the canonical defenses.

  Fix: ONE canonical implementation lives HERE. `helpers.py` and
  `api_utils.py` BOTH delegate to this module. If you need to add a fetcher,
  extend `_safe_fetch_url` here — do not create a third impl.

Defenses (kept identical to the previous `helpers._safe_fetch_url` so no
behavior regression on the safe path):
  1. scheme must be exactly http/https (rejects file://, ftp://, gopher://,
     data:, javascript:, etc.).
  2. hostname must NOT resolve to private / loopback / link-local / reserved /
     multicast / unspecified IP. Checked across ALL getaddrinfo results to
     mitigate DNS rebinding.
  3. strict User-Agent (`_SCP_SAFE_FETCH_UA`).
  4. [AUDIT-3 FIX] redirect following: ≤5 hops, each hop re-validated against
     `_is_disallowed_ip` (prevents SSRF via 302 → http://169.254.169.254/...).
  5. max_bytes cap via streaming read + early abort (no unbounded resp.read()).
  6. per-request timeout (default 8s).
  7. proxy disabled (prevents SSRF bypass via HTTP_PROXY env var).

On any policy violation or fetch error, raises ValueError. Callers should
catch ValueError and treat as a blocked fetch (NOT a server failure).
"""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("scp.core.url_fetcher")

# [SCP-DNA-FIX R5-1] Single canonical User-Agent for the safe fetcher.
# Was previously duplicated in api_server.py:73 AND helpers.py:36 — two
# definitions, same value, but the duplication was the seed of the
# "two impls" anti-pattern (DNA #5). Now defined ONCE here.
_SCP_SAFE_FETCH_UA = "SCP-V104/1.0 (security-safe-fetch)"


def _is_disallowed_ip(ip) -> bool:
    """True if IP is private/loopback/link-local/multicast/reserved/unspecified.

    Covers: 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16,
    169.254.0.0/16 (link-local incl. AWS/GCP/Azure metadata 169.254.169.254),
    ::1, fc00::/7 (unique-local), fe80::/10 (link-local), 0.0.0.0, ::.
    """
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow HTTP 3xx redirects safely — ≤5 hops, each hop re-validates IP.

    [AUDIT-3 FIX] TẠI SAO: the old _NoRedirectHandler rejected ALL redirects,
    breaking legitimate image CDNs (Imgur, S3 presigned URLs, Bit.ly, Google
    Photos — all use 302/301 redirects). But blindly following redirects is an
    SSRF vector (attacker sets up external URL that 302→169.254.169.254).
    Root-cause fix: follow ≤5 redirects, but re-validate the target URL
    against _is_disallowed_ip BEFORE following. If the redirect target is to
    a private/internal/metadata IP, raise ValueError (block the redirect).
    """

    # Limit redirect hops (urllib default is 30, far too many)
    max_repeats = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Re-validate the redirect target URL before following
        if not newurl or not isinstance(newurl, str):
            raise ValueError("redirect target missing URL")
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"redirect scheme not allowed: {parsed.scheme!r}")
        if not parsed.hostname:
            raise ValueError("redirect target missing hostname")
        # Resolve + check IP range (same logic as _safe_fetch_url initial check)
        try:
            infos = socket.getaddrinfo(parsed.hostname, None)
        except socket.gaierror as exc:
            raise ValueError(f"redirect DNS resolution failed: {exc}") from exc
        if not infos:
            raise ValueError("redirect target has no DNS records")
        for _family, _stype, _proto, _canon, sockaddr in infos:
            if not sockaddr or not sockaddr[0]:
                continue
            ip_str = sockaddr[0]
            if "%" in ip_str:
                ip_str = ip_str.split("%", 1)[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                raise ValueError(f"redirect target unparseable IP: {ip_str}") from None
            if _is_disallowed_ip(ip):
                raise ValueError("redirect target resolves to disallowed IP range")
        # Target is safe — delegate to parent to construct the redirect request
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _safe_fetch_url(
    url: str,
    *,
    max_bytes: int = 5_000_000,
    timeout: float = 8.0,
) -> bytes:
    """Fetch a user-supplied URL with SSRF/LFI defenses. Returns bytes.

    Raises ValueError on any policy violation or fetch error.

    [Fix 4-a-005] This is the CANONICAL safe URL fetcher for the SCP system.
    Both `scp.api_server_parts.helpers._safe_fetch_url` (re-export) and
    `scp.core.api_utils.fetch_with_retry` (delegates the I/O here) MUST use
    this implementation. Do NOT add a third fetcher — extend this one instead.
    """
    if not url or not isinstance(url, str):
        raise ValueError("invalid url")
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"scheme not allowed: {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError("missing hostname")
    hostname = parsed.hostname
    # Explicit test/staging egress policy. Production defaults to allow here,
    # while a hardened environment can set SCP_EGRESS_MODE=deny/offline.
    egress_mode = os.environ.get("SCP_EGRESS_MODE", "allow").strip().lower()
    if egress_mode in {"deny", "offline", "disabled"} and hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("external egress disabled by SCP_EGRESS_MODE")
    # Resolve hostname and reject if ANY resolved IP is disallowed.
    # (Checks all getaddrinfo results to mitigate DNS rebinding.)
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed: {exc}") from exc
    if not infos:
        raise ValueError("no DNS records")
    for _family, _stype, _proto, _canon, sockaddr in infos:
        if not sockaddr or not sockaddr[0]:
            continue
        ip_str = sockaddr[0]
        # Strip IPv6 zone id (e.g. fe80::1%eth0) before parsing.
        if "%" in ip_str:
            ip_str = ip_str.split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise ValueError(f"unparseable IP: {ip_str}") from None
        if _is_disallowed_ip(ip):
            raise ValueError("host resolves to disallowed IP range")
    # Safe-redirect + no-proxy opener. [AUDIT-3 FIX] was _NoRedirectHandler
    # (blocked ALL redirects, broke legitimate image CDNs). Now follows ≤5
    # redirects with per-hop IP re-validation.
    opener = urllib.request.build_opener(
        _SafeRedirectHandler,
        urllib.request.ProxyHandler({}),
    )
    req = urllib.request.Request(url, headers={"User-Agent": _SCP_SAFE_FETCH_UA})  # noqa: S310 — scheme validated above
    try:
        with opener.open(req, timeout=timeout) as resp:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"response exceeds max_bytes={max_bytes}")
                chunks.append(chunk)
            return b"".join(chunks)
    except ValueError:
        raise
    except urllib.error.HTTPError as exc:
        raise ValueError(f"HTTP error: {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:  # [FALSE-POS-FIX] B014: TimeoutError IS OSError in Python 3 — redundant
        raise ValueError(f"fetch error: {exc}") from exc


__all__ = [
    "_SCP_SAFE_FETCH_UA",
    "_is_disallowed_ip",
    "_SafeRedirectHandler",
    "_safe_fetch_url",
]
