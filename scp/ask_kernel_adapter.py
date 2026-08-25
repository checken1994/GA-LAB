from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

try:
    from .task_kernel import KernelError, TaskKernel
    from .trace_ledger import TraceLedger
except ImportError:
    from task_kernel import KernelError, TaskKernel
    from trace_ledger import TraceLedger
try:
    from scp.api_server_parts.helpers import AskResponse
except Exception:  # pragma: no cover - standalone kernel tests do not need API schema
    AskResponse = None


_TRACE_LOCK = threading.Lock()
_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def _dump(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, dict):
        return obj
    return dict(vars(obj))


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[\wÀ-ỹ]{4,}", (text or "").lower()))


class AskKernelAdapter:
    """Durable lifecycle gate around the existing context-backed /ask path.

    The adapter does not replace JudgeCore. It calls the supplied handler first,
    then independently checks the returned answer against request evidence before
    allowing the TaskKernel to complete the task.
    """

    def __init__(self, db_path: str, trace_path: str):
        self.kernel = TaskKernel(db_path)
        self.trace = TraceLedger(trace_path)

    def _task_id(
        self,
        question: str,
        contexts: list[str],
        retrieved_context: str,
        session_id: str | None,
        request_id: str | None,
    ) -> str:
        input_hash = self._input_hash(question, contexts, retrieved_context)
        # A client idempotency key is preferred. Without one, the canonical
        # request identity is stable across transport retries for the same
        # session/question/evidence tuple; it deliberately does not use time or
        # UUID, so a retry cannot silently dispatch the handler twice.
        identity = request_id or f"{session_id or ''}|{input_hash}"
        return "ask-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    def _input_hash(self, question: str, contexts: list[str], retrieved_context: str) -> str:
        raw = json_bytes(
            {
                "question": question,
                "contexts": contexts,
                "retrieved_context": retrieved_context,
            }
        )
        return "sha256:" + hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _request_id(request: Any) -> str | None:
        headers = getattr(request, "headers", None)
        if headers is None:
            return None
        value = headers.get("X-SCP-Idempotency-Key") or headers.get("Idempotency-Key")
        return str(value)[:200] if value else None

    def begin(
        self,
        question: str,
        contexts: list[str],
        retrieved_context: str,
        session_id: str | None,
        request: Any = None,
    ) -> dict[str, Any]:
        request_id = self._request_id(request)
        task_id = self._task_id(question, contexts, retrieved_context, session_id, request_id)
        input_hash = self._input_hash(question, contexts, retrieved_context)
        try:
            self.kernel.create_task(task_id, "ask-route", "rag-verified /ask", "R0", input_hash=input_hash)
            for state in ("PLANNING", "READY", "QUEUED"):
                self.kernel.transition(task_id, state, actor="ask-kernel-adapter", reason="ask_lifecycle")
            lease = self.kernel.claim(task_id, "ask-route-worker", ttl_seconds=60)
            self.kernel.start(task_id, lease.lease_id)
            logical_key, claimed = self.kernel.idempotency_claim(
                task_id,
                "rag-read",
                "rag.context.read",
                input_hash,
            )
            if not claimed:
                raise KernelError("logical ask action already claimed")
            checkpoint_id = self.kernel.checkpoint(
                task_id,
                lease.lease_id,
                "rag-read",
                "RUNNING",
                {
                    "operation": "rag-verified-read",
                    "risk_tier": "R0",
                    "contexts_count": len(contexts),
                    "retrieved_context_present": bool(retrieved_context.strip()),
                },
                0,
                logical_key,
                pre_observation_ref=f"ask://{task_id}/pre",
            )
            with _TRACE_LOCK:
                self.trace.append(
                    task_id=task_id,
                    attempt_id=lease.attempt_id,
                    step_id="rag-read",
                    lease_id=lease.lease_id,
                    checkpoint_id=checkpoint_id,
                    outcome="STARTED",
                    input_hash=input_hash,
                )
            return {
                "task_id": task_id,
                "lease_id": lease.lease_id,
                "attempt_id": lease.attempt_id,
                "checkpoint_id": checkpoint_id,
                "input_hash": input_hash,
            }
        except sqlite3.IntegrityError as exc:
            # Duplicate durable identity is a safe block, not a second handler
            # execution. The existing task is intentionally not overwritten.
            try:
                current = self.kernel.get_task(task_id)
            except Exception:
                current = {"state": "UNKNOWN"}
            with _TRACE_LOCK:
                self.trace.append(
                    task_id=task_id,
                    outcome="REJECTED_DUPLICATE",
                    reason="stable_idempotency_duplicate",
                    input_hash=input_hash,
                    existing_state=current.get("state"),
                )
            raise KernelError("stable logical ask already exists") from exc
        except Exception as exc:
            try:
                current = self.kernel.get_task(task_id)
                if current["state"] not in _TERMINAL:
                    self.kernel.set_task_kill(task_id, actor="ask-kernel-adapter-begin-failure")
            finally:
                with _TRACE_LOCK:
                    self.trace.append(
                        task_id=task_id,
                        outcome="FAILED",
                        reason="ask_begin_failed",
                        error_type=type(exc).__name__,
                        input_hash=input_hash,
                    )
            raise

    def verify_response(self, req: Any, response: Any, task: dict[str, Any]) -> dict[str, Any]:
        data = _dump(response)
        contexts = [str(value) for value in (getattr(req, "contexts", None) or []) if str(value).strip()]
        retrieved_context = str(getattr(req, "retrieved_context", "") or "").strip()
        if retrieved_context:
            contexts.append(retrieved_context)
        answer = str(data.get("final_answer") or "")
        verdict = str(data.get("verdict") or "")
        governance = str(data.get("governance_decision") or "")
        provenance_value = (data.get("v98_classification") or {}).get("provenance")
        provenance = str(provenance_value or "")
        evidence_ref = f"ask://{task['task_id']}/response/{data.get('trace_id') or 'no-trace'}"
        if not contexts or not answer or answer.startswith("[SCP:"):
            return {
                "verdict": "INSUFFICIENT",
                "verifier_id": "scp-ask-rag-verifier-v2",
                "evidence_ref": evidence_ref,
                "failures": ["missing_context_or_answer"],
                "checked": [],
            }
        evidence_terms = set().union(*(_terms(value) for value in contexts))
        answer_terms = _terms(answer)
        grounded_ratio = len(answer_terms & evidence_terms) / max(1, len(answer_terms))
        checks = {
            "verdict_pass": verdict == "PASS",
            "governance_uphold": governance == "UPHOLD",
            "grounded_ratio_min": grounded_ratio >= 0.35,
            "web_fallback_not_used": not bool(data.get("web_fallback_used")),
            # Empty provenance is tolerated for old GA-LAB responses; if the
            # route supplies one, it must explicitly be input-context-only.
            "provenance_compatible": provenance in {"", "input_context_only"},
        }
        failures = [name for name, ok in checks.items() if not ok]
        return {
            "verdict": "VERIFIED" if not failures else "CONTRADICTED",
            "verifier_id": "scp-ask-rag-verifier-v2",
            "evidence_ref": evidence_ref,
            "grounded_ratio": round(grounded_ratio, 6),
            "evidence_context_count": len(contexts),
            "evidence_context_hash": hashlib.sha256(
                json_bytes(contexts)
            ).hexdigest(),
            "checked": checks,
            "failures": failures,
        }

    def _safe_response(self, response: Any, verification: dict[str, Any]) -> Any:
        if verification.get("verdict") == "VERIFIED":
            return response
        data = _dump(response)
        data["final_answer"] = "[SCP: Answer withheld — evidence not verified]"
        data["verdict"] = "FAIL"
        data["governance_decision"] = "KILL" if data.get("governance_decision") == "KILL" else "ESCALATE"
        data["confidence"] = 0.0
        if hasattr(response, "model_copy"):
            return response.model_copy(update=data)
        if isinstance(response, dict):
            return data
        if hasattr(response, "copy"):
            try:
                return response.copy(update=data)
            except TypeError:
                return data
        return data

    def finalize(self, task: dict[str, Any], response: Any, req: Any) -> dict[str, Any]:
        task_id, lease_id = task["task_id"], task["lease_id"]
        self.kernel.transition(task_id, "VERIFYING", actor="ask-kernel-adapter", reason="ask_response_observed")
        verification = self.verify_response(req, response, task)
        if verification["verdict"] == "VERIFIED":
            final_task = self.kernel.commit_verification_result(task_id, lease_id, verification)
        else:
            self.kernel.transition(
                task_id,
                "HUMAN_REVIEW",
                actor="ask-kernel-adapter",
                reason="ask_evidence_insufficient_or_contradicted",
                payload={"verification": verification},
            )
            final_task = self.kernel.get_task(task_id)
        response_data = _dump(response)
        with _TRACE_LOCK:
            self.trace.append(
                task_id=task_id,
                attempt_id=task.get("attempt_id"),
                step_id="rag-read",
                lease_id=lease_id,
                checkpoint_id=task.get("checkpoint_id"),
                verifier_id=verification.get("verifier_id"),
                evidence_ref=verification.get("evidence_ref"),
                run_id=response_data.get("run_id"),
                trace_id=response_data.get("trace_id"),
                outcome=final_task.get("state"),
                verdict=verification.get("verdict"),
                grounded_ratio=verification.get("grounded_ratio"),
                response_elapsed_ms=response_data.get("elapsed_ms"),
            )
        return {
            "task": final_task,
            "verification": verification,
            "safe_response": self._safe_response(response, verification),
        }

    def fail(self, task: dict[str, Any], reason: str) -> None:
        try:
            current = self.kernel.get_task(task["task_id"])
            if current["state"] not in _TERMINAL:
                self.kernel.transition(task["task_id"], "FAILED", actor="ask-kernel-adapter", reason=reason)
            with _TRACE_LOCK:
                self.trace.append(
                    task_id=task["task_id"],
                    attempt_id=task.get("attempt_id"),
                    lease_id=task.get("lease_id"),
                    checkpoint_id=task.get("checkpoint_id"),
                    outcome="FAILED",
                    reason=reason,
                )
        except Exception as exc:  # non-fatal audit fallback; original error wins
            try:
                from scp.core.exception_policy import observe_nonfatal

                observe_nonfatal(component="scp/ask_kernel_adapter.py:fail", exception_type=type(exc).__name__)
            except Exception:
                return

    def _kernel_blocked_response(self, req: Any, exc: Exception) -> Any:
        session = getattr(req, "session_id", None) or "ask-kernel-blocked"
        trace_id = "trace-kernel-blocked-" + uuid.uuid4().hex
        if AskResponse is None:
            return {
                "verdict": "FAIL",
                "final_answer": "[SCP: Answer withheld — Kernel gate]",
                "confidence": 0.0,
                "domain": getattr(req, "domain_override", "") or getattr(req, "domain", "") or "general",
                "governance_decision": "KILL",
                "run_status": "REJECTED",
                "trace_id": trace_id,
            }
        return AskResponse(
            verdict="FAIL",
            final_answer="[SCP: Answer withheld — Kernel gate]",
            confidence=0.0,
            domain=getattr(req, "domain_override", "") or getattr(req, "domain", "") or "general",
            falsification_status="KERNEL_GATE",
            governance_decision="KILL",
            v98_guard={
                "mode": "rag-verified",
                "readOnly": True,
                "security_blocked": True,
                "kernel_error": type(exc).__name__,
            },
            v98_classification={"provenance": "kernel_gate", "evidence_count": 0},
            elapsed_ms=0.0,
            session_id=session,
            run_id="run-kernel-blocked-" + uuid.uuid4().hex,
            trace_id=trace_id,
            run_status="REJECTED",
            ledger_status="BLOCKED",
        )

    async def run_rag(
        self,
        req: Any,
        request: Any,
        handler: Callable[[Any, Any], Awaitable[Any]],
    ) -> Any:
        try:
            task = self.begin(
                req.question,
                list(req.contexts or []),
                req.retrieved_context or "",
                req.session_id,
                request=request,
            )
        except Exception as exc:
            return self._kernel_blocked_response(req, exc)
        try:
            response = await handler(req, request)
            result = self.finalize(task, response, req)
            return result["safe_response"]
        except Exception:
            self.fail(task, "ask_rag_exception")
            raise


def json_bytes(value: Any) -> bytes:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
