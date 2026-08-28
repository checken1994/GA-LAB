from __future__ import annotations

import asyncio
import json

from scp.core.learning_run_ledger import ledger_run


def test_fast_reject_is_recorded(tmp_path, monkeypatch):
    path = tmp_path / "learning_runs.jsonl"
    monkeypatch.setenv("SCP_LEARNING_RUN_LEDGER_PATH", str(path))

    @ledger_run("fast")
    async def run():
        return {"asked": 1, "verified": 0, "stored": 0, "skipped_known": 0}

    asyncio.run(run())
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["status"] == "VERIFY_REJECTED"
    assert row["asked"] == 1
    assert row["answered"] == 1
    assert row["rejected"] == 1
    assert row["stored"] == 0
    assert row["error_class"] is None


def test_evolution_skip_is_recorded(tmp_path, monkeypatch):
    path = tmp_path / "learning_runs.jsonl"
    monkeypatch.setenv("SCP_LEARNING_RUN_LEDGER_PATH", str(path))

    @ledger_run("evolution")
    def run():
        return {"action": "skipped", "reason": "evolution disabled"}

    run()
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["status"] == "NO_NEW_FACTS"
    assert row["mode"] == "evolution"


def test_provider_exception_is_recorded_and_reraised(tmp_path, monkeypatch):
    path = tmp_path / "learning_runs.jsonl"
    monkeypatch.setenv("SCP_LEARNING_RUN_LEDGER_PATH", str(path))

    @ledger_run("fast")
    def run():
        raise ConnectionError("provider unavailable")

    try:
        run()
    except ConnectionError:
        pass
    else:
        raise AssertionError("decorator must preserve provider exception")
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["status"] == "PROVIDER_FAILED"
    assert row["error_class"] == "ConnectionError"
    assert "provider unavailable" in row["error_summary"]
