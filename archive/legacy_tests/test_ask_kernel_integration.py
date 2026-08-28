from __future__ import annotations

from types import SimpleNamespace

import pytest

from scp.ask_kernel_adapter import AskKernelAdapter


def make_request(
    question: str = "Berlin is the capital of Germany?",
    contexts: list[str] | None = None,
    retrieved_context: str = "Berlin is the capital city of Germany.",
    session_id: str | None = "integration-session",
    rag_enabled: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        question=question,
        contexts=contexts or [],
        retrieved_context=retrieved_context,
        session_id=session_id,
        rag_enabled=rag_enabled,
        domain_override="history",
        domain="history",
    )


def make_response(answer: str = "Berlin is the capital city of Germany.") -> dict[str, object]:
    return {
        "verdict": "PASS",
        "final_answer": answer,
        "confidence": 0.99,
        "domain": "history",
        "governance_decision": "UPHOLD",
        "v98_classification": {"provenance": "input_context_only", "evidence_count": 1},
        "web_fallback_used": False,
        "run_id": "run-test",
        "trace_id": "trace-test",
        "elapsed_ms": 1.0,
    }


@pytest.mark.asyncio
async def test_retrieved_context_only_completes_with_kernel_evidence(tmp_path):
    adapter = AskKernelAdapter(str(tmp_path / "kernel.sqlite3"), str(tmp_path / "trace.jsonl"))
    req = make_request(contexts=[], retrieved_context="Berlin is the capital city of Germany.")
    calls = 0

    async def handler(_req, _request):
        nonlocal calls
        calls += 1
        return make_response()

    result = await adapter.run_rag(req, None, handler)
    assert calls == 1
    assert result["verdict"] == "PASS"
    task_id = next(iter(adapter.kernel.conn.execute("SELECT task_id FROM tasks")))["task_id"]
    assert adapter.kernel.get_task(task_id)["state"] == "COMPLETED"
    assert adapter.kernel.verify_journal(task_id)["hash_chain_valid"] is True
    checkpoint = next(iter(adapter.kernel.conn.execute("SELECT * FROM checkpoints")))
    assert checkpoint["state"] == "RUNNING"
    assert adapter.trace.verify()["hash_chain_valid"] is True
    adapter.kernel.close()


@pytest.mark.asyncio
async def test_missing_context_withholds_and_moves_to_human_review(tmp_path):
    adapter = AskKernelAdapter(str(tmp_path / "kernel.sqlite3"), str(tmp_path / "trace.jsonl"))
    req = make_request(question="What is an unsupported fact?", contexts=[], retrieved_context="")

    async def handler(_req, _request):
        return make_response("An answer without supplied evidence.")

    result = await adapter.run_rag(req, None, handler)
    assert result["verdict"] == "FAIL"
    assert "withheld" in result["final_answer"].lower()
    task_id = next(iter(adapter.kernel.conn.execute("SELECT task_id FROM tasks")))["task_id"]
    assert adapter.kernel.get_task(task_id)["state"] == "HUMAN_REVIEW"
    adapter.kernel.close()


@pytest.mark.asyncio
async def test_global_kill_blocks_handler_and_cancels_task(tmp_path):
    adapter = AskKernelAdapter(str(tmp_path / "kernel.sqlite3"), str(tmp_path / "trace.jsonl"))
    adapter.kernel.set_global_kill(True, actor="integration-test")
    calls = 0

    async def handler(_req, _request):
        nonlocal calls
        calls += 1
        return make_response()

    result = await adapter.run_rag(make_request(question="kill test"), None, handler)
    assert calls == 0
    assert result.verdict == "FAIL"
    assert result.governance_decision == "KILL"
    task_state = next(iter(adapter.kernel.conn.execute("SELECT state FROM tasks")))["state"]
    assert task_state == "CANCELLED"
    assert adapter.trace.verify()["hash_chain_valid"] is True
    adapter.kernel.close()


@pytest.mark.asyncio
async def test_stable_retry_does_not_execute_handler_twice(tmp_path):
    adapter = AskKernelAdapter(str(tmp_path / "kernel.sqlite3"), str(tmp_path / "trace.jsonl"))
    req = make_request(question="stable retry", session_id="retry-session")
    calls = 0

    async def handler(_req, _request):
        nonlocal calls
        calls += 1
        return make_response()

    first = await adapter.run_rag(req, None, handler)
    second = await adapter.run_rag(req, None, handler)
    assert calls == 1
    assert first["verdict"] == "PASS"
    assert second.verdict == "FAIL"
    assert second.governance_decision == "KILL"
    states = list(adapter.kernel.conn.execute("SELECT state FROM tasks"))
    assert len(states) == 1 and states[0]["state"] == "COMPLETED"
    assert adapter.trace.verify()["hash_chain_valid"] is True
    adapter.kernel.close()


@pytest.mark.asyncio
async def test_handler_crash_is_failed_and_trace_remains_valid(tmp_path):
    adapter = AskKernelAdapter(str(tmp_path / "kernel.sqlite3"), str(tmp_path / "trace.jsonl"))

    async def crash(_req, _request):
        raise RuntimeError("simulated_handler_crash")

    with pytest.raises(RuntimeError, match="simulated_handler_crash"):
        await adapter.run_rag(make_request(question="crash test"), None, crash)
    task_state = next(iter(adapter.kernel.conn.execute("SELECT state FROM tasks")))["state"]
    assert task_state == "FAILED"
    assert adapter.trace.verify()["hash_chain_valid"] is True
    adapter.kernel.close()


def test_route_wrapper_has_real_kernel_branch():
    """A small source-level guard complements runtime tests: /ask must call adapter."""
    from scp import api_server

    source = api_server.ask.__wrapped__.__code__.co_names
    assert "_ask_kernel_enabled" in source
    assert "_get_ask_kernel_adapter" in source
    assert "run_rag" in source
