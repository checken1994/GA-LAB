"""Property/regression tests for the production None-safety paths.

Unlike the previous version, these tests DO NOT reimplement the guards under
 test.  They inject source results into the real SLM classes and assert the
production call path remains safe and semantically correct.
"""
from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

import scp.core.crypto_verifier as crypto_verifier
import scp.core.smart_cache as smart_cache
import scp.runtime.slm_impls.chem_reality_astro_slm as chemistry_mod
from scp.core.crypto_verifier import CryptoResult
from scp.runtime.slm_impls.chem_reality_astro_slm import ChemistrySLM
from scp.runtime.slm_impls.numeric_data_slm import FinanceSLM
from scp.runtime.slms_parts.conversionslm import ConversionSLM


class _NoCache:
    def get(self, *_args, **_kwargs):
        return None

    def set(self, *_args, **_kwargs):
        return None


@pytest.fixture(autouse=True)
def _isolate_runtime_cache(monkeypatch):
    monkeypatch.setattr(smart_cache, "get_smart_cache", lambda: _NoCache())


def _currency_result(value):
    return {
        "value": value,
        "source": "test-source",
        "confidence": 0.9 if value is not None else 0.0,
        "sources_succeeded": ["test-source"] if value is not None else [],
        "all_values": [] if value is None else [{"value": value, "source": "test-source"}],
        "conflict_detected": False,
        "reason": "test fixture",
    }


def _crypto_result(value):
    return CryptoResult(
        value=value,
        source="test-source" if value is not None else "none",
        confidence=0.9 if value is not None else 0.0,
        sources_queried=["test-source"],
        sources_succeeded=["test-source"] if value is not None else [],
        sources_failed=[] if value is not None else ["test-source"],
        all_values=[] if value is None else [{"value": value, "source": "test-source"}],
        strategy="test",
        conflict_detected=False,
        reason="test fixture",
    )


@given(value=st.one_of(st.none(), st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False)))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_conversion_currency_none_guard_is_on_production_path(monkeypatch, value):
    monkeypatch.setattr(crypto_verifier, "fetch_currency_rate", lambda *_args: _currency_result(value))
    response = ConversionSLM().predict("convert 10 USD to EUR")

    if value is not None and value > 0:
        assert response.answer == f"10.0 USD = {10.0 * value} EUR"
        assert response.evidence["rate"] == value
    else:
        assert response.answer == ""
        assert response.confidence == 0.1
        assert response.evidence == {"source": "none"}


@given(value=st.one_of(st.none(), st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False)))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_conversion_crypto_none_guard_is_on_production_path(monkeypatch, value):
    monkeypatch.setattr(crypto_verifier, "fetch_crypto_price", lambda *_args: _crypto_result(value))
    response = ConversionSLM().predict("price of bitcoin")

    if value is not None and value > 0:
        assert response.answer == f"giá bitcoin = {value} USD"
        assert response.evidence["value"] == value
    else:
        assert response.answer == ""
        assert response.confidence == 0.1
        assert response.evidence == {"source": "none"}


@given(value=st.one_of(st.none(), st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False)))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_finance_slm_uses_same_production_none_guard(monkeypatch, value):
    monkeypatch.setattr(crypto_verifier, "fetch_currency_rate", lambda *_args: _currency_result(value))
    response = FinanceSLM().predict("chuyển đổi 10 USD sang EUR")

    if value is not None and value > 0:
        assert response.answer == f"10.0 USD = {10.0 * value} EUR"
        assert response.evidence["rate"] == value
    else:
        assert response.answer == ""
        assert response.confidence == 0.1


def test_chemistry_multi_source_none_is_not_swallowed_as_success(monkeypatch):
    monkeypatch.setattr(chemistry_mod, "db_query_one", lambda *_args, **_kwargs: None)

    import scp.data_sources.chemistry as chemistry_source
    import scp.core.multi_source_verifier as multi_source

    monkeypatch.setattr(chemistry_source.ChemistryDataSource, "fetch", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        multi_source,
        "fetch_chemistry_multi",
        lambda *_args, **_kwargs: {
            "value": None,
            "source": "none",
            "confidence": 0.0,
            "sources_succeeded": [],
            "all_values": [],
            "conflict_detected": False,
            "reason": "all sources failed",
        },
    )

    response = ChemistrySLM().predict("molar mass of definitely-not-a-real-compound-xyz?")
    assert response.answer == ""
    assert response.confidence == 0.3
    assert response.evidence["source"] == "none"


def test_crypto_unknown_coin_returns_explicit_none():
    result = crypto_verifier.fetch_crypto_price("definitely-not-a-real-coin-xyz")
    assert result.value is None
    assert result.strategy == "unknown_coin"


def test_old_buggy_expression_still_demonstrates_root_cause():
    with pytest.raises(TypeError):
        _ = None > 0


def test_nan_is_never_a_positive_source_value(monkeypatch):
    value = math.nan
    monkeypatch.setattr(crypto_verifier, "fetch_currency_rate", lambda *_args: _currency_result(value))
    response = ConversionSLM().predict("convert 10 USD to EUR")
    assert response.answer == ""
    assert response.confidence == 0.1
