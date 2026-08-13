from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from scp.security.auth import verify_admin
from scp.security.auth_config import AuthConfigError, load_auth_config


def _request(ip: str = "198.51.100.10"):
    return SimpleNamespace(client=SimpleNamespace(host=ip))


def test_file_normalization_and_diagnostics(tmp_path, monkeypatch):
    path = tmp_path / "token"
    path.write_text("\ufeff  \"fixture-token\"\r\n", encoding="utf-8")
    monkeypatch.delenv("SCP_AUTH_TOKEN_SECRET", raising=False)
    monkeypatch.setenv("SCP_AUTH_TOKEN_SECRET_FILE", str(path))
    monkeypatch.delenv("SCP_AUTH_PASSWORD", raising=False)
    monkeypatch.delenv("SCP_AUTH_PASSWORD_FILE", raising=False)
    config = load_auth_config()
    assert config.token == "fixture-token"
    assert config.token_source == "file"
    assert config.diagnostics()["token_length"] == len("fixture-token")
    assert "fixture-token" not in str(config.diagnostics())


def test_file_and_direct_conflict_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "token"
    path.write_text("file-token\n", encoding="utf-8")
    monkeypatch.setenv("SCP_AUTH_TOKEN_SECRET_FILE", str(path))
    monkeypatch.setenv("SCP_AUTH_TOKEN_SECRET", "different-direct-token")
    with pytest.raises(AuthConfigError, match="SCP_AUTH_TOKEN_SECRET_FILE_CONFLICT"):
        load_auth_config()


def test_verify_admin_correct_missing_wrong_and_invalid_config(tmp_path, monkeypatch):
    monkeypatch.delenv("SCP_AUTH_PASSWORD", raising=False)
    monkeypatch.delenv("SCP_AUTH_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("SCP_AUTH_TOKEN_SECRET", "fixture-token")
    monkeypatch.delenv("SCP_AUTH_TOKEN_SECRET_FILE", raising=False)
    assert verify_admin("Bearer fixture-token", request=_request("198.51.100.11")) is True
    with pytest.raises(HTTPException) as missing:
        verify_admin("", request=_request("198.51.100.12"))
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException) as wrong:
        verify_admin("Bearer wrong-token", request=_request("198.51.100.13"))
    assert wrong.value.status_code == 401

    path = tmp_path / "token"
    path.write_text("file-token\n", encoding="utf-8")
    monkeypatch.setenv("SCP_AUTH_TOKEN_SECRET_FILE", str(path))
    monkeypatch.setenv("SCP_AUTH_TOKEN_SECRET", "different-direct-token")
    with pytest.raises(HTTPException) as invalid:
        verify_admin("Bearer file-token", request=_request("198.51.100.14"))
    assert invalid.value.status_code == 503
