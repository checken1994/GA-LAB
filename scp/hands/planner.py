"""SCP Hands v3.6.1 bounded planner and plan runner.

The planner is deterministic and explicit. It accepts only registered Hands
actions, evaluates a small allowlisted condition language, retries bounded
failures, records evidence, and requires approval before risky steps.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from .hands_executor import HandsExecutor


PLAN_VERSION = "3.7"
PLAN_STATES = {"PLANNED", "RUNNING", "WAITING_APPROVAL", "VERIFIED", "FAILED", "ROLLED_BACK", "COMPLETED"}
STEP_STATES = {"PLANNED", "RUNNING", "WAITING_APPROVAL", "VERIFIED", "FAILED", "ROLLED_BACK"}
PRECONDITION_TYPES = {"always", "previous_steps_verified", "plan_state", "step_state"}
POSTCONDITION_TYPES = {"verification_passed", "success", "text_contains", "url_prefix", "evidence_field_equals", "field_equals"}
RETRY_TYPES = {"verification_failed", "execution_error", "always"}


class HandsPlanner:
    """Persisted, sequential Planner for the existing Hands Executor."""

    def __init__(self, executor: HandsExecutor | None = None) -> None:
        self.executor = executor or HandsExecutor()
        self.data_dir = self.executor.data_dir
        self.plan_path = self.data_dir / "plans.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _now() -> float:
        return time.time()

    @staticmethod
    def _bounded_text(value: Any, limit: int = 5000) -> str:
        return str(value or "")[:limit]

    def _record(self, event: str, plan: dict[str, Any], extra: dict[str, Any] | None = None) -> None:
        record = {
            "timestamp": self._now(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event,
            "planId": plan.get("planId"),
            "state": plan.get("state"),
            "goal": self._bounded_text(plan.get("goal"), 500),
            "stepCount": len(plan.get("steps", [])),
        }
        if extra:
            record.update(extra)
        with self.plan_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"plan": plan, **record}, ensure_ascii=False, default=str) + "\n")
        self.executor._audit(event, {key: value for key, value in record.items() if key != "event"})

    def _load_latest(self) -> dict[str, dict[str, Any]]:
        plans: dict[str, dict[str, Any]] = {}
        if not self.plan_path.exists():
            return plans
        for line in self.plan_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            plan = record.get("plan")
            if isinstance(plan, dict) and plan.get("planId"):
                plans[str(plan["planId"])] = plan
        return plans

    def _save(self, plan: dict[str, Any], event: str, extra: dict[str, Any] | None = None) -> None:
        plan["updatedAt"] = self._now()
        self._record(event, plan, extra)

    def _get(self, plan_id: str) -> dict[str, Any] | None:
        return self._load_latest().get(plan_id)

    def _public_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(plan, ensure_ascii=False, default=str))

    @staticmethod
    def _validate_condition(raw: Any, label: str, allowed_types: set[str]) -> dict[str, Any]:
        if raw in (None, {}):
            return {"type": "always"}
        if not isinstance(raw, dict):
            raise ValueError(f"{label} must be an object")
        condition = dict(raw)
        condition_type = str(condition.get("type", "always")).strip()
        if condition_type not in allowed_types:
            raise ValueError(f"{label} has unsupported type: {condition_type}")
        if condition_type == "previous_steps_verified":
            step_ids = condition.get("stepIds", [])
            if not isinstance(step_ids, list) or not step_ids or any(not str(item).strip() for item in step_ids):
                raise ValueError(f"{label} requires a non-empty stepIds list")
            condition["stepIds"] = [str(item).strip() for item in step_ids]
        elif condition_type in {"plan_state", "step_state"}:
            if not str(condition.get("equals", "")).strip():
                raise ValueError(f"{label} requires equals")
            if condition_type == "step_state" and not str(condition.get("stepId", "")).strip():
                raise ValueError(f"{label} requires stepId")
        elif condition_type in {"text_contains", "url_prefix", "field_equals", "evidence_field_equals"}:
            if not str(condition.get("value", "")).strip() and condition_type != "field_equals":
                raise ValueError(f"{label} requires value")
            if condition_type in {"field_equals", "evidence_field_equals"} and not str(condition.get("path", "")).strip():
                raise ValueError(f"{label} requires path")
        return condition

    @staticmethod
    def _validate_retry(raw: Any, label: str) -> dict[str, Any]:
        if raw in (None, {}):
            return {"maxAttempts": 1, "backoffSeconds": 0.0, "on": "verification_failed"}
        if not isinstance(raw, dict):
            raise ValueError(f"{label} must be an object")
        try:
            max_attempts = max(1, min(int(raw.get("maxAttempts", 1)), 3))
            backoff = max(0.0, min(float(raw.get("backoffSeconds", 0)), 5.0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} has invalid numeric values") from exc
        retry_on = str(raw.get("on", raw.get("retryOn", "verification_failed"))).strip()
        if retry_on not in RETRY_TYPES:
            raise ValueError(f"{label} has unsupported on value: {retry_on}")
        return {"maxAttempts": max_attempts, "backoffSeconds": backoff, "on": retry_on}

    def _validate_step(self, raw: dict[str, Any], index: int, known_ids: set[str]) -> dict[str, Any]:
        action = str(raw.get("action", "")).strip()
        if len(action) < 3:
            raise ValueError(f"Step {index + 1} requires an action")
        definition = self.executor.registry.get(action)
        if definition is None:
            raise ValueError(f"Unknown Hands action: {action}")
        step_id = str(raw.get("stepId") or f"step-{index + 1:02d}").strip()
        if step_id in known_ids:
            raise ValueError(f"Duplicate stepId: {step_id}")
        depends_on = [str(item) for item in raw.get("dependsOn", [])]
        if any(item not in known_ids for item in depends_on):
            raise ValueError(f"Step {step_id} has a forward or unknown dependency")
        if step_id in depends_on:
            raise ValueError(f"Step {step_id} cannot depend on itself")
        params = raw.get("params", {})
        if not isinstance(params, dict):
            raise ValueError(f"Step {step_id} params must be an object")
        precondition = self._validate_condition(raw.get("precondition"), f"Step {step_id} precondition", PRECONDITION_TYPES)
        postcondition = self._validate_condition(raw.get("postcondition"), f"Step {step_id} postcondition", POSTCONDITION_TYPES)
        for dependency_id in precondition.get("stepIds", []):
            if dependency_id not in known_ids:
                raise ValueError(f"Step {step_id} precondition references unknown step: {dependency_id}")
        if precondition.get("type") == "step_state" and precondition.get("stepId") not in known_ids:
            raise ValueError(f"Step {step_id} precondition references unknown step: {precondition.get('stepId')}")
        retry_policy = self._validate_retry(raw.get("retryPolicy"), f"Step {step_id} retryPolicy")
        return {
            "stepId": step_id,
            "action": action,
            "params": params,
            "capabilityLevel": max(0, min(int(raw.get("capabilityLevel", definition.capability_level)), 5)),
            "approved": bool(raw.get("approved", False)),
            "dryRun": bool(raw.get("dryRun", False)),
            "dependsOn": depends_on,
            "precondition": precondition,
            "postcondition": postcondition,
            "retryPolicy": retry_policy,
            "state": "PLANNED",
            "attempts": 0,
            "evidence": {},
            "error": "",
        }

    def create_plan(self, goal: str, steps: list[dict[str, Any]], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        goal = self._bounded_text(goal, 1000).strip()
        if not goal:
            raise ValueError("Plan goal is required")
        if not isinstance(steps, list) or not steps or len(steps) > 20:
            raise ValueError("Plan must contain between 1 and 20 steps")
        normalized: list[dict[str, Any]] = []
        known_ids: set[str] = set()
        for index, raw in enumerate(steps):
            if not isinstance(raw, dict):
                raise ValueError(f"Step {index + 1} must be an object")
            step = self._validate_step(raw, index, known_ids)
            normalized.append(step)
            known_ids.add(step["stepId"])
        plan = {
            "planId": uuid.uuid4().hex,
            "version": PLAN_VERSION,
            "goal": goal,
            "state": "PLANNED",
            "createdAt": self._now(),
            "updatedAt": self._now(),
            "currentStepId": None,
            "completedStepCount": 0,
            "metadata": metadata if isinstance(metadata, dict) else {},
            "steps": normalized,
        }
        self._save(plan, "PLAN_CREATED")
        return self._public_plan(plan)

    def list_plans(self, limit: int = 20) -> list[dict[str, Any]]:
        plans = sorted(self._load_latest().values(), key=lambda item: float(item.get("updatedAt", 0)), reverse=True)
        return [self._public_plan(item) for item in plans[: max(1, min(limit, 100))]]

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        plan = self._get(plan_id)
        return self._public_plan(plan) if plan else None

    def _summary(self, plan: dict[str, Any]) -> dict[str, Any]:
        steps = plan.get("steps", [])
        return {
            "planId": plan.get("planId"),
            "goal": plan.get("goal", ""),
            "state": plan.get("state", "PLANNED"),
            "currentStepId": plan.get("currentStepId"),
            "stepCount": len(steps),
            "completedStepCount": sum(1 for step in steps if step.get("state") == "VERIFIED"),
            "failedStepCount": sum(1 for step in steps if step.get("state") == "FAILED"),
            "waitingApprovalCount": sum(1 for step in steps if step.get("state") == "WAITING_APPROVAL"),
            "updatedAt": plan.get("updatedAt"),
        }

    @staticmethod
    def _read_path(source: Any, path: str) -> Any:
        current = source
        for part in [item for item in path.split(".") if item][:5]:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _evaluate_condition(self, condition: dict[str, Any], plan: dict[str, Any], result: dict[str, Any] | None = None) -> tuple[bool, str]:
        condition_type = str(condition.get("type", "always"))
        if condition_type == "always":
            return True, "always"
        if condition_type == "previous_steps_verified":
            states = {str(step.get("stepId")): step.get("state") for step in plan.get("steps", [])}
            missing = [step_id for step_id in condition.get("stepIds", []) if states.get(step_id) != "VERIFIED"]
            return (not missing, "all previous steps verified" if not missing else f"steps not verified: {', '.join(missing)}")
        if condition_type == "plan_state":
            expected = str(condition.get("equals"))
            return (plan.get("state") == expected, f"plan state is {plan.get('state')}, expected {expected}")
        if condition_type == "step_state":
            step_id = str(condition.get("stepId"))
            step = next((item for item in plan.get("steps", []) if str(item.get("stepId")) == step_id), None)
            expected = str(condition.get("equals"))
            actual = step.get("state") if step else None
            return (actual == expected, f"step {step_id} state is {actual}, expected {expected}")
        if result is None:
            return False, "postcondition needs an execution result"
        if condition_type == "verification_passed":
            actual = bool((result.get("verification") or {}).get("passed"))
            return actual, f"verification.passed={actual}"
        if condition_type == "success":
            actual = bool(result.get("success"))
            return actual, f"success={actual}"
        if condition_type == "text_contains":
            expected = str(condition.get("value", ""))
            text = str(result.get("text", ""))
            return expected in text, f"text contains expected={expected!r}"
        if condition_type == "url_prefix":
            expected = str(condition.get("value", ""))
            actual = str(result.get("url", ""))
            return actual.startswith(expected), f"url={actual!r}, prefix={expected!r}"
        if condition_type in {"field_equals", "evidence_field_equals"}:
            source = result.get("evidence", {}) if condition_type == "evidence_field_equals" else result
            actual = self._read_path(source, str(condition.get("path", "")))
            expected = condition.get("value")
            return actual == expected, f"{condition_type} {condition.get('path')}={actual!r}, expected={expected!r}"
        return False, f"unsupported condition type: {condition_type}"

    async def run_plan(
        self,
        plan_id: str,
        capability_level: int = 0,
        approved: bool = False,
        dry_run: bool = False,
        stop_on_failure: bool = True,
    ) -> dict[str, Any]:
        plan = self._get(plan_id)
        if not plan:
            return {"success": False, "error": "Plan not found", "planId": plan_id}
        if plan.get("state") in {"COMPLETED", "ROLLED_BACK"}:
            return {"success": False, "error": f"Plan is already {plan.get('state')}", "plan": self._public_plan(plan)}
        plan["state"] = "RUNNING"
        self._save(plan, "PLAN_STARTED")
        last_result: dict[str, Any] = {}
        had_failure = False
        for step in plan.get("steps", []):
            if step.get("state") == "VERIFIED":
                continue
            plan["currentStepId"] = step["stepId"]
            precondition_ok, precondition_message = self._evaluate_condition(step.get("precondition", {"type": "always"}), plan)
            if not precondition_ok:
                step["state"] = "FAILED"
                step["error"] = f"Precondition failed: {precondition_message}"
                step["evidence"] = {"preconditionPassed": False, "preconditionMessage": precondition_message}
                plan["state"] = "FAILED"
                self._save(plan, "PLAN_STEP_PRECONDITION_FAILED", {"stepId": step["stepId"], "action": step["action"], "error": step["error"]})
                if stop_on_failure:
                    return {"success": False, "plan": self._public_plan(plan), "stepId": step["stepId"], "error": step["error"]}
                had_failure = True
                continue
            definition = self.executor.registry.require(step["action"])
            requested_capability = max(int(capability_level), int(step.get("capabilityLevel", 0)))
            request_approved = bool(approved or step.get("approved", False))
            if requested_capability < definition.capability_level or (definition.requires_approval and not request_approved):
                step["state"] = "WAITING_APPROVAL"
                step["error"] = "Explicit approval or higher capability is required"
                plan["state"] = "WAITING_APPROVAL"
                self._save(plan, "PLAN_STEP_WAITING_APPROVAL", {"stepId": step["stepId"], "action": step["action"]})
                return {"success": False, "waitingApproval": True, "plan": self._public_plan(plan), "stepId": step["stepId"], "error": step["error"]}
            retry_policy = step.get("retryPolicy", {"maxAttempts": 1, "backoffSeconds": 0.0, "on": "verification_failed"})
            max_attempts = max(1, min(int(retry_policy.get("maxAttempts", 1)), 3))
            retry_on = str(retry_policy.get("on", "verification_failed"))
            while int(step.get("attempts", 0)) < max_attempts:
                step["state"] = "RUNNING"
                step["attempts"] = int(step.get("attempts", 0)) + 1
                self._save(plan, "PLAN_STEP_STARTED", {"stepId": step["stepId"], "action": step["action"], "attempt": step["attempts"], "maxAttempts": max_attempts})
                try:
                    last_result = await self.executor.execute(step["action"], step.get("params", {}), requested_capability, request_approved, dry_run or bool(step.get("dryRun", False)))
                except Exception as exc:
                    last_result = {"success": False, "error": f"Planner executor error: {exc}", "verification": {"passed": False}}
                verification = last_result.get("verification") if isinstance(last_result.get("verification"), dict) else {}
                verification_passed = bool(verification.get("passed"))
                postcondition_ok, postcondition_message = self._evaluate_condition(step.get("postcondition", {"type": "verification_passed"}), plan, last_result)
                passed = bool(last_result.get("success")) and verification_passed and postcondition_ok
                step["evidence"] = {
                    "success": bool(last_result.get("success")),
                    "verificationPassed": verification_passed,
                    "postconditionPassed": postcondition_ok,
                    "postconditionMessage": postcondition_message,
                    "verificationRule": self._bounded_text(verification.get("rule"), 200),
                    "evidence": last_result.get("evidence", {}),
                    "url": self._bounded_text(last_result.get("url"), 500),
                    "path": self._bounded_text(last_result.get("path"), 500),
                    "durationMs": last_result.get("durationMs"),
                }
                step["checkpointId"] = last_result.get("checkpointId")
                step["error"] = self._bounded_text(last_result.get("error"), 1000)
                if passed:
                    step["state"] = "VERIFIED"
                    step["error"] = ""
                    self._save(plan, "PLAN_STEP_VERIFIED", {"stepId": step["stepId"], "action": step["action"], "attempt": step["attempts"]})
                    break
                failure_kind = "execution_error" if step["error"] else "verification_failed"
                can_retry = int(step.get("attempts", 0)) < max_attempts and retry_on in {failure_kind, "always"}
                if can_retry:
                    step["state"] = "RUNNING"
                    self._save(plan, "PLAN_STEP_RETRY", {"stepId": step["stepId"], "action": step["action"], "attempt": step["attempts"], "nextAttempt": int(step["attempts"]) + 1, "reason": failure_kind})
                    backoff = max(0.0, min(float(retry_policy.get("backoffSeconds", 0)), 5.0))
                    if backoff:
                        await asyncio.sleep(backoff)
                    continue
                step["state"] = "FAILED"
                plan["state"] = "FAILED"
                had_failure = True
                self._save(plan, "PLAN_STEP_FAILED", {"stepId": step["stepId"], "action": step["action"], "error": step["error"], "attempts": step["attempts"]})
                break
            if step.get("state") == "FAILED" and stop_on_failure:
                return {"success": False, "plan": self._public_plan(plan), "stepId": step["stepId"], "result": last_result}
        if had_failure:
            plan["state"] = "FAILED"
            self._save(plan, "PLAN_FAILED")
            return {"success": False, "plan": self._public_plan(plan), "result": last_result}
        plan["state"] = "COMPLETED"
        plan["currentStepId"] = None
        plan["completedStepCount"] = sum(1 for step in plan.get("steps", []) if step.get("state") == "VERIFIED")
        self._save(plan, "PLAN_COMPLETED")
        return {"success": True, "plan": self._public_plan(plan), "result": last_result}

    async def _run_dag_step(self, plan: dict[str, Any], step: dict[str, Any], capability_level: int, approved: bool, dry_run: bool) -> dict[str, Any]:
        """Execute one ready DAG node with the same evidence/approval contract."""
        definition = self.executor.registry.require(step["action"])
        requested_capability = max(int(capability_level), int(step.get("capabilityLevel", 0)))
        request_approved = bool(approved or step.get("approved", False))
        if requested_capability < definition.capability_level or (definition.requires_approval and not request_approved):
            step["state"] = "WAITING_APPROVAL"
            step["error"] = "Explicit approval or higher capability is required"
            self._save(plan, "PLAN_STEP_WAITING_APPROVAL", {"stepId": step["stepId"], "action": step["action"], "scheduler": "dag"})
            return {"success": False, "waitingApproval": True, "stepId": step["stepId"], "error": step["error"]}
        retry_policy = step.get("retryPolicy", {"maxAttempts": 1, "backoffSeconds": 0.0, "on": "verification_failed"})
        max_attempts = max(1, min(int(retry_policy.get("maxAttempts", 1)), 3))
        retry_on = str(retry_policy.get("on", "verification_failed"))
        last_result: dict[str, Any] = {}
        while int(step.get("attempts", 0)) < max_attempts:
            step["state"] = "RUNNING"
            step["attempts"] = int(step.get("attempts", 0)) + 1
            self._save(plan, "PLAN_STEP_STARTED", {"stepId": step["stepId"], "action": step["action"], "attempt": step["attempts"], "maxAttempts": max_attempts, "scheduler": "dag"})
            try:
                last_result = await self.executor.execute(step["action"], step.get("params", {}), requested_capability, request_approved, dry_run or bool(step.get("dryRun", False)))
            except Exception as exc:
                last_result = {"success": False, "error": f"Planner executor error: {exc}", "verification": {"passed": False}}
            verification = last_result.get("verification") if isinstance(last_result.get("verification"), dict) else {}
            postcondition_ok, postcondition_message = self._evaluate_condition(step.get("postcondition", {"type": "verification_passed"}), plan, last_result)
            passed = bool(last_result.get("success")) and bool(verification.get("passed")) and postcondition_ok
            step["evidence"] = {
                "success": bool(last_result.get("success")),
                "verificationPassed": bool(verification.get("passed")),
                "postconditionPassed": postcondition_ok,
                "postconditionMessage": postcondition_message,
                "verificationRule": self._bounded_text(verification.get("rule"), 200),
                "evidence": last_result.get("evidence", {}),
                "url": self._bounded_text(last_result.get("url"), 500),
                "path": self._bounded_text(last_result.get("path"), 500),
                "durationMs": last_result.get("durationMs"),
            }
            step["checkpointId"] = last_result.get("checkpointId")
            step["error"] = self._bounded_text(last_result.get("error"), 1000)
            if passed:
                step["state"] = "VERIFIED"
                step["error"] = ""
                self._save(plan, "PLAN_STEP_VERIFIED", {"stepId": step["stepId"], "action": step["action"], "attempt": step["attempts"], "scheduler": "dag"})
                return {"success": True, "stepId": step["stepId"], "result": last_result}
            failure_kind = "execution_error" if step["error"] else "verification_failed"
            can_retry = int(step.get("attempts", 0)) < max_attempts and retry_on in {failure_kind, "always"}
            if can_retry:
                self._save(plan, "PLAN_STEP_RETRY", {"stepId": step["stepId"], "action": step["action"], "attempt": step["attempts"], "nextAttempt": int(step["attempts"]) + 1, "reason": failure_kind, "scheduler": "dag"})
                backoff = max(0.0, min(float(retry_policy.get("backoffSeconds", 0)), 5.0))
                if backoff:
                    await asyncio.sleep(backoff)
                continue
            step["state"] = "FAILED"
            self._save(plan, "PLAN_STEP_FAILED", {"stepId": step["stepId"], "action": step["action"], "error": step["error"], "attempts": step["attempts"], "scheduler": "dag"})
            return {"success": False, "stepId": step["stepId"], "result": last_result, "error": step["error"]}
        return {"success": False, "stepId": step["stepId"], "error": "Retry budget exhausted"}

    async def run_dag(
        self,
        plan_id: str,
        capability_level: int = 0,
        approved: bool = False,
        dry_run: bool = False,
        max_parallel: int = 2,
        stop_on_failure: bool = True,
    ) -> dict[str, Any]:
        """Run topologically ready steps concurrently with bounded parallelism."""
        plan = self._get(plan_id)
        if not plan:
            return {"success": False, "error": "Plan not found", "planId": plan_id}
        if plan.get("state") in {"COMPLETED", "ROLLED_BACK"}:
            return {"success": False, "error": f"Plan is already {plan.get('state')}", "plan": self._public_plan(plan)}
        max_parallel = max(1, min(int(max_parallel), 4))
        step_map = {str(step.get("stepId")): step for step in plan.get("steps", [])}
        pending = {step_id for step_id, step in step_map.items() if step.get("state") != "VERIFIED"}
        completed = {step_id for step_id, step in step_map.items() if step.get("state") == "VERIFIED"}
        plan["state"] = "RUNNING"
        plan["scheduler"] = "dag"
        plan["maxParallel"] = max_parallel
        self._save(plan, "PLAN_DAG_STARTED", {"maxParallel": max_parallel})
        running: dict[str, asyncio.Task] = {}
        last_results: dict[str, Any] = {}
        while pending or running:
            ready: list[str] = []
            for step_id in sorted(pending):
                step = step_map[step_id]
                dependencies = {str(item) for item in step.get("dependsOn", [])}
                if dependencies.issubset(completed):
                    precondition_ok, precondition_message = self._evaluate_condition(step.get("precondition", {"type": "always"}), plan)
                    if not precondition_ok:
                        step["state"] = "FAILED"
                        step["error"] = f"Precondition failed: {precondition_message}"
                        step["evidence"] = {"preconditionPassed": False, "preconditionMessage": precondition_message}
                        self._save(plan, "PLAN_STEP_PRECONDITION_FAILED", {"stepId": step_id, "action": step["action"], "scheduler": "dag"})
                        if stop_on_failure:
                            plan["state"] = "FAILED"
                            self._save(plan, "PLAN_FAILED", {"scheduler": "dag", "reason": "precondition"})
                            return {"success": False, "plan": self._public_plan(plan), "stepId": step_id, "error": step["error"]}
                        pending.remove(step_id)
                        continue
                    definition = self.executor.registry.require(step["action"])
                    requested_capability = max(int(capability_level), int(step.get("capabilityLevel", 0)))
                    request_approved = bool(approved or step.get("approved", False))
                    if requested_capability < definition.capability_level or (definition.requires_approval and not request_approved):
                        step["state"] = "WAITING_APPROVAL"
                        step["error"] = "Explicit approval or higher capability is required"
                        plan["state"] = "WAITING_APPROVAL"
                        self._save(plan, "PLAN_STEP_WAITING_APPROVAL", {"stepId": step_id, "action": step["action"], "scheduler": "dag"})
                        return {"success": False, "waitingApproval": True, "plan": self._public_plan(plan), "stepId": step_id, "error": step["error"]}
                    ready.append(step_id)
            slots = max_parallel - len(running)
            for step_id in ready[: max(0, slots)]:
                pending.remove(step_id)
                step = step_map[step_id]
                running[step_id] = asyncio.create_task(self._run_dag_step(plan, step, capability_level, approved, dry_run))
            if not running:
                unresolved = sorted(pending)
                plan["state"] = "FAILED"
                self._save(plan, "PLAN_FAILED", {"scheduler": "dag", "reason": "unresolved_dependencies", "steps": unresolved})
                return {"success": False, "plan": self._public_plan(plan), "error": f"Unresolved DAG dependencies: {', '.join(unresolved)}"}
            done, _ = await asyncio.wait(list(running.values()), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                result = task.result()
                step_id = str(result.get("stepId"))
                running.pop(step_id, None)
                last_results[step_id] = result
                if result.get("success") is True:
                    completed.add(step_id)
                elif stop_on_failure:
                    for other in running.values():
                        other.cancel()
                    if running:
                        await asyncio.gather(*running.values(), return_exceptions=True)
                    plan["state"] = "FAILED"
                    self._save(plan, "PLAN_FAILED", {"scheduler": "dag", "reason": "step_failure", "stepId": step_id})
                    return {"success": False, "plan": self._public_plan(plan), "stepId": step_id, "result": result}
        plan["state"] = "COMPLETED"
        plan["currentStepId"] = None
        plan["completedStepCount"] = sum(1 for step in plan.get("steps", []) if step.get("state") == "VERIFIED")
        self._save(plan, "PLAN_DAG_COMPLETED", {"maxParallel": max_parallel, "parallelSteps": max_parallel > 1})
        return {"success": True, "plan": self._public_plan(plan), "results": last_results}

    async def rollback_plan(self, plan_id: str, capability_level: int = 3, approved: bool = False) -> dict[str, Any]:
        plan = self._get(plan_id)
        if not plan:
            return {"success": False, "error": "Plan not found", "planId": plan_id}
        checkpoints = [step.get("checkpointId") for step in reversed(plan.get("steps", [])) if step.get("checkpointId")]
        if not checkpoints:
            return {"success": False, "error": "Plan has no reversible checkpoints", "plan": self._public_plan(plan)}
        rollback_results: list[dict[str, Any]] = []
        for checkpoint_id in checkpoints:
            result = await self.executor.rollback(str(checkpoint_id), capability_level, approved)
            rollback_results.append(result)
            if not result.get("success"):
                self._save(plan, "PLAN_ROLLBACK_FAILED", {"checkpointId": checkpoint_id, "error": result.get("error", "")})
                return {"success": False, "plan": self._public_plan(plan), "rollbackResults": rollback_results}
        for step in plan.get("steps", []):
            if step.get("checkpointId"):
                step["state"] = "ROLLED_BACK"
        plan["state"] = "ROLLED_BACK"
        plan["currentStepId"] = None
        self._save(plan, "PLAN_ROLLED_BACK", {"checkpointCount": len(rollback_results)})
        return {"success": True, "plan": self._public_plan(plan), "rollbackResults": rollback_results}

    def status(self) -> dict[str, Any]:
        plans = self.list_plans(20)
        active = next((item for item in plans if item.get("state") in {"PLANNED", "RUNNING", "WAITING_APPROVAL"}), None)
        return {
            "version": PLAN_VERSION,
            "planner": "online",
            "planCount": len(plans),
            "activePlan": active,
            "states": {state: sum(1 for plan in plans if plan.get("state") == state) for state in sorted(PLAN_STATES)},
        }
