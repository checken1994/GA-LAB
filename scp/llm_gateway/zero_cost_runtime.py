"""Runtime adapters for the P0 zero-cost LLM wall.

Z2 installs a PEP immediately before provider network drivers.
Z3 replaces the legacy paid-primary provider chat semantics with candidate
filtering that only attempts models carrying a fresh exact-$0 proof. The PEP
remains installed underneath Z3 so routing bugs still cannot spend money.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from scp.contracts.data_class import DataClass
from scp.governance.privacy import PrivacyWriteGate
from scp.llm_gateway.zero_cost_guard import (
    PricingProof,
    PricingProofStore,
    ZeroCostDecision,
    ZeroCostDenied,
    ZeroCostGuard,
    ZeroCostRequest,
)

_ROOT = Path(__file__).resolve().parents[2]
_lock = threading.Lock()
_store: PricingProofStore | None = None
_guard: ZeroCostGuard | None = None


def _runtime_store_path() -> Path:
    """Resolve an isolated proof store only inside an explicit test data root."""
    configured = str(os.environ.get("SCP_ZERO_COST_PROOF_DB", "")).strip()
    if not configured:
        return _ROOT / "data" / "foundation" / "zero_cost.sqlite"
    if str(os.environ.get("SCP_MODE", "")).strip().lower() != "test":
        raise RuntimeError("SCP_ZERO_COST_PROOF_DB is restricted to SCP_MODE=test")
    data_root_value = str(os.environ.get("SCP_DATA_DIR", "")).strip()
    if not data_root_value:
        raise RuntimeError("SCP_ZERO_COST_PROOF_DB requires SCP_DATA_DIR")
    data_root = Path(data_root_value).expanduser().resolve()
    candidate = Path(configured).expanduser().resolve()
    try:
        candidate.relative_to(data_root)
    except ValueError as exc:
        raise RuntimeError("SCP_ZERO_COST_PROOF_DB must stay inside SCP_DATA_DIR") from exc
    return candidate


def get_runtime_guard() -> ZeroCostGuard:
    global _store, _guard
    if _guard is None:
        with _lock:
            if _guard is None:
                ZeroCostGuard.validate_free_only_config()
                _store = PricingProofStore(_runtime_store_path())
                _guard = ZeroCostGuard(
                    _store,
                    privacy_gate=PrivacyWriteGate(_ROOT / "spec" / "data_policies.yaml"),
                    require_evidence_id=True,
                )
    return _guard


def _request(
    *,
    provider: str,
    model: str,
    task_class: str,
    data_class: DataClass | str | None,
) -> ZeroCostRequest:
    return ZeroCostRequest(
        provider=str(provider).strip().lower(),
        model=str(model).strip(),
        task_class=str(task_class).strip() or "default",
        data_class=data_class,
    )


def authorize_outbound(
    *,
    provider: str,
    model: str,
    task_class: str,
    data_class: DataClass | str | None = DataClass.INTERNAL,
):
    """Authorize one outbound model call at the transport boundary.

    Dispatch never refreshes pricing. Discovery is an independent scheduled
    concern: missing/stale/partial proof must deny before any provider call.
    """
    request = _request(
        provider=provider,
        model=model,
        task_class=task_class,
        data_class=data_class,
    )
    guard = get_runtime_guard()
    proof = guard.authorize(request)
    return request, proof


def record_outbound_sent(request: ZeroCostRequest, proof: PricingProof | None) -> str:
    return get_runtime_guard().record_sent(request, proof)


def install_openai_compatible_provider_pep(provider_cls: type) -> bool:
    """Install Z2 immediately before provider_cls' concrete network call."""
    if getattr(provider_cls, "_scp_zero_cost_pep_installed", False):
        return False
    original = getattr(provider_cls, "_call_model_once", None)
    if original is None:
        raise AttributeError("provider class has no _call_model_once boundary")

    async def guarded(self: Any, model: str, messages: list[dict], api_key: str):
        try:
            request, proof = authorize_outbound(
                provider=getattr(self, "PROVIDER_NAME", "unknown"),
                model=model,
                task_class=getattr(self, "task", "default"),
                data_class=getattr(self, "_scp_data_class", DataClass.INTERNAL),
            )
        except ZeroCostDenied as exc:
            return None, f"zero_cost_denied:{exc.decision.value}"
        answer, error = await original(self, model, messages, api_key)
        # The egress PEP is installed below this PEP and can still deny before
        # transport. Do not manufacture an actual_sent event in that case.
        if error != "egress_denied":
            record_outbound_sent(request, proof)
        return answer, error

    provider_cls._scp_zero_cost_original_call_model_once = original
    provider_cls._call_model_once = guarded
    provider_cls._scp_zero_cost_pep_installed = True
    return True


def install_free_only_provider_router(provider_cls: type) -> bool:
    """Install Z3 verified-free-only candidate routing on provider.chat().

    The legacy class may still carry historical paid defaults in attributes for
    compatibility/diagnostics. They are merely candidates: this router calls
    authorize_outbound BEFORE `_call_model`, skips every non-free candidate,
    and therefore never burns retry/breaker budget on a cost-policy denial.
    """
    if getattr(provider_cls, "_scp_free_only_router_installed", False):
        return False
    original_chat = getattr(provider_cls, "chat", None)
    if original_chat is None:
        raise AttributeError("provider class has no chat boundary")

    async def free_only_chat(
        self: Any,
        question: str,
        context: str = "",
        system_prompt: str = "",
        prioritize_free: bool = False,
    ):
        del prioritize_free  # free-only mode makes the old preference obsolete.
        if not getattr(self, "enabled", False):
            return None, "none"

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": f"{context}\n\n{question}".strip()})

        candidates: list[str] = []
        # Task-curated free candidate first, then any configured primary, then
        # OpenRouter's free auto-router. Every one still needs a fresh proof.
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
        for model in candidates:
            try:
                authorize_outbound(
                    provider=getattr(self, "PROVIDER_NAME", "unknown"),
                    model=model,
                    task_class=getattr(self, "task", "default"),
                    data_class=getattr(self, "_scp_data_class", DataClass.INTERNAL),
                )
                eligible.append(model)
            except ZeroCostDenied as exc:
                if exc.decision in {
                    ZeroCostDecision.DENY_UNKNOWN_PRICE,
                    ZeroCostDecision.DENY_STALE_PRICE,
                }:
                    blocked_for_proof = True
                continue

        if not eligible:
            return None, "blocked_zero_cost_proof" if blocked_for_proof else "blocked_no_qualified_free_model"

        quota_seen = False
        for model in eligible:
            key_count = max(1, int(self._key_count()))
            for _ in range(min(3, key_count)):
                key = self._next_key()
                answer, error = await self._call_model(model, messages, key)
                if answer:
                    return answer, f"{getattr(self, 'PROVIDER_NAME', 'provider')}:{model}"
                error_text = str(error or "").lower()
                if any(sig in error_text for sig in ("429", "402", "quota", "rate-limit")):
                    quota_seen = True
                    continue
                # Non-quota transport failure: try next exact-$0 candidate.
                break

        return None, "waiting_free_quota" if quota_seen else "none"

    provider_cls._scp_legacy_chat = original_chat
    provider_cls.chat = free_only_chat
    provider_cls._scp_free_only_router_installed = True
    return True
