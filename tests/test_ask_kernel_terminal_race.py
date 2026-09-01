from __future__ import annotations

import pytest

from scp.ask_kernel_adapter import AskKernelAdapter


class DummyReq:
    question = "what color is the sky?"
    contexts = ["sky is blue"]
    retrieved_context = ""
    session_id = "terminal-race"


@pytest.mark.asyncio
async def test_cancelled_task_before_finalize_withholds_unverified_response(tmp_path, monkeypatch):
    adapter = AskKernelAdapter(
        db_path=str(tmp_path / "kernel.sqlite3"),
        trace_path=str(tmp_path / "trace.jsonl"),
    )
    req = DummyReq()
    task = adapter.begin(
        req.question,
        list(req.contexts),
        req.retrieved_context,
        req.session_id,
    )
    adapter.kernel.transition(
        task["task_id"],
        "CANCELLED",
        actor="test",
        reason="simulate kill-switch race while handler was in flight",
    )

    async def forbidden_verify(*args, **kwargs):
        raise AssertionError("terminal task must not enter response verification")

    monkeypatch.setattr(adapter, "verify_response", forbidden_verify)
    raw_response = {
        "final_answer": "UNVERIFIED ANSWER MUST NOT ESCAPE",
        "verdict": "PASS",
        "governance_decision": "UPHOLD",
        "confidence": 1.0,
        "trace_id": "trace-terminal-race",
    }

    result = await adapter.finalize(task, raw_response, req)

    assert result["task"]["state"] == "CANCELLED"
    assert result["verification"]["verdict"] == "INSUFFICIENT"
    assert "task_terminal_before_verification" in result["verification"]["failures"]
    safe = result["safe_response"]
    assert safe["verdict"] == "FAIL"
    assert safe["confidence"] == 0.0
    assert safe["governance_decision"] in {"ESCALATE", "KILL"}
    assert safe["final_answer"].startswith("[SCP: Answer withheld")
    assert "UNVERIFIED ANSWER MUST NOT ESCAPE" not in safe["final_answer"]
    assert adapter.kernel.get_task(task["task_id"])["state"] == "CANCELLED"
