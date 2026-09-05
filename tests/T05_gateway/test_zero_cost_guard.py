from __future__ import annotations

import asyncio
import itertools
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scp.contracts.data_class import DataClass
from scp.epistemic.evidence_store import EvidenceStore
from scp.epistemic.evidence_writer import GovernedEvidenceWriter
from scp.governance.privacy import PrivacyWriteGate
from scp.llm_gateway import free_catalog
from scp.llm_gateway.client import OpenRouterProvider
from scp.llm_gateway.zero_cost_guard import (
    PricingProofStore,
    ZeroCostDecision,
    ZeroCostDenied,
    ZeroCostGuard,
    ZeroCostRequest,
)
from scp.llm_gateway.zero_cost_runtime import _runtime_store_path

ROOT = Path(__file__).resolve().parents[2]


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _setup(tmp_path):
    evidence = EvidenceStore(tmp_path / "epistemic.sqlite", tmp_path / "objects")
    privacy = PrivacyWriteGate(ROOT / "spec" / "data_policies.yaml")
    writer = GovernedEvidenceWriter(evidence, privacy)
    proof_evidence = writer.observe(
        kind="HTTP_RESPONSE",
        content=b'{"catalog":"fixture"}',
        collector_id="pricing-test",
        collector_version="1",
        data_class=DataClass.PUBLIC,
    )
    proofs = PricingProofStore(tmp_path / "zero_cost.sqlite")
    return evidence, privacy, proof_evidence, proofs


def _record(
    proofs,
    ev,
    *,
    model="free/model",
    prompt="0",
    completion="0",
    observed=None,
    expires=None,
):
    now = datetime.now(timezone.utc)
    return proofs.record(
        provider="openrouter",
        model=model,
        prompt_price=prompt,
        completion_price=completion,
        catalog_hash="sha256:catalog",
        evidence_id=ev["evidence_id"],
        observed_at=_iso(observed or now),
        expires_at=_iso(expires or (now + timedelta(hours=6))),
    )


def test_paid_unknown_stale_and_data_class_never_reach_send_boundary(tmp_path):
    evidence, privacy, ev, proofs = _setup(tmp_path)
    guard = ZeroCostGuard(proofs, privacy_gate=privacy)
    sent = 0

    def attempt(model, data_class):
        nonlocal sent
        request = ZeroCostRequest("openrouter", model, "chat", data_class)
        proof = guard.authorize(request)
        sent += 1  # represents the network call after the PEP
        guard.record_sent(request, proof)

    with pytest.raises(ZeroCostDenied) as exc:
        attempt("unknown/model", DataClass.PUBLIC)
    assert exc.value.decision is ZeroCostDecision.DENY_UNKNOWN_PRICE
    assert sent == 0

    _record(proofs, ev, model="paid/model", prompt="0.01", completion="0")
    with pytest.raises(ZeroCostDenied) as exc:
        attempt("paid/model", DataClass.PUBLIC)
    assert exc.value.decision is ZeroCostDecision.DENY_PAID
    assert sent == 0

    old = datetime.now(timezone.utc) - timedelta(hours=8)
    _record(
        proofs, ev, model="stale/model", observed=old, expires=old + timedelta(hours=1)
    )
    with pytest.raises(ZeroCostDenied) as exc:
        attempt("stale/model", DataClass.PUBLIC)
    assert exc.value.decision is ZeroCostDecision.DENY_STALE_PRICE
    assert sent == 0

    _record(proofs, ev, model="free/model")
    with pytest.raises(ZeroCostDenied) as exc:
        attempt("free/model", DataClass.SECRET)
    assert exc.value.decision is ZeroCostDecision.DENY_DATA_CLASS
    assert sent == 0

    attempt("free/model", DataClass.PUBLIC)
    assert sent == 1
    proofs.close()
    evidence.db.close()


def test_free_to_paid_catalog_transition_denies_next_request(tmp_path):
    evidence, privacy, ev, proofs = _setup(tmp_path)
    guard = ZeroCostGuard(proofs, privacy_gate=privacy)
    req = ZeroCostRequest("openrouter", "changing/model", "chat", DataClass.PUBLIC)
    _record(proofs, ev, model="changing/model", prompt="0", completion="0")
    assert guard.evaluate(req)[0] is ZeroCostDecision.ALLOW_FREE
    # A later immutable proof says the model now costs money. Latest proof wins.
    later = datetime.now(timezone.utc) + timedelta(seconds=1)
    _record(
        proofs,
        ev,
        model="changing/model",
        prompt="0.001",
        completion="0",
        observed=later,
        expires=later + timedelta(hours=6),
    )
    assert guard.evaluate(req, now=later)[0] is ZeroCostDecision.DENY_PAID
    proofs.close()
    evidence.db.close()


def test_free_only_config_cannot_enable_paid_or_unknown_price():
    valid = {
        "SCP_LLM_COST_MODE": "free_only",
        "SCP_ALLOW_PAID_FALLBACK": "0",
        "SCP_MAX_LLM_COST_USD": "0",
        "SCP_FREE_REQUIRE_PRICE_PROOF": "1",
        "SCP_FREE_FAIL_IF_PRICE_UNKNOWN": "1",
    }
    ZeroCostGuard.validate_free_only_config(valid)
    for key, value in (
        ("SCP_ALLOW_PAID_FALLBACK", "1"),
        ("SCP_MAX_LLM_COST_USD", "0.01"),
        ("SCP_FREE_REQUIRE_PRICE_PROOF", "0"),
        ("SCP_FREE_FAIL_IF_PRICE_UNKNOWN", "0"),
    ):
        bad = dict(valid)
        bad[key] = value
        with pytest.raises(ValueError):
            ZeroCostGuard.validate_free_only_config(bad)


def test_pricing_proof_survives_restart(tmp_path):
    evidence, privacy, ev, proofs = _setup(tmp_path)
    _record(proofs, ev, model="durable/free")
    proofs.close()
    reopened = PricingProofStore(tmp_path / "zero_cost.sqlite")
    guard = ZeroCostGuard(reopened, privacy_gate=privacy)
    assert (
        guard.evaluate(
            ZeroCostRequest("openrouter", "durable/free", "chat", DataClass.PUBLIC)
        )[0]
        is ZeroCostDecision.ALLOW_FREE
    )
    reopened.close()
    evidence.db.close()


def test_runtime_proof_store_override_is_test_scoped_and_data_scoped(
    tmp_path, monkeypatch
):
    data_root = tmp_path / "acceptance-evidence"
    proof_db = data_root / "foundation" / "zero_cost.sqlite"
    monkeypatch.setenv("SCP_MODE", "test")
    monkeypatch.setenv("SCP_DATA_DIR", str(data_root))
    monkeypatch.setenv("SCP_ZERO_COST_PROOF_DB", str(proof_db))

    assert _runtime_store_path() == proof_db.resolve()

    monkeypatch.setenv("SCP_MODE", "production")
    with pytest.raises(RuntimeError, match="restricted to SCP_MODE=test"):
        _runtime_store_path()

    monkeypatch.setenv("SCP_MODE", "test")
    monkeypatch.setenv("SCP_ZERO_COST_PROOF_DB", str(tmp_path / "outside.sqlite"))
    with pytest.raises(RuntimeError, match="inside SCP_DATA_DIR"):
        _runtime_store_path()


class _Response:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": "bounded answer"}}]}


class _RecordingTransport:
    def __init__(self):
        self.calls = 0
        self.models = []

    async def post(self, *_args, **kwargs):
        self.calls += 1
        self.models.append(kwargs["json"]["model"])
        return _Response()


def _runtime_fixture(tmp_path, monkeypatch):
    data_root = tmp_path / "runtime"
    proof_db = data_root / "zero-cost.sqlite"
    monkeypatch.setenv("SCP_MODE", "test")
    monkeypatch.setenv("SCP_DATA_DIR", str(data_root))
    monkeypatch.setenv("SCP_ZERO_COST_PROOF_DB", str(proof_db))
    monkeypatch.setenv("SCP_LLM_COST_MODE", "free_only")
    monkeypatch.setenv("SCP_ALLOW_PAID_FALLBACK", "0")
    monkeypatch.setenv("SCP_MAX_LLM_COST_USD", "0")
    monkeypatch.setenv("SCP_FREE_REQUIRE_PRICE_PROOF", "1")
    monkeypatch.setenv("SCP_FREE_FAIL_IF_PRICE_UNKNOWN", "1")
    monkeypatch.setenv("SCP_EGRESS_MODE", "allowlist")
    monkeypatch.setenv("SCP_LLM_EGRESS_ALLOWLIST", "openrouter.ai")
    # The autouse fixture owns singleton reset/cleanup; never close a foreign store.
    return PricingProofStore(proof_db)


def _provider(monkeypatch):
    monkeypatch.setattr(OpenRouterProvider, "_API_KEYS", ["test-key"])
    monkeypatch.setattr(OpenRouterProvider, "_key_cycle", itertools.cycle(["test-key"]))
    monkeypatch.setattr(OpenRouterProvider, "_dynamic_models_loaded", True)
    provider = OpenRouterProvider(task="chat")
    provider._scp_data_class = DataClass.PUBLIC
    provider._client = _RecordingTransport()
    return provider


def _runtime_record(
    store, *, model, prompt="0", completion="0", observed=None, expires=None
):
    now = datetime.now(timezone.utc)
    store.record(
        provider="openrouter",
        model=model,
        prompt_price=prompt,
        completion_price=completion,
        catalog_hash="sha256:runtime-fixture",
        evidence_id="evidence://pricing/runtime-fixture",
        observed_at=_iso(observed or now),
        expires_at=_iso(expires or (now + timedelta(minutes=5))),
    )


@pytest.mark.parametrize(
    ("model", "prompt", "completion", "stale", "decision"),
    [
        ("unknown/model", None, None, False, ZeroCostDecision.DENY_UNKNOWN_PRICE),
        ("partial/model", "0", None, False, ZeroCostDecision.DENY_UNKNOWN_PRICE),
        ("prompt-paid/model", "0.01", "0", False, ZeroCostDecision.DENY_PAID),
        ("completion-paid/model", "0", "0.01", False, ZeroCostDecision.DENY_PAID),
        ("stale/model", "0", "0", True, ZeroCostDecision.DENY_STALE_PRICE),
    ],
)
def test_runtime_pep_denies_before_real_transport_boundary(
    tmp_path, monkeypatch, model, prompt, completion, stale, decision
):
    """Z2 PEP denial occurs before the wrapped HTTP client's post()."""
    store = _runtime_fixture(tmp_path, monkeypatch)
    if model != "unknown/model":
        now = datetime.now(timezone.utc)
        _runtime_record(
            store,
            model=model,
            prompt=prompt,
            completion=completion,
            observed=now - timedelta(minutes=10) if stale else now,
            expires=now - timedelta(minutes=1) if stale else now + timedelta(minutes=5),
        )
    store.close()
    provider = _provider(monkeypatch)

    answer, error = asyncio.run(provider._call_model_once(model, [], "test-key"))

    assert answer is None
    assert error == f"zero_cost_denied:{decision.value}"
    assert provider._client.calls == 0


def test_fresh_exact_zero_reaches_transport_once(tmp_path, monkeypatch):
    store = _runtime_fixture(tmp_path, monkeypatch)
    _runtime_record(store, model="free/model")
    store.close()
    provider = _provider(monkeypatch)

    answer, error = asyncio.run(provider._call_model_once("free/model", [], "test-key"))

    assert (answer, error) == ("bounded answer", None)
    assert provider._client.calls == 1


def test_router_skips_paid_fallback_and_uses_only_verified_free(tmp_path, monkeypatch):
    store = _runtime_fixture(tmp_path, monkeypatch)
    _runtime_record(store, model="verified/free")
    _runtime_record(store, model="paid/fallback", prompt="0", completion="1")
    store.close()
    provider = _provider(monkeypatch)
    provider.free_fallback = "paid/fallback"
    provider.model = "verified/free"

    answer, label = asyncio.run(provider.chat("question"))

    assert answer == "bounded answer"
    assert label == "openrouter:verified/free"
    assert provider._client.calls == 1
    assert provider._client.models == ["verified/free"]


def test_partial_catalog_observation_supersedes_old_free_as_unknown(
    tmp_path, monkeypatch
):
    """A newer partial record must not leave a stale exact-zero proof active."""
    monkeypatch.setattr(free_catalog, "_FOUNDATION", tmp_path)
    assert free_catalog._persist_pricing_proofs(
        [{"id": "changing/model", "pricing": {"prompt": "0", "completion": "0"}}]
    )
    assert free_catalog._persist_pricing_proofs(
        [{"id": "changing/model", "pricing": {"prompt": "0"}}]
    )

    store = PricingProofStore(tmp_path / "zero_cost.sqlite")
    decision, proof = ZeroCostGuard(store).evaluate(
        ZeroCostRequest("openrouter", "changing/model", "chat", DataClass.PUBLIC)
    )
    assert decision is ZeroCostDecision.DENY_UNKNOWN_PRICE
    assert proof is not None and proof.completion_price is None
    store.close()


def test_cold_start_unknown_proof_never_refreshes_or_posts(monkeypatch):
    calls = []

    def forbidden_refresh(*args, **kwargs):
        calls.append("catalog")
        raise AssertionError("dispatch attempted discovery")

    monkeypatch.setattr(free_catalog, "refresh_free_catalog", forbidden_refresh)
    monkeypatch.setattr(OpenRouterProvider, "_dynamic_models_loaded", False)
    provider = OpenRouterProvider(task="chat")
    provider._client = _RecordingTransport()
    assert provider.enabled
    assert provider._key_count() == 1
    assert provider._next_key() == "test-key"
    assert provider.stats()["configured"]
    assert asyncio.run(provider.chat("question")) == (None, "blocked_zero_cost_proof")
    assert provider._client.calls == 0
    assert calls == []


@pytest.mark.parametrize(
    "pricing",
    [
        ["bad"],
        "bad",
        {"prompt": "0", "completion": "NaN"},
        {"prompt": "0", "completion": "sNaN"},
    ],
)
def test_malformed_catalog_supersedes_free(tmp_path, monkeypatch, pricing):
    monkeypatch.setattr(free_catalog, "_FOUNDATION", tmp_path)
    assert free_catalog._persist_pricing_proofs(
        [{"id": "changing", "pricing": {"prompt": "0", "completion": "0"}}]
    )
    assert free_catalog._persist_pricing_proofs(
        [{"id": "changing", "pricing": pricing}]
    )
    store = PricingProofStore(tmp_path / "zero_cost.sqlite")
    try:
        assert (
            ZeroCostGuard(store).evaluate(
                ZeroCostRequest("openrouter", "changing", "chat", DataClass.PUBLIC)
            )[0]
            is ZeroCostDecision.DENY_UNKNOWN_PRICE
        )
    finally:
        store.close()


def test_equal_timestamp_latest_partial_observation_wins(tmp_path):
    store = PricingProofStore(tmp_path / "prices.sqlite")
    now = datetime.now(timezone.utc)
    try:
        for completion in ("0", None):
            _runtime_record(
                store, model="same-time", completion=completion, observed=now
            )
        assert (
            ZeroCostGuard(store).evaluate(
                ZeroCostRequest("openrouter", "same-time", "chat", DataClass.PUBLIC)
            )[0]
            is ZeroCostDecision.DENY_UNKNOWN_PRICE
        )
    finally:
        store.close()


def test_paid_candidate_is_not_contacted_after_free_primary_timeout(
    pricing_runtime, monkeypatch
):
    pricing_runtime("primary")
    pricing_runtime("paid-fallback", completion="0.02")
    pricing_runtime("openrouter/free")
    provider = _provider(monkeypatch)
    provider.free_fallback = "primary"
    provider.model = "paid-fallback"
    seen = []

    class TimeoutResponse(_Response):
        status_code = 429

    class Transport:
        async def post(self, *_args, **kwargs):
            model = kwargs["json"]["model"]
            seen.append(model)
            return TimeoutResponse() if model == "primary" else _Response()

    provider._client = Transport()
    assert asyncio.run(provider.chat("q")) == (
        "bounded answer",
        "openrouter:openrouter/free",
    )
    assert seen == ["primary", "openrouter/free"]


def test_policy_denial_does_not_consume_retry_or_trip_breaker(monkeypatch):
    provider = _provider(monkeypatch)

    async def no_retry_sleep(*_args):
        pytest.fail("Policy denial was treated as a transient transport error")

    monkeypatch.setattr(asyncio, "sleep", no_retry_sleep)
    result = asyncio.run(provider._call_model("unproven", [], "test-key"))
    assert result == (None, "zero_cost_denied:DENY_UNKNOWN_PRICE")
    assert provider._client.calls == 0
    assert provider._breaker._consecutive_failures == 0


def test_egress_denial_does_not_record_sent(pricing_runtime, monkeypatch):
    pricing_runtime("free/model")
    provider = _provider(monkeypatch)
    monkeypatch.setenv("SCP_EGRESS_MODE", "deny")
    assert asyncio.run(provider._call_model_once("free/model", [], "test-key")) == (
        None,
        "egress_denied",
    )
    from scp.llm_gateway.zero_cost_runtime import get_runtime_guard

    rows = get_runtime_guard().proof_store.db.query(
        "SELECT * FROM zero_cost_outbound_events WHERE actual_sent=1"
    )
    assert rows == []
    assert provider._client.calls == 0


def test_proof_expiring_after_routing_is_denied_at_dispatch(
    pricing_runtime, monkeypatch
):
    from scp.llm_gateway import zero_cost_guard

    pricing_runtime("ephemeral")
    provider = _provider(monkeypatch)
    provider.free_fallback = "ephemeral"
    provider.model = "ephemeral"
    future = datetime.now(timezone.utc) + timedelta(hours=1)

    class DispatchClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return future.astimezone(tz)

    def expire_before_key_use():
        monkeypatch.setattr(zero_cost_guard, "datetime", DispatchClock)
        return "test-key"

    monkeypatch.setattr(provider, "_next_key", expire_before_key_use)
    assert asyncio.run(provider.chat("q")) == (None, "none")
    assert provider._client.calls == 0
    assert provider._breaker._consecutive_failures == 0
