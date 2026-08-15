"""SCP Hands v3.2Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Å“v3.6 local-only action and planner endpoints."""
from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from scp.hands.goal_parser import GoalParser
from scp.hands.hands_executor import HandsExecutor
from scp.hands.planner import HandsPlanner

from scp.core.request_run_ledger import RequestRunLedger, traced_request

_HANDS_ROUTES_LEDGER = RequestRunLedger()

router = APIRouter(prefix="/v3/hands", tags=["v3.5-hands", "v3.6-planner"])
_hands = HandsExecutor()
_planner = HandsPlanner(_hands)
_goal_parser = GoalParser(_planner)


class HandsActionRequest(BaseModel):
    action: str = Field(min_length=3, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    capabilityLevel: int = Field(default=0, ge=0, le=5)
    approved: bool = False
    dryRun: bool = False


class HandsRollbackRequest(BaseModel):
    checkpointId: str = Field(min_length=8, max_length=128)
    capabilityLevel: int = Field(default=3, ge=0, le=5)
    approved: bool = False


class PlannerCreateRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=1000)
    steps: list[dict[str, Any]] = Field(min_length=1, max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlannerRunRequest(BaseModel):
    capabilityLevel: int = Field(default=0, ge=0, le=5)
    approved: bool = False
    dryRun: bool = False
    stopOnFailure: bool = True


class PlannerDagRunRequest(BaseModel):
    capabilityLevel: int = Field(default=0, ge=0, le=5)
    approved: bool = False
    dryRun: bool = False
    maxParallel: int = Field(default=2, ge=1, le=4)
    stopOnFailure: bool = True


class GoalParseRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    preferLocal: bool = True


class PlannerRollbackRequest(BaseModel):
    capabilityLevel: int = Field(default=3, ge=0, le=5)
    approved: bool = False


def _guard(request: Request, token: str | None) -> None:
    host = request.client.host if request.client else ""
    if host in {"127.0.0.1", "::1", "localhost"} and os.environ.get("SCP_HANDS_LOCAL_ONLY", "1") == "1":
        return
    configured = os.environ.get("SCP_PC_CONTROLLER_TOKEN", "")
    if not configured or not token or not hmac.compare_digest(token, configured):
        raise HTTPException(status_code=403, detail="SCP Hands is local-only or token is invalid")


@router.get("/status")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=False, action="hands_status")
async def hands_status(request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    result = _hands.status()
    result["planner"] = _planner.status()
    result["plannerVersion"] = "3.7"
    return result


@router.get("/actions")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=False, action="hands_actions")
async def hands_actions(request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return {"version": "3.5", "actions": _hands.registry.list(), "backwardCompatibleRoutes": ["/status", "/actions", "/plan", "/execute", "/rollback"], "plannerVersion": "3.7"}


@router.post("/plan")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=False, action="hands_plan")
async def hands_plan(payload: HandsActionRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    try:
        return {"success": True, **_hands.registry.policy_preview(payload.action, payload.capabilityLevel, payload.approved)}
    except KeyError as exc:
        return {"success": False, "action": payload.action, "error": str(exc), "allowed": False}


@router.post("/execute")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="hands_execute")
async def hands_execute(payload: HandsActionRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return await _hands.execute(payload.action, payload.params, payload.capabilityLevel, payload.approved, payload.dryRun)


@router.post("/rollback")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="hands_rollback")
async def hands_rollback(payload: HandsRollbackRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return await _hands.rollback(payload.checkpointId, payload.capabilityLevel, payload.approved)


@router.get("/planner/status")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=False, action="planner_status")
async def planner_status(request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return _planner.status()


@router.get("/planner")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=False, action="planner_list")
async def planner_list(request: Request, limit: int = 20, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return {"version": "3.7", "plans": _planner.list_plans(limit)}


@router.get("/planner/{plan_id}")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=False, action="planner_get")
async def planner_get(plan_id: str, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    plan = _planner.get_plan(plan_id)
    if not plan:
        return {"success": False, "error": "Plan not found", "planId": plan_id}
    return {"success": True, "plan": plan}


@router.post("/planner")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="planner_create")
async def planner_create(payload: PlannerCreateRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    try:
        plan = _planner.create_plan(payload.goal, payload.steps, payload.metadata)
        return {"success": True, "version": "3.7", "plan": plan}
    except (TypeError, ValueError, KeyError) as exc:
        return {"success": False, "version": "3.7", "error": str(exc)}


@router.post("/planner/{plan_id}/run")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="planner_run")
async def planner_run(plan_id: str, payload: PlannerRunRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return await _planner.run_plan(plan_id, payload.capabilityLevel, payload.approved, payload.dryRun, payload.stopOnFailure)


@router.post("/planner/parse")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=False, action="planner_parse")
async def planner_parse(payload: GoalParseRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return await _goal_parser.parse(payload.goal, prefer_local=payload.preferLocal)


@router.post("/planner/{plan_id}/run-dag")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="planner_run_dag")
async def planner_run_dag(plan_id: str, payload: PlannerDagRunRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return await _planner.run_dag(plan_id, payload.capabilityLevel, payload.approved, payload.dryRun, payload.maxParallel, payload.stopOnFailure)


@router.post("/planner/{plan_id}/rollback")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="planner_rollback")
async def planner_rollback(plan_id: str, payload: PlannerRollbackRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return await _planner.rollback_plan(plan_id, payload.capabilityLevel, payload.approved)
