"""
SCP LLM Gateway — Unified LLM access layer.

Package-bound enforcement order:
  1. egress guard — destination/network authority;
  2. Z2 zero-cost PEP — fresh exact-$0 proof immediately before driver;
  3. Z3 free-only router — filters candidates before retry/failover;
  4. multimodal adapter — structured Vision messages reuse the same PEPs.

Z2 remains authoritative even if Z3, Vision, or any caller chooses the wrong model.
"""
from scp.llm_gateway import client as _client
from scp.llm_gateway.egress_policy import install_egress_guard
from scp.llm_gateway.multimodal_adapter import install_multimodal_gateway_adapter
from scp.llm_gateway.zero_cost_runtime import (
    install_free_only_provider_router,
    install_openai_compatible_provider_pep,
)

install_egress_guard(_client.OpenRouterProvider)
install_openai_compatible_provider_pep(_client.OpenRouterProvider)
install_free_only_provider_router(_client.OpenRouterProvider)
install_multimodal_gateway_adapter(_client.OpenRouterProvider, _client.LLMGateway)

LLMGateway = _client.LLMGateway
get_gateway = _client.get_gateway
chat_sync = _client.chat_sync

__all__ = ["LLMGateway", "get_gateway", "chat_sync"]
