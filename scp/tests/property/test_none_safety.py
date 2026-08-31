"""Property/regression tests for verifier None-safety contracts.

These tests exercise production verifier code directly. They intentionally avoid
legacy runtime naming and do not reimplement the boolean guards under test.
"""
from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

import scp.core.crypto_verifier as crypto_verifier


def _install_crypto_sources(monkeypatch, value):
    def _fetch(_symbol):
        return value

    monkeypatch.setattr(
        crypto_verifier,
        "SOURCE_FETCHERS",
        [("A", _fetch), ("B", _fetch), ("C", _fetch)],
    )
    monkeypatch.setitem(
        crypto_verifier.SYMBOL_MAP,
        "property-test-coin",
        {"a": "X", "b": "X", "c": "X"},
    )


@given(value=st.one_of(st.none(), st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False)))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_crypto_verifier_never_promotes_missing_or_nonpositive_values(monkeypatch, value):
    _install_crypto_sources(monkeypatch, value)
    result = crypto_verifier.fetch_crypto_price("property-test-coin")

    if value is None or value <= 0:
        assert result.value is None
        assert result.confidence == 0.0
        assert result.sources_succeeded == []
        assert result.strategy == "all_failed"
    else:
        assert result.value == pytest.approx(value)
        assert len(result.sources_succeeded) == 3
        assert result.confidence >= 0.85


def test_unknown_crypto_entity_is_explicit_unknown_not_zero():
    result = crypto_verifier.fetch_crypto_price("definitely-not-a-real-coin-xyz")
    assert result.value is None
    assert result.confidence == 0.0
    assert result.strategy == "unknown_coin"
    assert result.sources_succeeded == []


def test_old_buggy_expression_still_demonstrates_root_cause():
    with pytest.raises(TypeError):
        _ = None > 0
