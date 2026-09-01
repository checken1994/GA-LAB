"""Runtime adapter that places ZeroCostGuard immediately before LLM drivers.

The adapter exists separately from routing so a buggy router choosing a paid or
unknown-price model is still blocked at the provider method that performs the
network request. Missing/stale OpenRouter proof triggers exactly one catalog
refresh attempt before the final fail-closed verdict; PAID/DATA_CLASS denials
are never retried.
"""
from __future__ import annotations

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


def get_runtime_guard() -> ZeroCostGuard:
    global _store, _guard
    if _guard is None:
        with _lock:
            if _guard is None:
                ZeroCostGuard.validate_free_only_config()
                _store = PricingProofStore(_ROOT / "data" / "foundation" / "zero_cost.sqlite")
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

    For OpenRouter only, UNKNOWN/STALE proof gets one bounded catalog refresh
    because the catalog is the pricing authority. A refresh failure or a proof
    that remains unknown/stale still DENIES. No retry is made for PAID or
    DATA_CLASS decisions.
    """
    request = _request(
        provider=provider,
        model=model,
        task_class=task_class,
        data_class=data_class,
    )
    guard = get_runtime_guard()
    try:
        proof = guard.authorize(request)
        return request, proof
    except ZeroCostDenied as first:
        if request.provider != "openrouter" or first.decision not in {
            ZeroCostDecision.DENY_UNKNOWN_PRICE,
            ZeroCostDecision.DENY_STALE_PRICE,
        }:
            raise
        try:
            from scp.llm_gateway.free_catalog import refresh_free_catalog

            refresh_free_catalog(force=True)
        except Exception:
            # The second authorize below is the authoritative fail-closed result.
            pass
        proof = guard.authorize(request)
        return request, proof


def record_outbound_sent(request: ZeroCostRequest, proof: PricingProof | None) -> str:
    return get_runtime_guard().record_sent(request, proof)


def install_openai_compatible_provider_pep(provider_cls: type) -> bool:
    """Wrap provider_cls._call_model_once once, preserving its public API.

    This is a migration shim for the large legacy gateway: the cost PEP is
    installed at runtime without trusting routing semantics. Z3 may simplify
    the router later, while this boundary remains fail-closed.
    """
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
            # ZERO network call: cost-policy denial is not a transient provider
            # fault and must not be translated into a paid retry.
            return None, f"zero_cost_denied:{exc.decision.value}"
        answer, error = await original(self, model, messages, api_key)
        record_outbound_sent(request, proof)
        return answer, error

    provider_cls._scp_zero_cost_original_call_model_once = original
    provider_cls._call_model_once = guarded
    provider_cls._scp_zero_cost_pep_installed = True
    return True
