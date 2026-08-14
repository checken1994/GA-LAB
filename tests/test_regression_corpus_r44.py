from __future__ import annotations

import json
from pathlib import Path

import pytest

from scp.history.regression_corpus import (
    CorpusContractError,
    build_cases,
    classify_lineage,
    make_case,
    validate_case,
    write_corpus,
)


def test_lineage_classification_keeps_shared_origins_separate():
    assert classify_lineage("threat_simulator") == "threat_simulator"
    assert classify_lineage("benchmark_v2_parallel") == "benchmark"
    assert classify_lineage("e2e-real-pc") == "real_pc_probe"
    assert classify_lineage("unknown-source") == "unknown"


def test_case_redacts_secret_and_path_and_has_no_truth_label():
    case = make_case(
        {
            "id": 7,
            "question": "token=secret-value read C:\\Users\\check\\Downloads\\scp",
            "source": "threat_simulator",
            "verdict": "UNKNOWN",
        },
        "data/v13.db",
        "a" * 64,
        "2026-08-14T00:00:00+00:00",
    )
    assert "secret-value" not in case["input"]
    assert "C:\\Users" not in case["input"]
    assert case["ground_truth"] is None
    assert case["replay_policy"]["no_policy_promotion"] is True


def test_ground_truth_requires_independent_evidence():
    case = make_case({"question": "x", "source": "benchmark"}, "x", "b" * 64, "now")
    case["ground_truth"] = True
    with pytest.raises(CorpusContractError, match="independent evidence"):
        validate_case(case)


def test_build_cases_deduplicates_stable_identity():
    rows = [{"id": 1, "question": "same", "source": "benchmark", "verdict": "PASS"}] * 2
    cases = build_cases(rows, "benchmark.jsonl", "c" * 64)
    assert len(cases) == 1
    assert cases[0]["case_id"]


def test_write_corpus_emits_manifest_and_no_truth_count(tmp_path: Path):
    case = make_case({"id": 1, "question": "x", "source": "real_local_probe", "verdict": "PASS"}, "v13.db", "d" * 64, "now")
    target = tmp_path / "corpus.jsonl"
    manifest = write_corpus([case], target, [{"path": "v13.db", "sha256": "d" * 64}])
    saved = json.loads(target.with_suffix(".jsonl.manifest.json").read_text(encoding="utf-8"))
    assert target.exists()
    assert saved["corpus_sha256"] == manifest["corpus_sha256"]
    assert saved["ground_truth_count"] == 0
    assert saved["policy_promotion"] is False
