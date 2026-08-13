from __future__ import annotations

from pathlib import Path

import pytest

from scp.security.provider_keys import (
    ProviderCredentialError,
    load_openrouter_keys,
    provider_key_status,
)


def test_direct_keys_are_loaded_in_slot_order():
    env = {
        "OPENROUTER_API_KEY": "fixture-key-1",
        "OPENROUTER_API_KEY_2": "fixture-key-2",
    }
    assert load_openrouter_keys(env) == ["fixture-key-1", "fixture-key-2"]


def test_file_backed_keys_are_loaded_and_bom_is_normalized(tmp_path: Path):
    key_file = tmp_path / "provider-key.txt"
    key_file.write_text("\ufefffixture-file-key\n", encoding="utf-8")
    env = {"OPENROUTER_API_KEY_FILE": str(key_file)}
    assert load_openrouter_keys(env) == ["fixture-file-key"]


def test_direct_and_file_conflict_fails_closed(tmp_path: Path):
    key_file = tmp_path / "provider-key.txt"
    key_file.write_text("fixture-file-key\n", encoding="utf-8")
    env = {
        "OPENROUTER_API_KEY": "fixture-direct-key",
        "OPENROUTER_API_KEY_FILE": str(key_file),
    }
    with pytest.raises(ProviderCredentialError):
        load_openrouter_keys(env)


def test_missing_or_empty_file_fails_closed(tmp_path: Path):
    with pytest.raises(ProviderCredentialError):
        load_openrouter_keys({"OPENROUTER_API_KEY_FILE": str(tmp_path / "missing")})
    empty = tmp_path / "empty"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(ProviderCredentialError):
        load_openrouter_keys({"OPENROUTER_API_KEY_FILE": str(empty)})


def test_placeholder_is_not_provider_ready():
    assert load_openrouter_keys({"OPENROUTER_API_KEY": "your-key-here"}) == []
    assert provider_key_status({"OPENROUTER_API_KEY": "your-key-here"}) == {
        "configured": False,
        "key_count": 0,
        "config_error": False,
    }
