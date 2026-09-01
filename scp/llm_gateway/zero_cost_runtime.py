"""Runtime adapter that places ZeroCostGuard immediately before LLM drivers.

The adapter exists separately from routing so a buggy router choosing a paid or
unknown-price model is still blocked at the provider method that performs the
network request.
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


def authorize_outbound(
    *,
    provider: str,
    model: str,
    task_class: str,
    data_class: DataClass | str | None = DataClass.INTERNAL,
):
    request = ZeroCostRequest(
        provider=str(provider).strip().lower(),
        model=str(model).strip(),
        task_class=str(task_class).strip() or "default",
        data_class=data_class,
    )
    proof = get_runtime_guard().authorize(request)
    return request, proof


def record_outbound_sent(request: ZeroCostRequest, proof: PricingProof | None) -> str:
    return get_runtime_guard().record_sent(request, proof)


def install_openai_compatible_provider_pep(provider_cls: type) -> bool:
    """Wrap provider_cls._call_model_once once, preserving its public API.

    This is a migration shim for the large legacy gateway: the cost PEP is
    installed at runtime without changing routing semantics first. Z3 can then
    simplify the router after the boundary is already fail-closed.
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
            # ZERO network call: return a non-transient provider error so the
            # existing fallback chain may try another candidate, which will be
            # independently checked at the same PEP.
            return None, f"zero_cost_denied:{exc.decision.value}"
        answer, error = await original(self, model, messages, api_key)
        record_outbound_sent(request, proof)
        return answer, error

    provider_cls._scp_zero_cost_original_call_model_once = original
    provider_cls._call_model_once = guarded
    provider_cls._scp_zero_cost_pep_installed = True
    return True
