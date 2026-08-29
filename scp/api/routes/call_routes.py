from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, WebSocket

from scp.core.call_session_hub import CallSessionHub
from scp.core.request_run_ledger import RequestRunLedger, traced_request

_LEDGER = RequestRunLedger()
_HUB = CallSessionHub()
router = APIRouter(prefix="/v3/call", tags=["v3-call"])


def _guard(request: Request, token: str | None, authorization: str | None = None) -> None:
    if request.headers.get("X-Forwarded-For"):
        return False  # proxied = not local
    host = request.client.host if request.client else ""
    if os.environ.get("SCP_AGENT_LOCAL_ONLY", "1") == "1" and host in {"127.0.0.1", "::1", "localhost"}:
        return
    configured = os.environ.get("SCP_PC_CONTROLLER_TOKEN", "")
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else ""
    supplied = token or bearer
    if not configured or not supplied or not hmac.compare_digest(supplied, configured):
        raise HTTPException(status_code=403, detail="SCP call is local-only or token is invalid")


@router.post("/sessions")
@traced_request(_LEDGER, require_write=True, action="call_session_create")
async def create_call_session(request: Request, x_scp_pc_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token, authorization)
    try:
        data = await _HUB.create()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # The short-lived join token is returned to the local caller by design.
    # The request ledger only stores bounded, redacted metadata.
    return {"success": True, **data}


@router.get("/status")
@traced_request(_LEDGER, require_write=False, action="call_session_status")
async def call_status(request: Request, x_scp_pc_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token, authorization)
    return {"success": True, **_HUB.stats()}


@router.websocket("/sessions/{call_id}/signal")
async def call_signal(websocket: WebSocket, call_id: str, token: str = "") -> None:
    # This token is scoped to one short-lived call, not a global admin credential.
    await _HUB.connect(call_id[:64], token[:160], websocket)


__all__ = ["router"]
