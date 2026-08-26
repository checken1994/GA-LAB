from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "benchmark" / "run_ragas_v2.py"

spec = importlib.util.spec_from_file_location("phase3_ragas_runner", RUNNER)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_admission_is_fail_closed_for_runtime_and_candidate_rows() -> None:
    runtime = [
        {"question_id": "Q-200", "http_status": 429, "response_json": {}},
        {"question_id": "Q-201", "http_status": 200, "response_json": {"final_answer": "answer"}, "evidence_observed": {"items": [{"value": "observed context with enough text"}]}},
    ]
    gold = {
        "Q-201": {
            "question_id": "Q-201",
            "review_status": "CANDIDATE_SOURCE_FETCH_VERIFIED",
            "eligible_for_ragas": False,
            "candidate_answer": "candidate",
        }
    }
    admitted, excluded = module.build_admission(runtime, gold)
    assert admitted == []
    assert excluded["runtime_http_not_200"] == 1
    assert excluded["gold_not_verified_or_not_eligible"] == 1


def test_verified_gate_requires_explicit_review_and_eligibility() -> None:
    runtime = [{
        "question_id": "Q-202",
        "http_status": 200,
        "response_json": {"final_answer": "answer"},
        "evidence_observed": {"items": [{"value": "observed context with enough text"}]},
    }]
    gold = {"Q-202": {"question_id": "Q-202", "review_status": "HUMAN_VERIFIED", "eligible_for_ragas": True, "reviewed_answer": "truth"}}
    admitted, excluded = module.build_admission(runtime, gold)
    assert len(admitted) == 1
    assert admitted[0]["ground_truth"] == "truth"
    assert excluded == {}
