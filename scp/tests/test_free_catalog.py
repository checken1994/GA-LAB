import sys

sys.path.insert(0, ".")

import pytest

from scp.llm_gateway import client as cl
from scp.llm_gateway import free_catalog as fc

original_allowlist = list(cl.OPENROUTER_FREE_MODELS)


def _reset() -> None:
    fc._fetched = False
    fc._last_ok = None
    cl.OPENROUTER_FREE_MODELS = list(original_allowlist)
    if hasattr(fc, "OPENROUTER_FREE_MODELS"):
        del fc.OPENROUTER_FREE_MODELS


def test_text_capable_rejects_audio_video() -> None:
    assert fc._text_capable({"output_modalities": ["audio"]}) is False
    assert fc._text_capable({"output_modalities": ["video"]}) is False


def test_text_capable_accepts_text_and_absent() -> None:
    assert fc._text_capable({"output_modalities": ["text"]}) is True
    assert fc._text_capable({}) is True


def test_text_capable_supports_nested_architecture_schema() -> None:
    assert fc._text_capable({"architecture": {"output_modalities": ["text"]}}) is True
    assert fc._text_capable({"architecture": {"output_modalities": ["audio"]}}) is False


def test_refresh_replaces_allowlist_and_filters_audio(monkeypatch) -> None:
    _reset()
    cat = [{"id": "m/a:free", "context_length": 9000, "output_modalities": ["audio"]}]
    cat.append({"id": "m/x:free", "context_length": 8000, "output_modalities": ["text"]})
    monkeypatch.setattr(fc, "_fetch_free_models", lambda timeout=None: cat)
    assert fc.refresh_free_catalog() is True
    assert cl.OPENROUTER_FREE_MODELS == ["m/x:free"]


def test_refresh_replaces_client_allowlist_not_fc_module(monkeypatch) -> None:
    _reset()
    cat = [{"id": "m/y:free", "context_length": 7000, "output_modalities": ["text"]}]
    monkeypatch.setattr(fc, "_fetch_free_models", lambda timeout=None: cat)
    assert fc.refresh_free_catalog() is True
    assert cl.OPENROUTER_FREE_MODELS == ["m/y:free"]
    assert not hasattr(fc, "OPENROUTER_FREE_MODELS")


def test_refresh_network_fail_keeps_hardcoded(monkeypatch) -> None:
    _reset()
    before = list(cl.OPENROUTER_FREE_MODELS)
    monkeypatch.setattr(fc, "_fetch_free_models", lambda timeout=None: None)
    assert fc.refresh_free_catalog() is False
    assert cl.OPENROUTER_FREE_MODELS == before


def test_refresh_empty_catalog_keeps_hardcoded(monkeypatch) -> None:
    _reset()
    before = list(cl.OPENROUTER_FREE_MODELS)
    monkeypatch.setattr(fc, "_fetch_free_models", lambda timeout=None: [])
    assert fc.refresh_free_catalog() is False

def test_refresh_force_bypasses_fetched_flag(monkeypatch) -> None:
    _reset()
    cat = [{"id": "m/z:free", "context_length": 6000, "output_modalities": ["text"]}]
    monkeypatch.setattr(fc, "_fetch_free_models", lambda timeout=None: cat)
    assert fc.refresh_free_catalog(force=True) is True
    assert cl.OPENROUTER_FREE_MODELS == ["m/z:free"]


def test_start_background_refresh_is_idempotent() -> None:
    _reset()
    fc._refresh_thread_started = True
    fc.start_background_refresh()
    fc.start_background_refresh()
    assert fc._refresh_thread_started is True
