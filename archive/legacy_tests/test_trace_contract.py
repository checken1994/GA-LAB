from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scp.core.request_run_ledger import RequestRunLedger, traced_request
from scp.core.trace_contract import redact_attributes, stable_hash


def read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_trace_span_parent_child_terminal_events_and_redaction(tmp_path: Path) -> None:
    ledger = RequestRunLedger(tmp_path / "runs.jsonl")
    run = ledger.begin(SimpleNamespace(source="test", domain="general", question="private question"))

    root = ledger.trace_contract.start(
        trace_id=run.trace_id,
        name="test.request",
        kind="workflow",
        attributes={"component": "test", "api_key": "must-not-leak"},
        input_value="private question",
    )
    child = ledger.trace_contract.start(
        trace_id=run.trace_id,
        name="test.tool",
        kind="tool",
        parent_id=root.span_id,
        attributes={"authorization": "Bearer secret-value", "attempt": 1},
        input_value={"question": "private question"},
    )
    ledger.trace_contract.finish(child, status="OK", output_value={"answer": "private answer"})
    ledger.trace_contract.finish(root, status="OK", output_value={"status": "SUCCESS"})

    events = read_events(tmp_path / "runs.jsonl")
    spans = [event for event in events if event["event"] in {"span_started", "span_finished"}]
    assert [event["event"] for event in spans] == [
        "span_started",
        "span_started",
        "span_finished",
        "span_finished",
    ]
    started_root, started_child, finished_child, finished_root = spans
    assert started_root["trace_id"] == run.trace_id
    assert started_child["parent_id"] == started_root["span_id"]
    assert finished_child["span_id"] == started_child["span_id"]
    assert finished_root["span_id"] == started_root["span_id"]
    assert finished_child["status"] == "OK"
    assert finished_root["duration_ms"] >= 0
    assert ledger.trace_contract.active_span_ids() == []
    serialized = (tmp_path / "runs.jsonl").read_text(encoding="utf-8")
    assert "must-not-leak" not in serialized
    assert "secret-value" not in serialized
    assert "private question" not in serialized
    assert "private answer" not in serialized
    assert stable_hash("same") == stable_hash("same")
    assert stable_hash("same") != "same"
    assert redact_attributes({"nested": {"password": "hidden"}})["nested"]["password"] == "[REDACTED]"


def test_stage_is_recorded_as_child_span_when_root_is_active(tmp_path: Path) -> None:
    ledger = RequestRunLedger(tmp_path / "runs.jsonl")
    run = ledger.begin(SimpleNamespace(source="test", domain="general", question="q"))
    root = ledger.trace_contract.start(trace_id=run.trace_id, name="root", kind="workflow")
    assert ledger.stage(run, "policy_check", "AUDIT_READY", decision_source="test") is True
    ledger.trace_contract.finish(root, status="OK")
    events = read_events(tmp_path / "runs.jsonl")
    stage_start = next(event for event in events if event["event"] == "span_started" and event["span_name"] == "policy_check")
    assert stage_start["parent_id"] == root.span_id
    assert not ledger.trace_contract.active_span_ids()


def test_invalid_span_status_becomes_error_and_double_finish_is_rejected(tmp_path: Path) -> None:
    ledger = RequestRunLedger(tmp_path / "runs.jsonl")
    span = ledger.trace_contract.start(trace_id="trace-test", name="invalid-status")
    event = ledger.trace_contract.finish(span, status="NOT_A_STATUS")
    assert event["status"] == "ERROR"
    with pytest.raises(RuntimeError, match="span is not active"):
        ledger.trace_contract.finish(span, status="OK")


def test_traced_request_emits_span_and_preserves_success_result(tmp_path: Path) -> None:
    ledger = RequestRunLedger(tmp_path / "runs.jsonl")
    request = SimpleNamespace(state=SimpleNamespace())

    @traced_request(ledger)
    async def handler(req, request):
        return {"ok": True, "payload": "bounded"}

    result = asyncio.run(handler(req=SimpleNamespace(source="test", domain="general", question="q"), request=request))
    assert result["run_status"] == "SUCCESS"
    assert result["ledger_status"] == "OK"
    assert request.state.scp_run.trace_id == result["trace_id"]
    events = read_events(tmp_path / "runs.jsonl")
    names = [event["event"] for event in events]
    assert "request_received" in names
    assert "request_finished" in names
    assert names.count("span_started") == 1
    assert names.count("span_finished") == 1
    span_finished = next(event for event in events if event["event"] == "span_finished")
    assert span_finished["status"] == "OK"
    assert span_finished["trace_id"] == result["trace_id"]
