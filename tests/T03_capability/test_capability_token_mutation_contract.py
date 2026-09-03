from __future__ import annotations

import base64
import json

from scp.core import capability_token


def _payload(token: str) -> dict:
    encoded = token.split(".", 1)[0]
    encoded += "=" * (-len(encoded) % 4)
    return json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))


def test_default_token_ttl_is_exact(monkeypatch) -> None:
    monkeypatch.setattr(capability_token.time, "time", lambda: 1_000.0)

    payload = _payload(capability_token.mint_token("issuer", "read", 1))

    assert payload["iat"] == 1_000
    assert payload["exp"] == 4_600


def test_invalid_formats_and_signature_fail_closed() -> None:
    assert capability_token.verify_token("")["valid"] is False
    assert capability_token.verify_token("no-separator")["valid"] is False
    assert capability_token.verify_token("a.b.c")["valid"] is False

    token = capability_token.mint_token("issuer", "read", 1, ttl_seconds=60)
    payload, _signature = token.rsplit(".", 1)
    result = capability_token.verify_token(f"{payload}.tampered")
    assert result["valid"] is False
    assert result["error"] == "Invalid signature"


def test_expired_token_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(capability_token.time, "time", lambda: 1_000.0)
    token = capability_token.mint_token("issuer", "read", 1, ttl_seconds=60)

    monkeypatch.setattr(capability_token.time, "time", lambda: 2_000.0)
    result = capability_token.verify_token(token)
    assert result["valid"] is False
    assert result["error"] == "Token expired"


def test_expiry_boundary_is_inclusive_of_exp_second(monkeypatch) -> None:
    monkeypatch.setattr(capability_token.time, "time", lambda: 1_000.0)
    token = capability_token.mint_token("issuer", "read", 1, ttl_seconds=60)

    monkeypatch.setattr(capability_token.time, "time", lambda: 1_059.0)
    assert capability_token.verify_token(token)["valid"] is True

    monkeypatch.setattr(capability_token.time, "time", lambda: 1_060.0)
    assert capability_token.verify_token(token)["valid"] is True

    monkeypatch.setattr(capability_token.time, "time", lambda: 1_061.0)
    expired = capability_token.verify_token(token)
    assert expired["valid"] is False
    assert expired["error"] == "Token expired"


def test_scope_mismatch_fails_closed() -> None:
    token = capability_token.mint_token("issuer", "read", 1, ttl_seconds=600)

    assert capability_token.verify_token(token, required_scope="read")["valid"] is True
    assert capability_token.verify_token(token)["valid"] is True

    denied = capability_token.verify_token(token, required_scope="write")
    assert denied["valid"] is False
    assert denied["error"] == "Scope mismatch"


def test_wildcard_issuer_scope_passes_any_requirement() -> None:
    token = capability_token.mint_token("issuer", "*", 1, ttl_seconds=600)

    assert capability_token.verify_token(token, required_scope="write")["valid"] is True
    assert capability_token.verify_token(token, required_scope="read")["valid"] is True


def test_base64_padding_variants_stay_valid() -> None:
    # Payloads whose stripped base64 length is not a multiple of 4 exercise the
    # "=" padding restoration path in verify_token; all must stay valid.
    for issuer in ("a", "abc", "abcd"):
        token = capability_token.mint_token(issuer, "read", 1, ttl_seconds=600)
        encoded = token.rsplit(".", 1)[0]
        assert len(encoded) % 4 != 0, "test premise: this token needs padding"
        assert capability_token.verify_token(token)["valid"] is True
