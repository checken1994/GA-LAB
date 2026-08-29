"""
SCP LLM Gateway — Unified LLM client (API-only).

Single source of truth for ALL LLM calls in SCP (inference + learning).

TẠI SAO không còn OllamaProvider (2026-08-29):
  Ollama local đã bị gỡ khỏi deployment. Toàn bộ tầng Ollama (provider,
  TASK_MODEL_MAP, provider_mode "ollama_only"/"auto", check_startup probe
  11434) là dead code trên đường sống → bị xóa thay vì khóa bằng config
  (Clean Workspace: code không dùng phải xóa; test phải test reality mới).
  Gateway giờ chỉ gọi OpenRouter API trực tiếp.

Design:
  - Async-first (httpx.AsyncClient) for inference path (/ask)
  - chat_sync() wrapper for background threads (learning engines)
  - Task routing: mỗi task có một OpenRouterProvider riêng
    (primary = OPENROUTER_MODEL, free fallback per task, key round-robin)
  - Singleton get_gateway() — shared connection pool, thread-safe init
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import os
import threading

import httpx

logger = logging.getLogger("scp.llm_gateway")

# Sync wrapper hard timeout: OpenRouter client timeout is 60s inside
# _call_model; the sync wrapper adds headroom for thread-pool scheduling.
SYNC_CALL_TIMEOUT_SECONDS = 90

# ============================================================
# [OPENROUTER-FREE-FIX] REGISTRY OF ALL 17 FREE MODELS ON OPENROUTER
# ============================================================
# Verified via https://openrouter.ai/api/v1/models on 2026-08-06.
# All have pricing.prompt=0 AND pricing.completion=0 (cost $0).
# Use this list when you need to iterate over ALL free models (e.g. for
# fallback chains, model rotation, or auto-discovery).
# ============================================================
OPENROUTER_FREE_MODELS: list[str] = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",            # 550B, 1M ctx — strongest
    "nvidia/nemotron-3-super-120b-a12b:free",            # 120B, 262K ctx — balanced
    "google/gemma-4-31b-it:free",                        # 31B, 262K ctx — factual, multimodal
    "google/gemma-4-26b-a4b-it:free",                    # 26B, 262K ctx — multimodal
    "nvidia/nemotron-3-nano-30b-a3b:free",               # 30B, 256K ctx — mid-tier
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", # 30B, 256K ctx — audio+image+video
    "cohere/north-mini-code:free",                       # 256K ctx — code-focused
    "inclusionai/ling-3.0-tiny:free",                    # 262K ctx — multilingual
    "poolside/laguna-s-2.1:free",                        # 262K ctx — code
    "poolside/laguna-xs-2.1:free",                       # 262K ctx — code (smaller)
    "openrouter/free",                                   # 200K ctx — auto-router (picks any free)
    "openai/gpt-oss-20b:free",                           # 20B, 131K ctx — fast
    "nvidia/nemotron-3.5-content-safety:free",           # 128K ctx — content moderation
    "nvidia/nemotron-nano-12b-v2-vl:free",               # 12B, 128K ctx — image+video
    "nvidia/nemotron-nano-9b-v2:free",                   # 9B, 128K ctx — fastest
    "google/lyria-3-pro-preview",                        # 1M ctx — image generation
    "google/lyria-3-clip-preview",                       # 1M ctx — image generation
]


from scp.security.provider_keys import ProviderCredentialError, load_openrouter_keys

class OpenRouterProvider:
    """OpenRouter cloud LLM provider — PAID primary + FREE fallback.

    Architecture:
      1. PRIMARY: PAID model (OPENROUTER_MODEL env) — used for ALL tasks by default.
      2. FALLBACK: FREE models (cost $0) — used when PAID model fails
         (rate limit, quota exhausted, network error).
         Task-specific FREE model selected from TASK_FREE_FALLBACK_MAP.
      3. 3 API KEYS round-robin: OPENROUTER_API_KEY, _2, _3 — rotates per call
         to avoid 20 req/min rate limit per key. Effective: 60 req/min total.

    Fallback chain per call:
      1. Try PAID model with key rotation
      2. If 429/402/quota → try task-specific FREE model
      3. If still fails → try openrouter/free (auto-router, picks any free)
      4. If still fails → return None (caller sees provider "none" and must
         fail closed — no answer is fabricated)
    """

    # Task → FREE fallback model. Used ONLY when PAID model fails.
    # All defaults are FREE (cost $0), verified on 2026-08-06.
    TASK_FREE_FALLBACK_MAP: dict[str, str] = {
        "autofix":       "nvidia/nemotron-3-ultra-550b-a55b:free",
        "why":           "google/gemma-4-31b-it:free",
        "learning":      "google/gemma-4-31b-it:free",
        "fast_learning": "nvidia/nemotron-3-nano-30b-a3b:free",
        "judge":         "nvidia/nemotron-3-super-120b-a12b:free",
        "chat":          "openai/gpt-oss-20b:free",
        "default":       "openai/gpt-oss-20b:free",
    }

    # Class-level: 3 API keys + round-robin iterator (shared across all instances)
    _API_KEYS: list[str] = []
    _key_cycle: itertools.cycle | None = None
    _key_lock = threading.Lock()

    @classmethod
    def _init_keys(cls) -> None:
        """Load API keys from env vars (3 keys supported for round-robin)."""
        if cls._API_KEYS:
            return  # already loaded
        try:
            keys = load_openrouter_keys()
        except ProviderCredentialError as exc:
            logger.error("[LLM Gateway] provider credential configuration rejected: %s", str(exc))
            keys = []
        cls._API_KEYS = keys
        if keys:
            cls._key_cycle = itertools.cycle(keys)

    @classmethod
    def _next_key(cls) -> str:
        """Get next API key (round-robin). Returns '' if no keys configured."""
        cls._init_keys()
        with cls._key_lock:
            if cls._key_cycle is None:
                return ""
            return next(cls._key_cycle)

    def __init__(self, task: str = "default"):
        self.task = task
        # PRIMARY: PAID model (user's OPENROUTER_MODEL) — used FIRST for ALL tasks.
        self.model = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash-0731")
        # FREE fallback for this task (used if PAID fails with 429/402/quota)
        self.free_fallback = os.environ.get(
            f"OPENROUTER_MODEL_{task.upper()}",
            self.TASK_FREE_FALLBACK_MAP.get(task, self.TASK_FREE_FALLBACK_MAP["default"]),
        )
        self.base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self._client: httpx.AsyncClient | None = None
        # [Fix 4-a-014] Race condition on lazy _client init — two concurrent
        # _call_model() calls could both see _client is None, both create an
        # httpx.AsyncClient, and one would leak. asyncio.Lock + double-checked
        # init closes the race. DNA #9 (no harm — leaked httpx clients).
        self._client_lock = asyncio.Lock()

    @property
    def api_key(self) -> str:
        """Current API key (round-robin across 3 keys)."""
        return self._next_key()

    @property
    def enabled(self) -> bool:
        """True if at least one non-placeholder API key is configured."""
        self._init_keys()
        return len(self._API_KEYS) > 0

    async def _call_model(self, model: str, messages: list[dict], api_key: str) -> tuple[str | None, str | None]:
        """Call a specific model with a specific key. Returns (answer, error)."""
        try:
            # [Fix 4-a-014] Double-checked locking — only the first concurrent
            # caller creates _client; subsequent callers see it set + skip
            # the lock entirely (no contention on the hot path).
            if self._client is None:
                async with self._client_lock:
                    if self._client is None:
                        self._client = httpx.AsyncClient(timeout=60.0)
            resp = await self._client.post(
                f"{self.base_url}/chat/completions",
                json={"model": model, "messages": messages, "stream": False},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://scp-vietnam.local",
                    "X-Title": "SCP Gateway",
                },
            )
            # 429 = rate limit, 402 = payment required (quota exhausted)
            if resp.status_code in (429, 402):
                return None, f"HTTP {resp.status_code} (quota/rate-limit)"
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return (answer or None, None)
        except Exception as e:
            return None, str(e)

    async def chat(self, question: str, context: str = "", system_prompt: str = "") -> tuple[str | None, str]:
        """Chat with LLM. Returns (answer, provider_name).

        Fallback chain:
          1. PAID model (OPENROUTER_MODEL) with key rotation
          2. FREE task-specific fallback (e.g. nemotron-ultra for autofix)
          3. openrouter/free (auto-router, picks any available free model)
        """
        if not self.enabled:
            return None, "none"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if context:
            messages.append({"role": "user", "content": context})
        messages.append({"role": "user", "content": question})

        # Layer 1: PAID model (try up to 3 keys = 1 round)
        for _attempt in range(min(3, len(self._API_KEYS))):
            key = self._next_key()
            answer, err = await self._call_model(self.model, messages, key)
            if answer:
                return answer, f"openrouter:{self.model}"
            if err and "quota" not in err.lower() and "rate-limit" not in err.lower() and "429" not in err and "402" not in err:
                # Non-quota error (network, 500, etc.) — don't retry with same model
                logger.debug(f"OpenRouter PAID ({self.model}) failed: {err}")
                break
            logger.debug(f"OpenRouter PAID ({self.model}) key failed: {err}, trying next key")

        # Layer 2: FREE task-specific fallback
        if self.free_fallback != self.model:  # avoid retrying same model
            key = self._next_key()
            answer, err = await self._call_model(self.free_fallback, messages, key)
            if answer:
                logger.info(f"OpenRouter PAID failed, FREE fallback succeeded: {self.free_fallback}")
                return answer, f"openrouter:{self.free_fallback}"
            logger.debug(f"OpenRouter FREE fallback ({self.free_fallback}) failed: {err}")

        # Layer 3: openrouter/free (auto-router, picks any available free model)
        if self.free_fallback != "openrouter/free":
            key = self._next_key()
            answer, err = await self._call_model("openrouter/free", messages, key)
            if answer:
                logger.info("OpenRouter auto-router (openrouter/free) succeeded")
                return answer, "openrouter:openrouter/free"
            logger.debug(f"OpenRouter auto-router failed: {err}")

        # No answer was produced by any configured model. Do not return the
        # primary model label here: callers use the provider field as an
        # evidence signal, so a failed chain must be explicit.
        return None, "none"

    def stats(self) -> dict:
        self._init_keys()
        return {
            "configured": self.enabled,
            "num_keys": len(self._API_KEYS),
            "primary_model": self.model,
            "free_fallback": self.free_fallback,
            "task": self.task,
            "total_free_models_available": len(OPENROUTER_FREE_MODELS),
        }


# ============================================================
# GATEWAY — single entry point with task routing
# ============================================================

class LLMGateway:
    """Unified LLM gateway — OpenRouter API only, routed per task.

    Task routing (primary model is OPENROUTER_MODEL for every task; the
    per-task provider differs only in its FREE fallback model):
        task="autofix"       → free fallback nemotron-3-ultra-550b:free
        task="why"           → free fallback gemma-4-31b-it:free
        task="learning"      → free fallback gemma-4-31b-it:free
        task="fast_learning" → free fallback nemotron-3-nano-30b:free
        task="judge"         → free fallback nemotron-3-super-120b:free
        task="chat"          → free fallback gpt-oss-20b:free
        task="default"       → free fallback gpt-oss-20b:free

    Usage (async):
        gw = get_gateway()
        answer, provider = await gw.chat("What is 2+2?", task="default")

    Usage (sync — for background threads):
        answer, provider = chat_sync("What is 2+2?", task="learning")
    """

    def __init__(self):
        # One OpenRouterProvider per task (differs only in FREE fallback).
        self.openrouter_autofix  = OpenRouterProvider(task="autofix")
        self.openrouter_why      = OpenRouterProvider(task="why")
        self.openrouter_learning = OpenRouterProvider(task="learning")
        self.openrouter_fast     = OpenRouterProvider(task="fast_learning")
        self.openrouter_judge    = OpenRouterProvider(task="judge")
        self.openrouter_default  = OpenRouterProvider(task="default")
        # Backward-compat aliases — old code used `gateway.openrouter`.
        self.openrouter = self.openrouter_default
        # Alias: openrouter_fast_learning (matches the old ollama_fast pattern)
        self.openrouter_fast_learning = self.openrouter_fast
        self._stats = {
            "total_calls": 0,
            "openrouter_calls": 0,
            "failures": 0,
        }

    async def chat(
        self,
        question: str,
        context: str = "",
        system_prompt: str = "",
        task: str = "default",
    ) -> tuple[str | None, str]:
        """Chat with LLM. Returns (answer, provider_name)."""
        self._stats["total_calls"] += 1
        openrouter_provider = {
            "autofix":       self.openrouter_autofix,
            "why":           self.openrouter_why,
            "learning":      self.openrouter_learning,
            "fast_learning": self.openrouter_fast,
            "judge":         self.openrouter_judge,
            "chat":          self.openrouter_default,
        }.get(task, self.openrouter_default)

        if openrouter_provider.enabled:
            self._stats["openrouter_calls"] += 1
            answer, _ = await openrouter_provider.chat(question, context, system_prompt)
            if answer:
                return answer, f"openrouter:{openrouter_provider.model}"

        self._stats["failures"] += 1
        return None, "none"

    def chat_sync(
        self,
        question: str,
        context: str = "",
        system_prompt: str = "",
        task: str = "default",
    ) -> tuple[str | None, str]:
        """Sync wrapper for background threads. Runs async chat safely.

        [RUNTIME-FIX-2] Root cause (runtime log line 732, 941):
          RuntimeWarning: coroutine 'LLMGateway.chat' was never awaited
        Bug: `loop.run_until_complete(self.chat(...))` evaluates self.chat(...)
        FIRST, creating a coroutine object. If run_until_complete raises (e.g.
        'event loop already running' inside async thread, or RuntimeError on
        loop creation), the coroutine object is never awaited and never closed
        -> leaks memory + GC pressure. In production 24/7 this means thousands
        of leaked coroutines per day.

        Fix: hold the coroutine reference explicitly. On ANY exception path,
        call coro.close() to release it cleanly. Use asyncio.run() (which
        handles loop creation+close properly) instead of manual loop management.
        Detect 'event loop already running' and fall back to ThreadPoolExecutor
        so we don't nest event loops.
        """
        coro = self.chat(question, context, system_prompt, task=task)
        try:
            # Detect if we're already inside an async context (event loop running).
            # In that case, asyncio.run() would raise RuntimeError. Fall back to
            # running in a fresh thread with its own event loop.
            try:
                asyncio.get_running_loop()
                _in_async = True
            except RuntimeError:
                _in_async = False

            if _in_async:
                # We're inside async code (e.g. called from async def without await).
                # Run the coroutine in a separate thread to avoid 'loop already running'.
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result(timeout=SYNC_CALL_TIMEOUT_SECONDS)
            else:
                # Normal sync context — asyncio.run handles loop lifecycle properly.
                return asyncio.run(coro)
        except Exception as e:
            # CRITICAL: ensure coroutine is closed to prevent leak.
            # RuntimeWarning 'coroutine was never awaited' happens when coro
            # is created but never awaited AND never closed.
            # [SCP-DNA-FIX R5-5] TẠI SAO: Python 3 semantic — `except Exception
            # as e:` DELETES `e` on exit of the except block (PEP 3110). The
            # inner `try/except` below calls `coro.close()`, and if coro.close()
            # raises, the inner except's exit deletes its OWN `e` — but the
            # outer `e` is ALSO already gone by the time we reach the
            # `logger.warning(f"chat_sync failed: {e}")` line below, raising
            # NameError. Breaks the chat_sync fail-open contract (returns
            # (None, "none") on error). mypy [misc] "Trying to read deleted
            # variable e" caught it. Fix: snapshot `e` into a local `_err`
            # BEFORE the inner try so it survives the inner-except deletion.
            _err = e  # save before inner try deletes e
            try:
                coro.close()
            except Exception as e:
                logger.exception("[client.py:608] silenced exception")
            logger.warning(f"chat_sync failed: {_err}")  # upgrade debug->warning for observability
            self._stats["failures"] += 1
            return None, "none"

    def stats(self) -> dict:
        return {
            **self._stats,
            "openrouter_default":  self.openrouter_default.stats(),
            "openrouter_autofix":  self.openrouter_autofix.stats(),
            "openrouter_why":      self.openrouter_why.stats(),
            "openrouter_learning": self.openrouter_learning.stats(),
            "openrouter_fast":     self.openrouter_fast.stats(),
            "openrouter_judge":    self.openrouter_judge.stats(),
        }


# ============================================================
# SINGLETON (thread-safe — EXEC-2 R3)
# ============================================================
# FRESH-2 finding: bare `if _gateway is None: _gateway = LLMGateway()` had no
# lock. Two concurrent first-callers (e.g. /ask hit while a learning thread
# boots) would both pass the None check and create duplicate LLMGateway
# instances — leaking httpx.AsyncClient connection pools and breaking the
# shared-stats invariant. Fix: double-checked locking with threading.Lock.
# ============================================================

_gateway: LLMGateway | None = None
_gateway_lock = threading.Lock()


def get_gateway() -> LLMGateway:
    """Get or create the singleton LLM gateway (thread-safe)."""
    global _gateway
    if _gateway is None:
        with _gateway_lock:
            # Re-check inside lock — another thread may have created it while
            # we were waiting.
            if _gateway is None:
                _gateway = LLMGateway()
    return _gateway


def chat_sync(
    question: str,
    context: str = "",
    system_prompt: str = "",
    task: str = "default",
) -> tuple[str | None, str]:
    """Module-level sync shortcut. Uses singleton gateway."""
    return get_gateway().chat_sync(question, context, system_prompt, task=task)
