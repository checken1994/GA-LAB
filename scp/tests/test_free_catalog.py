import sys

sys.path.insert(0, ".")

import pytest

from scp.llm_gateway import free_catalog as fc


def _reset() -> None:
    """Put the module back into the pre-fetch state (for repeated scenarios)."""
    fc._fetched = False
    fc._last_ok = None


def test_text_capable_rejects_audio_video() -> None:
    assert fc._text_capable({"output_modalities": ["audio"]}) is False
    assert fc._text_capable({"output_modalities": ["video"]}) is False

def test_text_capable_accepts_text_and_absent() -> None:
    assert fc._text_capable({"output_modalities": ["text"]}) is True

def test_refresh_replaces_allowlist_and_filters_audio(monkeypatch) -> None:
    _reset()
    catalog = [{"id": "m/a:free", "context_length": 9000, "output_modalities": ["audio"]},
                    {"id": "m/x:free", "context_length": 8000, "output_modalities": ["text"]}]
    monkeypatch.setattr(fc, "_fetch_free_models", lambda timeout=None: catalog)
    assert fc.refresh_free_catalog() is True
    assert fc.OPENROUTER_FREE_MODELS == ["m/x:free"]  # audio removed; text kept

def test_refresh_network_fail_keeps_hardcoded(monkeypatch) -> None:
    _reset()
    before = list(fc.OPENROUTER_FREE_MODELS)
    monkeypatch.setattr(fc, "_fetch_free_models", lambda timeout=None: None)
    assert fc.refresh_free_catalog() is False
    assert fc.OPENROUTER_FREE_MODELS == before#  kept unchanged

def test_refresh_empty_catalog_keeps_hardcoded(monkeypatch) -> None:
    _reset()
    before = list(fc.OPENROUTER_FREE_MODELS)
    monkeypatch.setattr(fc, "_fetch_free_models", lambda timeout=None: [])
    assert fc.refresh_free_catalog() is False
    assert fc.OPENROUTER_FREE_MODELS == before