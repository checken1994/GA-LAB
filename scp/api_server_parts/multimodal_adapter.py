"""Composition-boundary adapter that wires restored Vision into /ask.

The large extracted `_ask_impl.py` remains byte-identical to main.  This
wrapper performs the missing multimodal security/vision pre-pass and then
invokes the original function rebound against api_server's authoritative
globals.  This keeps the port small, reversible, and avoids a second runtime.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import types
from typing import Callable


def build_multimodal_ask_wrapper(base_fn: Callable):
    async def _ask_impl(req, request):
        from fastapi import HTTPException
        from scp.api_server_parts.helpers import AskResponse, _safe_fetch_url
        from scp.capabilities.vision import VisionHandler
        from scp.security.image_voice_detector import ImageJailbreakDetector

        image_bytes = None
        mime_type = "image/jpeg"
        if getattr(req, "image_data", None):
            try:
                raw = req.image_data
                if "," in raw and raw.lower().startswith("data:"):
                    header, raw = raw.split(",", 1)
                    declared = header[5:].split(";", 1)[0].strip().lower()
                    if declared in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
                        mime_type = declared
                image_bytes = base64.b64decode(raw, validate=True)
                if not image_bytes or len(image_bytes) > 6_000_000:
                    raise ValueError("image_too_large_or_empty")
            except (binascii.Error, ValueError):
                raise HTTPException(status_code=400, detail="Invalid or oversized image_data") from None
        elif getattr(req, "image_url", None):
            try:
                image_bytes = await asyncio.to_thread(_safe_fetch_url, req.image_url)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid or disallowed image_url") from None

        ai_answer = getattr(req, "ai_answer", "")
        if image_bytes:
            detection = ImageJailbreakDetector().detect(image_bytes=image_bytes)
            if detection and detection.jailbreak_detected:
                return AskResponse(
                    verdict="FAIL",
                    final_answer="[SCP: Answer withheld — multimodal jailbreak detected]",
                    confidence=0.0,
                    domain="security",
                    elapsed_ms=0,
                    session_id=getattr(req, "session_id", None),
                )
            if not str(ai_answer or "").strip():
                observation = await VisionHandler().observe_image(
                    image_bytes,
                    getattr(req, "question", ""),
                    mime_type=mime_type,
                    data_class="INTERNAL",
                )
                if not observation:
                    return AskResponse(
                        verdict="UNKNOWN",
                        final_answer="SCP không thể quan sát nội dung ảnh qua một đường VLM được phép; không suy đoán từ ảnh.",
                        confidence=0.0,
                        domain="vision",
                        elapsed_ms=0,
                        session_id=getattr(req, "session_id", None),
                    )
                ai_answer = observation.description

        if hasattr(req, "model_copy"):
            forwarded = req.model_copy(update={"ai_answer": ai_answer, "image_data": None, "image_url": None})
        else:
            forwarded = req.copy(update={"ai_answer": ai_answer, "image_data": None, "image_url": None})

        # api_server._rebind_part_function rebinds this wrapper to the
        # composition-root globals. Rebind the original extracted function to
        # those same globals before invoking it, preserving all legacy state.
        rebound_base = types.FunctionType(
            base_fn.__code__, globals(), base_fn.__name__, base_fn.__defaults__, base_fn.__closure__
        )
        rebound_base.__kwdefaults__ = base_fn.__kwdefaults__
        return await rebound_base(forwarded, request)

    return _ask_impl
