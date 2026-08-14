from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scp.history import HistoryMigration


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_sqlite_scan_is_telemetry_only_and_does_not_mutate(tmp_path: Path):
    db = tmp_path / "v13.db"
    connection = sqlite3.connect(db)
    connection.execute("create table question_events (id integer)")
    connection.execute("insert into question_events values (1)")
    connection.commit()
    connection.close()
    before = db.read_bytes()

    migration = HistoryMigration()
    counts = migration.scan_sqlite(db)

    assert counts == {"question_events": 1}
    assert db.read_bytes() == before
    assert migration.artifacts[0].disposition == "telemetry_only"
    assert migration.manifest()["mutating"] is False


def test_learning_runs_are_operational_reliability_only(tmp_path: Path):
    path = tmp_path / "learning_runs.jsonl"
    _write_jsonl(path, [{"status": "TIMEOUT"}, {"status": "SUCCESS", "stored": 1}])

    migration = HistoryMigration()
    summary = migration.scan_jsonl(path)

    assert summary["rows"] == 2
    assert summary["states"]["status=TIMEOUT"] == 1
    assert migration.artifacts[0].disposition == "operational_reliability_only"


def test_static_knowledge_is_reference_only(tmp_path: Path):
    path = tmp_path / "v3_knowledge.json"
    path.write_text(json.dumps({"math": {"pi": "3.14"}}), encoding="utf-8")

    migration = HistoryMigration()
    summary = migration.scan_static_knowledge(path)

    assert summary == {"domains": 1, "facts": 1, "disposition": "reference_only"}
    assert migration.artifacts[0].evidence_level == "L1"


def test_reality_results_with_null_rows_are_quarantined(tmp_path: Path):
    path = tmp_path / "reality-results.json"
    path.write_text(json.dumps({"results": [{"pass": None}, {"pass": None}]}), encoding="utf-8")

    migration = HistoryMigration()
    summary = migration.scan_reality_results(path)

    assert summary["valid_row_contract"] is False
    assert migration.artifacts[0].disposition == "contract_invalid_quarantine"


def test_verified_evolution_lesson_is_candidate_not_policy(tmp_path: Path):
    path = tmp_path / "kb_evolve.sqlite"
    connection = sqlite3.connect(path)
    connection.execute(
        "create table lessons (lesson_id text, bug_type text, bug_file text, bug_line integer, "
        "fix_verified integer, occurrence_count integer, success_rate real)"
    )
    connection.execute("create table evolved_patterns (pattern_id text, bug_type text, source_lesson_id text, occurrence_count integer, false_positive_count integer, confidence real)")
    connection.execute("insert into lessons values ('l1','BareExceptPass','x.py',1,1,1,1.0)")
    connection.execute("insert into evolved_patterns values ('p1','BareExceptPass','l1',0,0,0.5)")
    connection.commit()
    connection.close()

    migration = HistoryMigration()
    result = migration.scan_evolution_db(path)

    assert len(result["verified_lesson_candidates"]) == 1
    assert result["verified_lesson_candidates"][0]["disposition"] == "candidate_only"
    assert len(result["patterns_quarantined"]) == 1
    assert migration.manifest()["policy_promotion"] is False
