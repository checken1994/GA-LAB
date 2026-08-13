"""[V104.34 #34] memory_manager — wraps SmartCache via get_smart_cache().

TẠI SAO: Behavioral test expects this module to use the factory function
(not the deprecated singleton accessor).
The module was previously deleted during a refactor but the test + expected
behavior remain. This restore provides a thin memory-manager facade.

DNA SCP: If a test verifies a behavior contract, the contract must be honored
even after refactors. Either restore the module OR delete the test — but
don't leave the test failing silently (that hides real regressions).
"""
from __future__ import annotations

from scp.core.smart_cache import get_smart_cache, SmartCache


class MemoryManager:
    """Thin wrapper around the global SmartCache instance.

    Uses get_smart_cache() (factory) instead of the deprecated singleton pattern
    (deprecated singleton) per V104.34 #34 fix.

    [SCP-DNA-FIX] SmartCache exposes a NAMESPACED API:
        get(namespace, identifier) / set(namespace, identifier, value, source="")
        / invalidate(namespace, identifier) / clear() / stats()
    The previous MemoryManager passed a flat `key` as the first positional arg,
    which:
      - get(key, default) -> TypeError (missing `identifier`) OR wrong-arg-type
      - set(key, value, ttl) -> TypeError (value passed as `identifier`)
      - delete(key) -> AttributeError (SmartCache has no `delete`, only `invalidate`)
    Every call crashed. They were swallowed by callers' try/except -> silent.
    Fix: bridge the flat-key facade to SmartCache's (namespace, identifier)
    contract using a fixed namespace "memmgr".
    """

    _NS = "memmgr"  # namespace for MemoryManager's flat-key facade

    def __init__(self):
        # [V104.34 #34] Use factory function, not deprecated singleton.
        self._cache: SmartCache = get_smart_cache()

    def get(self, key: str, default=None):
        """Retrieve a cached value by key."""
        val = self._cache.get(self._NS, key)
        return val if val is not None else default

    def set(self, key: str, value, ttl: int | None = None) -> None:
        """Store a value in cache.

        NOTE: SmartCache derives TTL internally from `source` (via _get_ttl).
        The `ttl` arg is accepted for API backward-compat but cannot be pushed
        down to SmartCache.set(); callers needing custom TTL must use SmartCache
        directly. This is documented rather than silently ignored.
        """
        _ = ttl  # accepted for backward-compat; SmartCache manages TTL via source
        self._cache.set(self._NS, key, value, source="memmgr")

    def delete(self, key: str) -> bool:
        """Invalidate a key from cache. Returns True (SmartCache.invalidate is
        fire-and-forget — it does not report whether the key existed)."""
        self._cache.invalidate(self._NS, key)
        return True

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def stats(self) -> dict:
        """Return cache statistics."""
        return self._cache.stats() if hasattr(self._cache, "stats") else {}


__all__ = ["MemoryManager", "get_smart_cache"]
