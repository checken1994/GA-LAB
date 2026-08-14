from __future__ import annotations

import json
from pathlib import Path

from scp.autofix.classifier import BugReport, BugTier
from scp.autofix.deterministic_patches import build_candidate
from scp.autofix.deterministic_worker import DeterministicWorker, WorkerConfig


def _bug(path: Path, line: int, bug_type: str) -> BugReport:
    return BugReport(
        file=str(path),
        line=line,
        bug_type=bug_type,
        description=f"fixture {bug_type}",
        suggested_fix="",
        tier=BugTier.TIER_1_AUTO_FIX,
    )


def test_bare_except_ast_candidate_is_precise(tmp_path: Path):
    source = (
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "def f():\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:\n"
        "        pass\n"
    )
    path = tmp_path / "bare.py"
    path.write_text(source, encoding="utf-8")
    candidate = build_candidate(_bug(path, 6, "BareExceptPass"))
    assert candidate is not None
    assert candidate.patch_id == "bare_except_pass_ast_v1"
    assert "logger.debug" in candidate.source_after
    assert "except Exception as _scp_exc:" in candidate.source_after
    ok, reason = candidate.verify_after(candidate.source_after)
    assert ok, reason
    assert path.read_text(encoding="utf-8") == source


def test_sql_candidate_is_ast_bounded_and_rejects_identifier_interpolation(tmp_path: Path):
    path = tmp_path / "sql.py"
    path.write_text(
        'def f(cursor, user_id):\n    cursor.execute(f"SELECT * FROM users WHERE id={user_id}")\n',
        encoding="utf-8",
    )
    candidate = build_candidate(_bug(path, 2, "SQLInjection"))
    assert candidate is not None
    assert candidate.patch_id == "sql_parameterize_ast_v1"
    assert "WHERE id=?" in candidate.source_after
    assert "(user_id,)" in candidate.source_after

    path.write_text(
        'def f(cursor, table):\n    cursor.execute(f"SELECT * FROM {table} WHERE id=1")\n',
        encoding="utf-8",
    )
    assert build_candidate(_bug(path, 2, "SQLInjection")) is None


def test_worker_applies_low_risk_and_records_rollback(tmp_path: Path):
    source = (
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "def f():\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:\n"
        "        pass\n"
    )
    path = tmp_path / "bare.py"
    path.write_text(source, encoding="utf-8")
    config = WorkerConfig(
        data_dir=tmp_path / "runtime",
        allowed_root=tmp_path,
        max_jobs=1,
        max_retries=1,
        auto_apply_risk="low",
    )
    worker = DeterministicWorker(config)
    queued = worker.enqueue_bug(_bug(path, 6, "BareExceptPass"))
    result = worker.run_once()
    assert result["fixed"] == 1
    item = result["results"][0]
    assert item["llm_generated"] is False
    assert item["rollback_token"]
    assert "logger.debug" in path.read_text(encoding="utf-8")
    row = worker.ledger.get(queued["job_id"])
    assert row["state"] == "applied"
    events = worker.ledger.list_events(queued["job_id"])
    assert [event["to_state"] for event in events] == ["queued", "running", "applied"]
    audit_lines = (config.data_dir / "autofix_audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert audit_lines
    audit = json.loads(audit_lines[-1])
    for field in ("before_hash", "after_hash", "rollback_token", "reality_test_result"):
        assert audit[field]


def test_worker_does_not_auto_apply_medium_risk_by_default(tmp_path: Path):
    path = tmp_path / "sql.py"
    path.write_text(
        'def f(cursor, user_id):\n    cursor.execute(f"SELECT * FROM users WHERE id={user_id}")\n',
        encoding="utf-8",
    )
    config = WorkerConfig(data_dir=tmp_path / "runtime", allowed_root=tmp_path, max_jobs=1, auto_apply_risk="low")
    worker = DeterministicWorker(config)
    queued = worker.enqueue_bug(_bug(path, 2, "SQLInjection"))
    result = worker.run_once()
    assert result["candidate"] == 1
    assert path.read_text(encoding="utf-8").count("f\"SELECT") == 1
    assert worker.ledger.get(queued["job_id"])["state"] == "candidate"


def test_worker_rejects_stale_source_hash_without_writing(tmp_path: Path):
    path = tmp_path / "bare.py"
    path.write_text(
        "import logging\nlogger = logging.getLogger(__name__)\n"
        "def f():\n    try:\n        return 1\n    except Exception:\n        pass\n",
        encoding="utf-8",
    )
    config = WorkerConfig(data_dir=tmp_path / "runtime", allowed_root=tmp_path, max_jobs=1)
    worker = DeterministicWorker(config)
    queued = worker.enqueue_bug(_bug(path, 6, "BareExceptPass"))
    path.write_text(path.read_text(encoding="utf-8") + "\n# changed after enqueue\n", encoding="utf-8")
    result = worker.run_once()
    assert result["rejected"] == 1
    assert worker.ledger.get(queued["job_id"])["state"] == "rejected"
    assert "changed after enqueue" in path.read_text(encoding="utf-8")
