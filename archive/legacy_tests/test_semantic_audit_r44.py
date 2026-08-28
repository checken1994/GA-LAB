from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.history.r44_semantic_audit import main


def test_semantic_audit_rejects_metadata_only_lesson(tmp_path: Path):
    db = tmp_path / "kb_evolve.sqlite"
    connection = sqlite3.connect(db)
    connection.execute(
        "CREATE TABLE lessons (lesson_id TEXT, bug_type TEXT, bug_file TEXT, bug_line INTEGER, fix_verified INTEGER, success_rate REAL)"
    )
    source = tmp_path / "typed.py"
    source.write_text("def f():\n    try:\n        return 1\n    except Exception:\n        pass\n", encoding="utf-8")
    connection.execute("INSERT INTO lessons VALUES (?, ?, ?, ?, ?, ?)", ("L1", "BareExceptPass", str(source), 4, 1, 1.0))
    connection.commit()
    connection.close()
    output = tmp_path / "audit.json"
    assert main(["--db", str(db), "--output", str(output)]) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["lesson_count"] == 1
    assert result["verified_record_count"] == 1
    assert result["promotion_allowed_count"] == 0
    assert result["classification_mismatch_count"] == 1
    assert result["missing_snapshot_count"] == 1
    assert result["missing_external_evidence_count"] == 1
    assert result["policy_promotion"] is False
