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
