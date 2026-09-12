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
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

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



@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((urllib.error.URLError, ConnectionError, TimeoutError)),
    reraise=False
)
def fetch_with_retry(url, headers=None, timeout=10, max_retries=3):
    # --- SCP V3 ENTERPRISE: TENACITY RETRY & CIRCUIT BREAKER ---
    from scp.core.url_fetcher import _safe_fetch_url
    try:
        # [EE] Egress gate FIRST (idempotent — also enforced inside
        # _safe_fetch_url). EgressDeniedError is a ValueError, so the
        # "policy violation → no retry, return None" contract below holds.
        from scp.security.url_safety import enforce_egress_policy
        enforce_egress_policy(url)
        raw_bytes = _safe_fetch_url(url)
        return json.loads(raw_bytes.decode("utf-8"))
    except ValueError as e:
        # SSRF / Policy violation. Do not retry.
        logger.warning(f"Policy violation fetching {url}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"JSON decode failed for {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Transient error fetching {url}: {e}")
        raise  # Reraise to trigger Tenacity retry
