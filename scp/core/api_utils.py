"""
SCP - Viet Nam | Self-Correcting Pipeline
Copyright (c) 2026 SCP Vietnam Project. All Rights Reserved.




License: See LICENSE file
Contact: scp-vietnam@example.com
"""

"""
SCP V14 — API Utilities
APICache + fetch_with_retry (V29: tích hợp CircuitBreaker).

[Fix 4-a-005 / Phase 3-A — DNA #5, #14, #19]
`fetch_with_retry` is now a THIN WRAPPER around the canonical
`_safe_fetch_url` in `scp.core.url_fetcher`. Previously it had its OWN
urllib.request.urlopen implementation with only a scheme check, NO IP
allowlist, NO redirect policy (urllib follows 30x by default), NO size
cap — divergent from `helpers._safe_fetch_url` which had all those
defenses. ONE safety impl now; this file only adds circuit-breaker +
retry + JSON-parse logic on top.
"""
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("scp.api_utils")

class APICache:
    def __init__(self, ttl=300):
        self.cache: dict[str, tuple[float, Any]] = {}
        self.ttl = ttl

    def _key(self, url_template, entity):
        if isinstance(entity, (list, tuple)):
            entity_str = "|".join(str(e) for e in entity)
        else:
            entity_str = str(entity)
        return f"{url_template}::{entity_str}"

    def get(self, url_template, entity):
        key = self._key(url_template, entity)
        if key in self.cache:
            ts, val = self.cache[key]
            if time.time() - ts < self.ttl:
                return val
            del self.cache[key]
        return None

    def set(self, url_template, entity, value):
        key = self._key(url_template, entity)
        self.cache[key] = (time.time(), value)
        if len(self.cache) > 10000:
            items = sorted(self.cache.items(), key=lambda x: x[1][0])
            for i in range(len(self.cache) // 5):
                del self.cache[items[i][0]]

    def clear(self):
        self.cache.clear()

    def stats(self):
        return {"cache_size": len(self.cache), "ttl_seconds": self.ttl}


# ============================================================
#  CIRCUIT BREAKER REGISTRY — auto-detect API by URL
# ============================================================
def _detect_breaker(url: str):
    """Detect appropriate circuit breaker dựa trên URL."""
    try:
        from scp.core.circuit_breaker import (
            CircuitBreakerRegistry,
            get_coingecko_breaker,
            get_frankfurter_breaker,
            get_openmeteo_breaker,
            get_pubchem_breaker,
            get_restcountries_breaker,
            get_wikipedia_breaker,
        )
        url_lower = url.lower()
        if 'pubchem.ncbi.nlm.nih.gov' in url_lower:
            return get_pubchem_breaker()
        if 'coingecko.com' in url_lower:
            return get_coingecko_breaker()
        if 'frankfurter.app' in url_lower:
            return get_frankfurter_breaker()
        if 'open-meteo.com' in url_lower:
            return get_openmeteo_breaker()
        if 'wikipedia.org' in url_lower:
            return get_wikipedia_breaker()
        if 'restcountries.com' in url_lower:
            return get_restcountries_breaker()
        # Generic breaker cho APIs khác
        if 'api.' in url_lower or 'http' in url_lower:
            # Use domain as breaker name
            from urllib.parse import urlparse
            domain = urlparse(url).netloc or "unknown"
            return CircuitBreakerRegistry().get(domain, fail_threshold=5, cooldown_sec=60)
        return None
    except Exception as e:
        logger.debug(f"Breaker detect error: {e}")
        return None


# [Fix 4-a-005 / Phase 3-A] `_validate_url_safe` was the INCOMPLETE safety
# check (scheme-only, no IP allowlist, no redirect policy). It has been
# REMOVED — the canonical safety check now lives inside
# `scp.core.url_fetcher._safe_fetch_url` (scheme + IP allowlist + redirect
# re-validation + size cap + no-proxy opener). `fetch_with_retry` delegates
# ALL HTTP I/O to `_safe_fetch_url`. Do NOT re-add a local validator — that
# would re-introduce the divergent-implementation anti-pattern (DNA #5/#14).
import urllib.parse as _url_parse  # noqa: E402  (kept for legacy callers that may `from api_utils import _url_parse`)


def fetch_with_retry(url, headers, timeout=10, max_retries=3):
    """ Fetch URL với retry + circuit breaker.

    [Fix 4-a-005 / Phase 3-A — DNA #5, #14, #19]
    PREVIOUSLY: this function had its OWN `urllib.request.urlopen` call
    with only a scheme check (`_validate_url_safe`), NO IP allowlist, NO
    redirect policy (urllib follows 30x by default), NO size cap. A second
    fetcher `helpers._safe_fetch_url` had ALL these defenses — divergent
    impls of "safe URL fetch". DNA #5: scanners saw `_validate_url_safe`
    and assumed safety. DNA #14: same name "safe fetch" ≠ same safety.

    NOW: the actual HTTP I/O is delegated to the canonical `_safe_fetch_url`
    in `scp.core.url_fetcher`. This function keeps its circuit-breaker +
    retry + JSON-parsing contract (returns dict | None), but ALL safety
    defenses (scheme allowlist, IP range check, redirect re-validation,
    size cap, no-proxy opener) live in ONE place. If `_safe_fetch_url`
    adds a new defense, `fetch_with_retry` inherits it automatically.

    Behavior:
      - Returns parsed JSON dict on success.
      - Returns None on: SSRF/policy block (logged warning, no retry);
        HTTP error after retries exhausted; network error after retries
        exhausted; JSON decode failure (server responded, bad payload).
      - Circuit breaker: opens after 5 failures per domain, then skip
        all calls to that domain for cooldown_sec (60s default).

    Args:
        url: URL to fetch (must be http/https, must NOT resolve to a
            private/loopback/link-local/reserved IP).
        headers: IGNORED — _safe_fetch_url uses the canonical
            _SCP_SAFE_FETCH_UA (strict UA is an SSRF defense; accepting
            arbitrary caller UAs would re-introduce the divergent-fetcher
            risk). Kept in signature for backward-compat with callers
            that pass `{"User-Agent": "..."}`.
        timeout: per-request timeout in seconds (default 10).
        max_retries: max retry attempts on HTTP/network error (default 3).
            SSRF/policy blocks do NOT retry (retrying won't fix policy).
    """
    if headers is None:
        headers = {"User-Agent": "SCP/1.0"}

    #  Check circuit breaker
    breaker = _detect_breaker(url)
    if breaker and not breaker.allow():
        logger.debug(f"[CircuitBreaker] Skip call to {url} (OPEN)")
        return None

    # [Fix 4-a-005] Lazy import of the canonical safe fetcher (avoids
    # module-load-time circular import — url_fetcher is leaf-level but
    # this keeps the dependency direction explicit).
    from scp.core.url_fetcher import _safe_fetch_url

    for attempt in range(max_retries):
        try:
            # _safe_fetch_url enforces: scheme allowlist + IP/private-range
            # check + safe-redirect handler (≤5 hops, per-hop re-validation)
            # + size cap (5MB default) + no-proxy opener + strict UA.
            # We just JSON-parse the bytes and apply circuit-breaker logic.
            raw = _safe_fetch_url(url, timeout=timeout)
            if breaker:
                breaker.record_success()
            try:
                return json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                # [V104.34 #41] Server responded with valid HTTP 200 but the
                # body wasn't valid JSON. Treat as successful fetch (breaker
                # happy) — the API was reachable, just bad payload.
                logger.warning(f"[fetch_with_retry] JSON decode failed for {url}: {e}")
                return None
        except ValueError as e:
            # _safe_fetch_url raises ValueError for BOTH policy violations
            # (SSRF blocks) AND wrapped HTTP/network errors. Distinguish:
            msg = str(e)
            msg_lower = msg.lower()
            is_http_error = msg_lower.startswith("http error:")
            is_fetch_error = msg_lower.startswith("fetch error:")
            if is_http_error or is_fetch_error:
                # Server-side or network error → record breaker failure + retry.
                if breaker:
                    breaker.record_failure(reason=msg[:100])
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                continue
            # SSRF/policy block (e.g., "host resolves to disallowed IP range",
            # "scheme not allowed", "missing hostname", "invalid url",
            # "DNS resolution failed", "no DNS records", "unparseable IP",
            # "redirect ...", "response exceeds max_bytes=...").
            # Do NOT retry (retrying won't fix a policy block) and do NOT
            # record breaker failure (the API is fine; the URL is the problem).
            logger.warning(f"[SSRF] {url} blocked by _safe_fetch_url: {msg}")
            return None
        except OSError as e:
            # Belt-and-suspenders: _safe_fetch_url wraps OSError as
            # ValueError("fetch error: ..."), but if a new error type
            # sneaks through, catch it here. Treat as network failure.
            if breaker:
                breaker.record_failure(reason=str(e)[:100])
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            continue
    return None
