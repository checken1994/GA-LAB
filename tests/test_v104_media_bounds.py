from __future__ import annotations

import base64

import pytest

from scp.api.routes.v104_routes import (
    _MAX_AUDIO_BASE64_BYTES,
    _MAX_IMAGE_BASE64_BYTES,
    _decode_bounded_base64,
    _PayloadTooLarge,
)


def test_bounded_base64_accepts_small_payload() -> None:
    raw = b"safe fixture"
    encoded = base64.b64encode(raw).decode("ascii")
    assert _decode_bounded_base64(encoded, max_bytes=1024, label="image") == raw


def test_bounded_base64_rejects_invalid_encoding() -> None:
    with pytest.raises(ValueError, match="invalid image base64"):
        _decode_bounded_base64("not-base64!", max_bytes=1024, label="image")


def test_bounded_base64_rejects_encoded_size_before_decode() -> None:
    oversized = "A" * (((_MAX_IMAGE_BASE64_BYTES + 2) // 3) * 4 + 1)
    with pytest.raises(_PayloadTooLarge):
        _decode_bounded_base64(oversized, max_bytes=_MAX_IMAGE_BASE64_BYTES, label="image")


def test_audio_budget_is_explicit_and_smaller_payload_passes() -> None:
    raw = b"audio fixture"
    encoded = base64.b64encode(raw).decode("ascii")
    assert _MAX_AUDIO_BASE64_BYTES > _MAX_IMAGE_BASE64_BYTES
    assert _decode_bounded_base64(encoded, max_bytes=_MAX_AUDIO_BASE64_BYTES, label="audio") == raw
