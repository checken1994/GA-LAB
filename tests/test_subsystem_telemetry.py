from __future__ import annotations

import asyncio
import json
from pathlib import Path

from scp.core.subsystem_telemetry import (
    SubsystemTelemetry,
    classify_cycle_status,
    telemetry_async_cycle,
)


def test_heartbeat_and_ledger_record_completed_cycle(tmp_path: Path):
    telemetry = SubsystemTelemetry("fast_learning", tmp_path)
    telemetry.start(config={"mode": "test"})
    telemetry.tick(status="IDLE")
    telemetry.cycle_started("run-1", asked=2)
    telemetry.cycle_completed("run-1", "SUCCESS", asked=2, verified=1, stored=1)

    snapshot = telemetry.snapshot()
    assert snapshot["last_status"] == "SUCCESS"
    assert snapshot["cycles_started"] == 1
    assert snapshot["cycles_completed"] == 1
    rows = [json.loads(line) for line in (tmp_path / "fast_learning_runs.jsonl").read_text().splitlines()]
    assert [row["event_type"] for row in rows] == ["started", "cycle_started", "cycle_completed"]
    assert rows[-1]["run_id"] == "run-1"
    assert "prompt" not in rows[-1]


def test_status_classification_distinguishes_failure_states():
    assert classify_cycle_status({"asked": 0, "skipped_known": 2}) == "NO_NEW_FACTS"
    assert classify_cycle_status({"asked": 2, "provider_failed": 2, "verified": 0}) == "PROVIDER_FAILED"
    assert classify_cycle_status({"asked": 2, "verified": 0, "stored": 0}) == "VERIFY_REJECTED"
    assert classify_cycle_status({"bugs_found": 0, "bugs_fixed": 0, "stored": 0, "action": "skipped"}) == "DISABLED"


def test_evolution_disabled_is_explicit_and_audited(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SCP_EVOLUTION_ENABLED", raising=False)
    monkeypatch.delenv("SCP_EVOLUTION_AUTO", raising=False)
    monkeypatch.delenv("SCP_WHY_LLM_ENABLED", raising=False)
    from scp.autofix.evolution import EvolutionEngine

    engine = EvolutionEngine(data_dir=str(tmp_path))
    assert engine.stats().enabled is False
    result = engine.evolve_cycle(max_bugs=1)
    assert result["action"] == "skipped"
    assert engine._telemetry.snapshot()["last_status"] == "DISABLED"


def test_async_cycle_wrapper_writes_start_and_completion(tmp_path: Path):
    class Dummy:
        def __init__(self):
            self._telemetry = SubsystemTelemetry("dummy", tmp_path)
            self._telemetry.start(config={"mode": "test"})

        @telemetry_async_cycle
        async def cycle(self):
            return {"asked": 1, "verified": 1, "stored": 1}

    dummy = Dummy()
    result = asyncio.run(dummy.cycle())
    assert result["run_id"].startswith("dummy-")
    snapshot = dummy._telemetry.snapshot()
    assert snapshot["last_status"] == "SUCCESS"
    rows = [json.loads(line) for line in (tmp_path / "dummy_runs.jsonl").read_text().splitlines()]
    assert rows[-1]["event_type"] == "cycle_completed"
    assert rows[-1]["status"] == "SUCCESS"
