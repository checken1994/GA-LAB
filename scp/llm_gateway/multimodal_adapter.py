"""Structured multimodal adapters for the canonical LLM gateway.

The historical V104/V105 VisionHandler called Ollama directly.  This adapter
adds structured-message support to the current OpenRouterProvider/LLMGateway
at package composition time, without modifying the large legacy client
monolith.  Every model candidate still crosses the current exact-$0, privacy
and egress PEPs before transport.
"""
from __future__ import annotations

from typing import Any


def install_multimodal_gateway_adapter(provider_cls: type, gateway_cls: type) -> None:
    if getattr(provider_cls, "_scp_multimodal_adapter_installed", False):
        return

    async def provider_chat_messages(self: Any, messages: list[dict], *, data_class: str = "INTERNAL"):
        from scp.llm_gateway.zero_cost_guard import ZeroCostDecision, ZeroCostDenied
        from scp.llm_gateway.zero_cost_runtime import authorize_outbound, outbound_data_class

        if not self.enabled:
            return None, "none"

        candidates: list[str] = []
        for candidate in (
            getattr(self, "free_fallback", ""),
            getattr(self, "model", ""),
            "openrouter/free" if getattr(self, "PROVIDER_NAME", "") == "openrouter" else "",
        ):
            candidate = str(candidate or "").strip()
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        eligible: list[str] = []
        blocked_for_proof = False
        with outbound_data_class(data_class):
            for model in candidates:
                try:
                    authorize_outbound(
                        provider=getattr(self, "PROVIDER_NAME", "unknown"),
                        model=model,
                        task_class=getattr(self, "task", "vision"),
                        data_class=data_class,
                    )
                    eligible.append(model)
                except ZeroCostDenied as exc:
                    if exc.decision in {
                        ZeroCostDecision.DENY_UNKNOWN_PRICE,
                        ZeroCostDecision.DENY_STALE_PRICE,
                    }:
                        blocked_for_proof = True

            if not eligible:
                return None, "blocked_zero_cost_proof" if blocked_for_proof else "blocked_no_qualified_free_model"

            quota_seen = False
            for model in eligible:
                for _ in range(min(3, max(1, int(self._key_count())))):
                    answer, error = await self._call_model(model, messages, self._next_key())
                    if answer:
                        return answer, f"{getattr(self, 'PROVIDER_NAME', 'provider')}:{model}"
                    error_text = str(error or "").lower()
                    if any(sig in error_text for sig in ("429", "402", "quota", "rate-limit")):
                        quota_seen = True
                        continue
                    break
        return None, "waiting_free_quota" if quota_seen else "none"

    async def gateway_chat_messages(
        self: Any,
        messages: list[dict],
        *,
        task: str = "vision",
        data_class: str = "INTERNAL",
    ):
        """Route structured messages via existing providers without flattening image content."""
        self._stats["total_calls"] += 1
        # Reuse canonical OpenRouter provider mechanics, but instantiate with
        # the semantic task class so pricing/telemetry records say "vision".
        provider = provider_cls(task=task)
        if not provider.enabled:
            self._stats["failures"] += 1
            return None, "none"
        answer, label = await provider.chat_messages(messages, data_class=data_class)
        if answer:
            return answer, label
        self._stats["failures"] += 1
        return None, label

    provider_cls.chat_messages = provider_chat_messages
    gateway_cls.chat_messages = gateway_chat_messages
    provider_cls._scp_multimodal_adapter_installed = True
    gateway_cls._scp_multimodal_adapter_installed = True
