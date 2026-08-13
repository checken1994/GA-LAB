"""Local-only SCP V3.1 PC Controller API."""
from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from scp.pc_control.pc_controller import PCController

router = APIRouter(prefix="/v3/pc", tags=["v3-pc-controller"])
_controller = PCController()


class PlanRequest(BaseModel):
    command: str = Field(min_length=1, max_length=2000)
    capabilityLevel: int = Field(default=0, ge=0, le=5)
    approved: bool = False


class ExecuteRequest(PlanRequest):
    timeout: int = Field(default=120, ge=1, le=300)


class ReadRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    maxBytes: int = Field(default=200_000, ge=1_000, le=1_000_000)


class WriteRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    content: str = Field(max_length=2_000_000)
    capabilityLevel: int = Field(default=0, ge=0, le=5)
    approved: bool = False


class KillRequest(BaseModel):
    reason: str = Field(default="user requested", max_length=500)


class ClearKillRequest(BaseModel):
    approved: bool = False


def _is_local(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost"}


def _guard(request: Request, token: str | None) -> None:
    """Allow local dashboard calls; require a separate token for remote calls."""
    if _is_local(request) and os.environ.get("SCP_PC_LOCAL_ONLY", "1") == "1":
        return
    configured = os.environ.get("SCP_PC_CONTROLLER_TOKEN", "")
    if not configured or not token or not hmac.compare_digest(token, configured):
        raise HTTPException(status_code=403, detail="PC Controller is local-only or token is invalid")


@router.get("/status")
async def pc_status(request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return _controller.status()


@router.post("/plan")
async def pc_plan(payload: PlanRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return _controller.plan(payload.command, payload.capabilityLevel, payload.approved)


@router.post("/execute")
async def pc_execute(payload: ExecuteRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return await _controller.execute(payload.command, payload.capabilityLevel, payload.approved, payload.timeout)


@router.post("/read")
async def pc_read(payload: ReadRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return await _controller.read_file(payload.path, payload.maxBytes)


@router.post("/write")
async def pc_write(payload: WriteRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return await _controller.write_file(payload.path, payload.content, payload.capabilityLevel, payload.approved)


@router.post("/kill")
async def pc_kill(payload: KillRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return _controller.engage_kill_switch(payload.reason)


@router.post("/kill/clear")
async def pc_clear_kill(payload: ClearKillRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return _controller.clear_kill_switch(payload.approved)
