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


def test_valid_token_verification_and_payload_roundtrip() -> None:
    token = capability_token.mint_token("agent-1", "exec", 2, ttl_seconds=300)
    res = capability_token.verify_token(token, required_scope="exec")
    assert res["valid"] is True
    assert res["payload"]["iss"] == "agent-1"
    assert res["payload"]["scope"] == "exec"
    assert res["payload"]["cap"] == 2

    # Default wildcard required_scope allows specific token scope
    res_wild = capability_token.verify_token(token)
    assert res_wild["valid"] is True
    assert res_wild["payload"]["scope"] == "exec"


def test_base64_padding_variations_decode_successfully() -> None:
    # Different payload string lengths exercise all base64 padding boundaries (mod 4: 0, 1, 2, 3)
    for s in ["a", "ab", "abc", "abcd", "abcde", "abcdef"]:
        token = capability_token.mint_token("iss", s, 1, ttl_seconds=300)
        res = capability_token.verify_token(token, required_scope=s)
        assert res["valid"] is True, f"Verification failed for scope: {s}"


def test_corrupted_payload_with_valid_signature_fails_closed() -> None:
    import hashlib
    import hmac

    bad_payload_b64 = "bm90LWpzb24"  # "not-json" in base64
    sig = hmac.new(capability_token._SECRET, bad_payload_b64.encode(), hashlib.sha256).hexdigest()
    token = f"{bad_payload_b64}.{sig}"
    res = capability_token.verify_token(token)
    assert res["valid"] is False
    assert res["error"] == "Invalid payload"


def test_token_missing_exp_claim_fails_closed(monkeypatch) -> None:
    import hashlib
    import hmac

    monkeypatch.setattr(capability_token.time, "time", lambda: 0.5)
    payload_b64 = base64.urlsafe_b64encode(json.dumps({"scope": "read"}).encode()).decode().rstrip("=")
    sig = hmac.new(capability_token._SECRET, payload_b64.encode(), hashlib.sha256).hexdigest()
    res = capability_token.verify_token(f"{payload_b64}.{sig}", required_scope="read")
    assert res["valid"] is False
    assert res["error"] == "Token expired"


def test_expired_token_and_boundary_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(capability_token.time, "time", lambda: 1_000.0)
    token = capability_token.mint_token("issuer", "read", 1, ttl_seconds=60)

    # Within TTL
    monkeypatch.setattr(capability_token.time, "time", lambda: 1_059.0)
    assert capability_token.verify_token(token)["valid"] is True

    # Exactly at boundary (exp == 1060, time == 1060 -> 1060 < 1060 is False -> valid)
    monkeypatch.setattr(capability_token.time, "time", lambda: 1_060.0)
    assert capability_token.verify_token(token)["valid"] is True

    # 1 second past boundary (exp == 1060, time == 1061 -> 1060 < 1061 is True -> expired)
    monkeypatch.setattr(capability_token.time, "time", lambda: 1_061.0)
    expired = capability_token.verify_token(token)
    assert expired["valid"] is False
    assert expired["error"] == "Token expired"


def test_scope_mismatch_and_wildcard_semantics() -> None:
    token = capability_token.mint_token("issuer", "read", 1, ttl_seconds=600)

    assert capability_token.verify_token(token, required_scope="read")["valid"] is True
    assert capability_token.verify_token(token)["valid"] is True

    denied = capability_token.verify_token(token, required_scope="write")
    assert denied["valid"] is False
    assert denied["error"] == "Scope mismatch"

    wildcard_token = capability_token.mint_token("issuer", "*", 1, ttl_seconds=600)
    assert capability_token.verify_token(wildcard_token, required_scope="write")["valid"] is True
    assert capability_token.verify_token(wildcard_token, required_scope="read")["valid"] is True

