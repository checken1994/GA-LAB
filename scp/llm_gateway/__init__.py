"""
SCP LLM Gateway — Unified LLM access layer.

The package installs both outbound policy boundaries on the concrete provider
method before callers receive LLMGateway/get_gateway:
  1. egress policy (destination/network authority)
  2. zero-cost policy (fresh $0 proof + data-class authority)

Routing is not trusted to enforce either invariant; a buggy/fallback router is
still checked immediately before the provider network driver.
"""
from scp.llm_gateway import client as _client
from scp.llm_gateway.egress_policy import install_egress_guard
from scp.llm_gateway.zero_cost_runtime import install_openai_compatible_provider_pep

install_egress_guard(_client.OpenRouterProvider)
install_openai_compatible_provider_pep(_client.OpenRouterProvider)

LLMGateway = _client.LLMGateway
get_gateway = _client.get_gateway
chat_sync = _client.chat_sync

__all__ = ["LLMGateway", "get_gateway", "chat_sync"]
