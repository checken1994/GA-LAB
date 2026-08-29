"""SCP V3.1 browser and AI orchestration endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from scp.web_control.ai_orchestrator import AIOrchestrator
from scp.web_control.multi_source_orchestrator import MultiSourceOrchestrator
from scp.web_control.web_navigator import WebNavigator

from scp.core.request_run_ledger import RequestRunLedger, traced_request

_WEB_CONTROL_ROUTES_LEDGER = RequestRunLedger()

router = APIRouter(prefix="/v3", tags=["v3-web-control"])
_navigator = WebNavigator()
_orchestrator = AIOrchestrator(_navigator.browser)
_multi_source = MultiSourceOrchestrator(_orchestrator, _navigator)


class BrowseRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    useLoggedInBrowser: bool = False


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    maxResults: int = Field(default=10, ge=1, le=20)


class ResilientAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20_000)
    providers: list[str] | None = None
    approved: bool = False
    useBrowser: bool = False
    allowLocal: bool = True


class AskAIRequest(BaseModel):
    ai: str = Field(min_length=2, max_length=32)
    question: str = Field(min_length=1, max_length=20_000)
    approved: bool = False
    useBrowser: bool = True
    allowApiFallback: bool = False


class CrossVerifyRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20_000)
    scpAnswer: str = Field(min_length=1, max_length=20_000)
    ais: list[str] | None = None
    approved: bool = False


def _guard(request: Request, token: str | None) -> None:
    # This first version is local-only. Remote access requires an explicit token.
    if request.headers.get("X-Forwarded-For"):
        return False  # proxied = not local
    host = request.client.host if request.client else ""
    if host in {"127.0.0.1", "::1", "localhost"}:
        return
    import hmac
    import os
    configured = os.environ.get("SCP_PC_CONTROLLER_TOKEN", "")
    if not configured or not token or not hmac.compare_digest(token, configured):
        raise HTTPException(status_code=403, detail="Web control is local-only or token is invalid")


@router.get("/web/status")
@traced_request(_WEB_CONTROL_ROUTES_LEDGER, require_write=False, action="web_status")
async def web_status(request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return {"navigator": await _navigator.status(), "orchestrator": await _orchestrator.status()}


@router.post("/web/search")
@traced_request(_WEB_CONTROL_ROUTES_LEDGER, require_write=False, action="search_web")
async def search_web(request_payload: SearchRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return await _navigator.search_public(request_payload.query, request_payload.maxResults)


@router.post("/web/browse")
@traced_request(_WEB_CONTROL_ROUTES_LEDGER, require_write=True, action="browse")
async def browse(request_payload: BrowseRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return await _navigator.browse(request_payload.url, request_payload.useLoggedInBrowser)


@router.post("/ai/ask-resilient")
@traced_request(_WEB_CONTROL_ROUTES_LEDGER, require_write=True, action="ask_resilient")
async def ask_resilient(request_payload: ResilientAskRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    if request_payload.useBrowser and not request_payload.approved:
        raise HTTPException(status_code=400, detail="Browser AI action requires approved=true")
    return await _multi_source.run(
        request_payload.question,
        providers=request_payload.providers,
        approved=request_payload.approved,
        use_browser=request_payload.useBrowser,
        allow_local=request_payload.allowLocal,
    )


@router.post("/ai/ask")
@traced_request(_WEB_CONTROL_ROUTES_LEDGER, require_write=True, action="ask_ai")
async def ask_ai(request_payload: AskAIRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    if request_payload.useBrowser and not request_payload.approved:
        raise HTTPException(status_code=400, detail="Browser AI action requires approved=true")
    return await _orchestrator.ask_ai(request_payload.ai, request_payload.question, request_payload.approved, request_payload.useBrowser, request_payload.allowApiFallback)


@router.post("/ai/cross-verify")
@traced_request(_WEB_CONTROL_ROUTES_LEDGER, require_write=False, action="cross_verify")
async def cross_verify(request_payload: CrossVerifyRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    if not request_payload.approved:
        raise HTTPException(status_code=400, detail="Cross-verification requires approved=true")
    return await _orchestrator.cross_verify(request_payload.question, request_payload.scpAnswer, request_payload.ais, request_payload.approved)
