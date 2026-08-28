from __future__ import annotations

import json
from pathlib import Path

from scripts.history.r44_bare_except_ab import run


def test_ab_harness_matches_independent_detector_and_compiles_candidate(tmp_path: Path):
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "sample.py").write_text(
        "def f():\n    try:\n        return 1\n    except:\n        pass\n",
        encoding="utf-8",
    )
    result = run(source_root, 10, tmp_path / "cache.json")
    assert result["files_total"] == 1
    assert result["baseline_findings"] == 1
    assert result["candidate_findings"] == 1
    assert result["compile_pass"] == 1
    assert result["compile_fail"] == 0
    assert result["ground_truth_available"] is False
    assert result["policy_promotion"] is False


def test_ab_harness_has_no_false_truth_label(tmp_path: Path):
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "clean.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    result = run(source_root, 10, tmp_path / "cache.json")
    assert result["baseline_findings"] == 0
    assert result["candidate_findings"] == 0
    assert result["independent_true_positive_evidence"] == 0
    assert result["independent_false_positive_evidence"] == 0
    json.dumps(result)
