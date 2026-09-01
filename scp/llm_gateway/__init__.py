"""
SCP LLM Gateway — Unified LLM access layer.

TÁI SAO tách riêng: trước đây có 3 bản implement LLM call:
  1. runtime/llm_client.py (async httpx, retry, fallback) — inference path
  2. core/fast_learning_engine.py::_ask_llm_sync (sync urllib, no retry) — learning
  3. core/real_learning_engine.py::_ask_llm (sync urllib, no retry) — learning

3 bản diverge trên 7 chiều: sync/async, endpoint, retry, prompt template,
token limit, stats, singleton. Learning path không có retry/fallback →
1 network glitch = mất câu hỏi. Inference path có retry nhưng learning
không được hưởng.

[ARCH-1 FIX] Tách thành 1 gateway duy nhất:
  - Async-first (httpx) + sync wrapper (cho background threads)
  - Provider adapters: OpenRouter (primary), EnvCompatProvider (fallback via OPENAI_API_KEY / SCP_LLM_FALLBACK_PROVIDERS)
  - ProviderRouter: ordered failover (OpenRouter → env-declared providers)
  - Singleton get_gateway() shared by inference + learning
  - One fail-closed outbound policy at the provider transport boundary
"""
from scp.llm_gateway import client as _client
from scp.llm_gateway.egress_policy import install_egress_guard

install_egress_guard(_client.OpenRouterProvider)

LLMGateway = _client.LLMGateway
get_gateway = _client.get_gateway
chat_sync = _client.chat_sync

__all__ = ["LLMGateway", "get_gateway", "chat_sync"]
