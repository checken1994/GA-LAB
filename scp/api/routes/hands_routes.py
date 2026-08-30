"""SCP Hands v3.2│Ă¢â€Â¬Ă¢â‚¬Å“v3.6 local-only action and planner endpoints."""
from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from scp.core.request_run_ledger import RequestRunLedger, traced_request
from scp.api._shared import verify_admin
from scp.hands.goal_parser import GoalParser
from scp.hands.hands_executor import HandsExecutor
from scp.hands.planner import HandsPlanner
from scp.hands.task_kernel_bridge import TaskKernelHandsBridge

_HANDS_ROUTES_LEDGER = RequestRunLedger()

router = APIRouter(prefix="/v3/hands", tags=["v3.5-hands", "v3.6-planner"])
_hands = HandsExecutor()
_hands_bridge = TaskKernelHandsBridge(_hands)
_planner = HandsPlanner(_hands_bridge)
_goal_parser = GoalParser(_planner)


def _active_bridge() -> TaskKernelHandsBridge:
    global _hands_bridge
    if _hands_bridge.executor is not _hands:
        _hands_bridge = TaskKernelHandsBridge(_hands)
    return _hands_bridge


class CapabilityControlRequest(BaseModel):
    reason: str = Field(default="operator_control", min_length=1, max_length=256)


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


class HandsReconcileRequest(BaseModel):
    taskId: str = Field(min_length=8, max_length=128)
    checkpointId: str = Field(min_length=8, max_length=128)
    outcome: str = Field(min_length=8, max_length=16)
    evidenceRef: str = Field(min_length=1, max_length=512)
    verifierId: str | None = Field(default=None, max_length=128)


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


class PlannerRollbackRequest(BaseModel):
    capabilityLevel: int = Field(default=3, ge=0, le=5)
    approved: bool = False


class PlannerRecoveryRequest(BaseModel):
    decision: str = Field(min_length=6, max_length=32)
    evidenceRef: str = Field(min_length=1, max_length=512)
    approved: bool = False


def _guard(request: Request, token: str | None) -> None:
    host = request.client.host if request.client else ""
    is_local = host in {"127.0.0.1", "::1", "localhost"}
    configured = os.environ.get("SCP_PC_CONTROLLER_TOKEN", "")
    if not configured or not token or not __import__("hmac").compare_digest(token, configured):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="SCP Hands is local-only or token is invalid")


@router.get("/status")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=False, action="hands_status")
async def hands_status(request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    result = _hands.status()
    result["planner"] = _planner.status()
    result["plannerVersion"] = "3.7"
    return result


@router.get("/capabilities")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=False, action="hands_capability_status")
async def hands_capability_status(request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return {"success": True, "capability": _hands.capability_status()}


@router.post("/capabilities/revoke")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="hands_capability_revoke")
async def hands_capability_revoke(payload: CapabilityControlRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return {"success": True, "capability": _hands.revoke_capabilities(payload.reason, "operator")}


@router.post("/capabilities/restore")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="hands_capability_restore")
async def hands_capability_restore(payload: CapabilityControlRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return {"success": True, "capability": _hands.restore_capabilities(payload.reason, "operator")}


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
    request_key = request.headers.get("X-SCP-Idempotency-Key") or request.headers.get("Idempotency-Key")
    return await _active_bridge().execute(payload.action, payload.params, payload.capabilityLevel, payload.approved, payload.dryRun, request_key=request_key)


@router.post("/rollback")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="hands_rollback")
async def hands_rollback(payload: HandsRollbackRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return await _active_bridge().rollback(payload.checkpointId, payload.capabilityLevel, payload.approved)


@router.post("/reconcile")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="hands_reconcile")
async def hands_reconcile(payload: HandsReconcileRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    try:
        task = _active_bridge().reconcile_unknown(
            payload.taskId,
            payload.checkpointId,
            payload.outcome,
            payload.evidenceRef,
            payload.verifierId,
        )
        return {"success": True, "task": task}
    except Exception as exc:
        return {"success": False, "error": str(exc), "taskId": payload.taskId}


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
    for step in payload.steps:
        if step.get("approved"):
            step["approved"] = False
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
    return await _goal_parser.parse(payload.goal)


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


@router.post("/planner/{plan_id}/recover")
@traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="planner_recover")
async def planner_recover(plan_id: str, payload: PlannerRecoveryRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    return _planner.recover_plan(plan_id, payload.decision, payload.evidenceRef, payload.approved)
