"""
[V104.48] SCP Chat Ă¢â‚¬â€ WebSocket giao ti-p real-time vĂ¡Â»â€ºi user

T-I SAO: SCP V104.47 chĂ¡Â»â€° cÄ‚Â³ /ask (1 question Ă¢â€ â€™ 1 verdict) vÄ‚Â  /v1/chat/completions
(OpenAI-compat). KH-NG cÄ‚Â³ chat nhi-u turn, nhĂ¡Â»â€º context, h-i lĂ¡ÂºÂ¡i user, giĂ¡ÂºÂ£i thÄ‚Â­ch.

Module nÄ‚Â y th-m:
  - WebSocket /chat: real-time bidirectional
  - Context memory: nhĂ¡Â»â€º lĂ¡Â»â€¹ch s-­ conversation
  - SCP t-± h-i lĂ¡ÂºÂ¡i user khi UNKNOWN
  - SimpleExplainer: giĂ¡ÂºÂ£i thÄ‚Â­ch quy-t Ă„â€˜Ă¡Â»â€¹nh bĂ¡ÂºÂ±ng ti-ng ViĂ¡Â»â€¡t
  - Evolution status: user xem SCP Ă„â€˜ang t-± s-­a gÄ‚Â¬
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from types import SimpleNamespace
from scp.core.request_run_ledger import RequestRunLedger
from scp.core.chat_memory_store import ChatMemoryStore

# [FIX-CRIT-27 BUG 9] Import verify_admin from api_server to gate the
# /chat/sessions + /chat/{id}/history endpoints (previously NO auth Ă¢â‚¬â€ anyone
# could list all active sessions + read any session's full history).
from scp.api._shared import verify_admin
from scp.core.release_identity import RELEASE_LABEL
from typing import Optional

logger = logging.getLogger("scp.chat")

router = APIRouter()
_CHAT_LEDGER = RequestRunLedger()  # P2_CHAT_LEDGER


class ConversationManager:
    """QuĂ¡ÂºÂ£n lÄ‚Â½ lĂ¡Â»â€¹ch s-­ conversation per session."""

    def __init__(self, max_sessions: int = 100, max_history: int = 20, memory_store: ChatMemoryStore | None = None):
        self._sessions: dict[str, list[dict]] = {}
        self._max_sessions = max_sessions
        self._max_history = max_history
        self._memory_store = memory_store or ChatMemoryStore()
        self._persistence_failures = 0

    def get_history(self, session_id: str) -> list[dict]:
        if session_id not in self._sessions:
            loaded = self._memory_store.load(session_id, limit=self._max_history)
            if loaded:
                self._sessions[session_id] = loaded[-self._max_history :]
        return self._sessions.get(session_id, [])

    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[dict] = None):
        if session_id not in self._sessions:
            if len(self._sessions) >= self._max_sessions:
                oldest = next(iter(self._sessions))
                del self._sessions[oldest]
            self._sessions[session_id] = []

        self._sessions[session_id].append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata or {},
        })

        if len(self._sessions[session_id]) > self._max_history:
            self._sessions[session_id] = self._sessions[session_id][-self._max_history:]
        if not self._memory_store.append(session_id, role, content, metadata):
            self._persistence_failures += 1

    def persistence_status(self) -> dict:
        return {
            "mode": "redacted_durable",
            "path_configured": True,
            "write_failures": self._persistence_failures,
        }

    def get_context_string(self, session_id: str) -> str:
        history = self.get_history(session_id)
        if not history:
            return ""
        lines = []
        for msg in history[-10:]:
            role = "User" if msg["role"] == "user" else "SCP"
            lines.append(f"{role}: {msg['content'][:200]}")
        return "\n".join(lines)


_conversation_mgr = ConversationManager()


@router.websocket("/chat")
async def scp_chat(websocket: WebSocket):
    """
    WebSocket endpoint Ă¢â‚¬â€  chat real-time vĂ¡Â»â€ºi SCP.

    User g-­i: {"message": "What is 2+2?"}
    SCP trĂ¡ÂºÂ£: {"answer": "4", "verdict": "PASS", "confidence": 0.99, "reasoning": "..."}
    """
    await websocket.accept()

    try:
        from scp.security.auth_config import load_auth_config
        cfg = load_auth_config()
        # Fallback to session_id as token if token query param isn't set, for backward compat in dev UI
        client_token = str(websocket.query_params.get("token") or websocket.query_params.get("session_id", "") or "")
        if client_token.startswith("Bearer "):
            client_token = client_token[7:]
        
        import secrets
        is_valid = False
        if cfg.token and secrets.compare_digest(client_token, cfg.token):
            is_valid = True
        elif cfg.password and secrets.compare_digest(client_token, cfg.password):
            is_valid = True
            
        if not cfg.configured:
            await websocket.close(code=1011)
            return
        if not is_valid:
            await websocket.close(code=1008)
            return
    except Exception:
        await websocket.close(code=1011)
        return

    requested_session = str(websocket.query_params.get("session_id", "")).strip()
    session_id = requested_session if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", requested_session or "") else str(uuid.uuid4())[:8]
    resumed_history = bool(_conversation_mgr.get_history(session_id))
    logger.info(f"[SCP Chat] Session {session_id} connected resumed={resumed_history}")

    await websocket.send_json({
        "type": "system",
        "message": f"{RELEASE_LABEL} — kết nối. Session: {session_id}\n"
                   f"Tôi có thể kiểm tra câu trả lời, phát hiện tấn công, và tự học.\n"
                   f"Hỏi tôi bất cứ điều gì — tôi sẽ nói 'Tại sao?' và kiểm tra.",
        "session_id": session_id,
        "resumed": resumed_history,
        "memory_mode": "redacted_durable",
    })

    try:
        while True:
            data = await websocket.receive_text()
            msg = {}
            try:
                msg = json.loads(data)
                user_message = msg.get("message", "").strip()
            except json.JSONDecodeError:
                user_message = data.strip()

            task_mode = str(msg.get("mode", "")).strip().lower() in {"agent_task", "task", "orchestrate"}
            if not user_message:
                continue
            _conversation_mgr.add_message(session_id, "user", user_message, {"type": "user_message", "mode": "agent_task" if task_mode else "chat"})
            run = _CHAT_LEDGER.begin(SimpleNamespace(source="websocket_chat", domain="general", message=user_message))
            if not run.ledger_write_ok:
                await websocket.send_json({"type": "error", "message": "Audit ledger unavailable; chat processing blocked", "run_id": run.run_id, "trace_id": run.trace_id, "run_status": "DB_WRITE_FAILED", "ledger_status": "DB_WRITE_FAILED"})
                continue
            _CHAT_LEDGER.stage(run, "chat_message_started", "RUNNING")

            if task_mode:
                try:
                    from scp.core.agent_orchestrator import AgentOrchestrator

                    agent = AgentOrchestrator()
                    task_result = await agent.run(
                        goal=user_message,
                        execute=True,
                        capability_level=0,
                        approved=False,
                        parent_trace_id=run.trace_id,
                    )
                    task_status = str(task_result.get("status", "INTERNAL_FAILED"))
                    if task_result.get("ledger_status") == "DB_WRITE_FAILED":
                        outer_status = "DB_WRITE_FAILED"
                    elif task_result.get("success") is True:
                        outer_status = "SUCCESS"
                    elif task_status in {"PLAN_READY", "WAITING_APPROVAL"}:
                        outer_status = "UNKNOWN"
                    else:
                        outer_status = "INTERNAL_FAILED"
                    terminal_status, ledger_ok = _CHAT_LEDGER.finish(
                        run,
                        outer_status,
                        result={"verdict": "PASS" if outer_status == "SUCCESS" else "UNKNOWN"},
                        task_status=task_status,
                        agent_run_id=task_result.get("agent_run_id"),
                    )
                    task_response = {
                        "type": "agent_task",
                        "status": task_status,
                        "success": bool(task_result.get("success")),
                        "answer": "Đã hoàn thành tác vụ an toàn." if task_result.get("success") else "Tác vụ chưa được hoàn thành; xem trạng thái và approval.",
                        "agent_run_id": task_result.get("agent_run_id"),
                        "agent_trace_id": task_result.get("trace_id"),
                        "plan": task_result.get("plan"),
                        "approval": task_result.get("approval"),
                        "result": task_result.get("result"),
                        "run_id": run.run_id,
                        "trace_id": run.trace_id,
                        "run_status": outer_status if terminal_status != "DB_WRITE_FAILED" else "DB_WRITE_FAILED",
                        "ledger_status": "OK" if ledger_ok else "DB_WRITE_FAILED",
                    }
                    await websocket.send_json(task_response)
                    _conversation_mgr.add_message(session_id, "scp", task_response.get("answer", ""), task_response)
                except Exception as exc:
                    failure_status = _CHAT_LEDGER.classify_error(exc)
                    terminal_status, ledger_ok = _CHAT_LEDGER.finish(run, failure_status, error=exc, task_mode=True)
                    await websocket.send_json({
                        "type": "error",
                        "message": "Lỗi xử lý agent task; xem run_id trong ledger",
                        "run_id": run.run_id,
                        "trace_id": run.trace_id,
                        "run_status": terminal_status,
                        "ledger_status": "OK" if ledger_ok else "DB_WRITE_FAILED",
                    })
                continue

            _conversation_context = _conversation_mgr.get_context_string(session_id)

            try:
                import asyncio

                from scp.api_server import get_judge

                # [FIX-CRIT-27 BUG 8] Removed `os.environ.setdefault("SCP_DEV_MODE", "1")`
                # Ă¢â‚¬â€ any WebSocket client was force-enabling SCP_DEV_MODE globally,
                # which disables admin auth for ALL endpoints server-wide (verify_admin
                # reads SCP_DEV_MODE at call time). Dev mode must be explicit, not
                # auto-enabled by a chat connection.
                judge = get_judge()
                _CHAT_LEDGER.stage(run, "judge_ready", "RUNNING")

                v = await asyncio.to_thread(
                    judge.judge,
                    question=user_message,
                    ai_answer="",
                    cycle_count=0,
                    source="chat",
                    v98_context={
                        "session_id": session_id,
                        "ip": "websocket",
                        "conversation_history": _conversation_context,
                        "current_question": user_message,
                    },
                )
                _CHAT_LEDGER.stage(run, "verifier_completed", "RUNNING", verdict=v.verdict, governance_decision=v.evidence.get("governance_decision", ""))

                # [FIX-CRIT-27 BUG 7] Determine abstain BEFORE building response.
                # Previously `answer` was set to v.final_answer unconditionally,
                # then FAIL added an `explanation` but the leaked answer remained
                # in the JSON. Now FAIL/KILL/FLAGGED withhold the answer.
                _gov = v.evidence.get("governance_decision", "")
                _abstain = (_gov == "KILL") or (v.verdict in ("FAIL", "FLAGGED"))
                _ws_answer = ("[SCP: Answer withheld]" if _abstain
                              else (v.final_answer or "(Không có câu trả lời)"))
                _ws_reasoning = ("" if _abstain
                                 else (v.reasoning[:300] if v.reasoning else ""))

                response = {
                    "type": "answer",
                    "answer": _ws_answer,
                    "verdict": v.verdict,
                    "confidence": round(v.confidence, 2),
                    "domain": v.domain or "general",
                    "reasoning": _ws_reasoning,
                    "why_plan": "no" if _abstain else ("yes" if v.evidence.get("why_plan") else "no"),
                    "governance": _gov if _gov else "none",
                    "healing": 0 if _abstain else len(v.evidence.get("healing_actions", [])),
                }

                if v.verdict == "UNKNOWN":
                    response["type"] = "clarification"
                    response["question"] = (
                        f"Tôi chưa đủ thông tin để kết luận. "
                        f"Bạn có thể cung cấp thêm chi tiết về '{user_message[:50]}' không?"
                    )

                if v.verdict == "FAIL":
                    response["type"] = "rejected"
                    response["answer"] = "[SCP: Answer withheld]"  # [FIX-CRIT-27 BUG 7] belt-and-suspenders
                    response["reasoning"] = ""  # don't leak why attack was caught
                    response["explanation"] = (
                        f"Tôi không thể xác nhận câu trả lời này. Lý do: "
                        f"{v.reasoning[:200] if v.reasoning else 'Không đủ bằng chứng.'}"
                    )

                if v.verdict == "PASS":
                    response["type"] = "verified"
                    response["explanation"] = (
                        f"Đã kiểm tra: câu trả lời đạt độ tin cậy {v.confidence:.0%}. "
                        f"Domain: {v.domain}."
                    )

                if "tiến hóa" in user_message.lower() or "evolution" in user_message.lower():
                    try:
                        from scp.core.code_evolution_agent import get_evolution_agent
                        agent = get_evolution_agent()
                        response["evolution"] = agent.get_stats()
                    except Exception:
                        logger.exception("[chat.py:182] silenced exception")

                if "học" in user_message.lower() or "learning" in user_message.lower():
                    try:
                        from scp.api_server import _fast_learning
                        if _fast_learning:
                            # [SCP-DNA-FIX] FastLearningEngine exposes stats(),
                            # NOT get_stats(). Previous call -> AttributeError ->
                            # silent except -> learning stats never surfaced in chat.
                            response["learning"] = _fast_learning.stats()
                    except Exception:
                        logger.exception("[chat.py:190] silenced exception")

                run_status = RequestRunLedger.classify_result(response)
                terminal_status, ledger_ok = _CHAT_LEDGER.finish(run, run_status, result=response)
                if run_status == "SUCCESS" and terminal_status == "DB_WRITE_FAILED":
                    run_status = "DB_WRITE_FAILED"
                response.update({"run_id": run.run_id, "trace_id": run.trace_id, "run_status": run_status, "ledger_status": "OK" if ledger_ok else "DB_WRITE_FAILED"})
                await websocket.send_json(response)
                _conversation_mgr.add_message(session_id, "scp", response.get("answer", ""), response)

            except Exception as e:
                failure_status = _CHAT_LEDGER.classify_error(e)
                terminal_status, ledger_ok = _CHAT_LEDGER.finish(run, failure_status, error=e)
                await websocket.send_json({
                    "type": "error",
                    "message": "Lỗi xử lý request; xem run_id trong ledger",
                    "run_id": run.run_id,
                    "trace_id": run.trace_id,
                    "run_status": terminal_status,
                    "ledger_status": "OK" if ledger_ok else "DB_WRITE_FAILED",
                })
                logger.error(f"[SCP Chat] Error: {e}")

    except WebSocketDisconnect:
        logger.info(f"[SCP Chat] Session {session_id} disconnected")
    except Exception as e:
        logger.error(f"[SCP Chat] WebSocket error: {e}")


@router.get("/chat/sessions")
async def list_sessions(_admin: bool = Depends(verify_admin)):  # [FIX-CRIT-27 BUG 9] was NO auth
    return {
        "active_sessions": len(_conversation_mgr._sessions),
        "sessions": list(_conversation_mgr._sessions.keys()),
        "memory": _conversation_mgr.persistence_status(),
    }


@router.get("/chat/{session_id}/history")
async def get_session_history(session_id: str, _admin: bool = Depends(verify_admin)):  # [FIX-CRIT-27 BUG 9] was NO auth
    return {
        "session_id": session_id,
        "messages": _conversation_mgr.get_history(session_id),
    }
