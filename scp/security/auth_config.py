"""Canonical, fail-closed authentication configuration.

This module centralizes file/env precedence for backend and packaged runs. It
never logs or returns credential values in diagnostics.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


class AuthConfigError(RuntimeError):
    """Authentication configuration is unsafe or unreadable."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _clean(value: str | None) -> str:
    value = (value or "").lstrip("\ufeff").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _file_value(file_env: str, raw_path: str) -> tuple[str, str]:
    path_text = _clean(raw_path)
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        value = path.read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise AuthConfigError(f"{file_env}_UNREADABLE") from exc
    value = _clean(value)
    if not value:
        raise AuthConfigError(f"{file_env}_EMPTY")
    return value, "file"


def _resolve_value(env_name: str, file_env: str) -> tuple[str, str]:
    direct = _clean(os.environ.get(env_name))
    file_ref = _clean(os.environ.get(file_env))
    if file_ref:
        from_file, source = _file_value(file_env, file_ref)
        if direct and direct != from_file:
            raise AuthConfigError(f"{env_name}_FILE_CONFLICT")
        return from_file, source
    if direct:
        return direct, "env"
    return "", "none"


@dataclass(frozen=True)
class AuthConfig:
    token: str
    password: str
    token_source: str
    password_source: str

    @property
    def configured(self) -> bool:
        return bool(self.token or self.password)

    @property
    def config_digest(self) -> str:
        material = "|".join(
            (
                self.token,
                self.password,
                self.token_source,
                self.password_source,
            )
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def diagnostics(self) -> dict[str, object]:
        return {
            "auth_configured": self.configured,
            "token_source": self.token_source,
            "password_source": self.password_source,
            "token_length": len(self.token),
            "password_length": len(self.password),
            "config_digest": self.config_digest,
        }


def load_auth_config() -> AuthConfig:
    token, token_source = _resolve_value(
        "SCP_AUTH_TOKEN_SECRET", "SCP_AUTH_TOKEN_SECRET_FILE"
    )
    password, password_source = _resolve_value(
        "SCP_AUTH_PASSWORD", "SCP_AUTH_PASSWORD_FILE"
    )
    return AuthConfig(
        token=token,
        password=password,
        token_source=token_source,
        password_source=password_source,
    )


__all__ = ["AuthConfig", "AuthConfigError", "load_auth_config"]
