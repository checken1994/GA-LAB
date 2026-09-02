from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scp.contracts.data_class import DataClass
from scp.epistemic.evidence_store import EvidenceStore
from scp.epistemic.evidence_writer import GovernedEvidenceWriter
from scp.governance.privacy import PrivacyWriteGate
from scp.llm_gateway.zero_cost_guard import (
    PricingProofStore,
    ZeroCostDecision,
    ZeroCostDenied,
    ZeroCostGuard,
    ZeroCostRequest,
)


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


def _record(proofs, ev, *, model="free/model", prompt="0", completion="0", observed=None, expires=None):
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
    _record(proofs, ev, model="stale/model", observed=old, expires=old + timedelta(hours=1))
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
    assert guard.evaluate(req)[0] is ZeroCostDecision.DENY_PAID
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
    assert guard.evaluate(
        ZeroCostRequest("openrouter", "durable/free", "chat", DataClass.PUBLIC)
    )[0] is ZeroCostDecision.ALLOW_FREE
    reopened.close()
    evidence.db.close()
