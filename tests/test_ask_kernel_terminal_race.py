from __future__ import annotations

import pytest

from scp.ask_kernel_adapter import AskKernelAdapter


class _Req:
    session_id = "terminal-race-test"
    domain_override = ""
    domain = "general"


class _Kernel:
    def __init__(self, state: str) -> None:
        self.state = state
        self.transition_calls = 0

    def get_task(self, task_id: str) -> dict[str, str]:
        return {"task_id": task_id, "state": self.state}

    def transition(self, *args, **kwargs):
        self.transition_calls += 1
        raise AssertionError("terminal task must not transition to VERIFYING")


class _Trace:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def append(self, **fields):
        self.entries.append(fields)
        return fields


def _dump_response(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return dict(vars(value))


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_state", ["CANCELLED", "FAILED", "COMPLETED"])
async def test_finalize_fails_closed_if_task_becomes_terminal_before_verification(
    monkeypatch, terminal_state: str
) -> None:
    adapter = AskKernelAdapter.__new__(AskKernelAdapter)
    adapter.kernel = _Kernel(terminal_state)
    adapter.trace = _Trace()

    async def forbidden_verify(*args, **kwargs):
        raise AssertionError("terminal response must not be verified or committed")

    monkeypatch.setattr(adapter, "verify_response", forbidden_verify)

    task = {
        "task_id": "terminal-race-task",
        "lease_id": "lease-1",
        "attempt_id": "attempt-1",
        "checkpoint_id": "checkpoint-1",
    }
    response = {
        "verdict": "PASS",
        "final_answer": "unchecked answer",
        "governance_decision": "UPHOLD",
        "confidence": 1.0,
        "run_id": "run-1",
        "trace_id": "trace-1",
    }

    result = await adapter.finalize(task, response, _Req())

    assert set(result) == {"task", "verification", "safe_response"}
    assert result["task"]["state"] == terminal_state
    assert result["verification"]["verdict"] == "TERMINAL_STATE"
    assert result["verification"]["failures"] == [f"task_terminal:{terminal_state}"]
    assert adapter.kernel.transition_calls == 0

    safe = _dump_response(result["safe_response"])
    assert safe["verdict"] == "FAIL"
    assert safe["governance_decision"] == "KILL"
    assert safe["run_status"] == "REJECTED"
    assert "Answer withheld" in safe["final_answer"]

    assert adapter.trace.entries
    trace = adapter.trace.entries[-1]
    assert trace["outcome"] == terminal_state
    assert trace["verdict"] == "TERMINAL_STATE"
    assert trace["reason"] == "task_terminal_before_verification"
