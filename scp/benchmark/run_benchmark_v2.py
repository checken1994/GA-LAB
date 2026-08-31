#!/usr/bin/env python3
"""SCP Benchmark v2 compatibility wrapper.

The benchmark implementation is split into focused part modules while this
module preserves the historical public API and shared module namespace.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import requests

try:
    from scp.benchmark.question_generator import generate_random_questions, save_questions_to_jsonl
except ImportError:
    from question_generator import generate_random_questions, save_questions_to_jsonl

BENCHMARK_DIR = Path(__file__).parent
DEFAULT_URL = os.environ.get("SCP_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_TOKEN = os.environ.get("SCP_AUTH_TOKEN_SECRET", os.environ.get("SCP_AUTH_PASSWORD", ""))
QUESTION_CATEGORIES_V2 = {
    "math": "questions_v2/math_sample.jsonl",
    "geography": "questions_v2/geography_sample.jsonl",
    "ambiguous": "questions_v2/ambiguous_sample.jsonl",
}
ATTACK_CATEGORIES_V2 = {"dan": "attacks_v2/dan_sample.jsonl"}


def normalize_string(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\b(the|a|an|le|la|les|un|une|của|là|có)\b", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_number(s: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", s.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


from .run_benchmark_v2_parts import check_factual_correctness as _p_check_factual
from .run_benchmark_v2_parts import extract_claims_from_answer as _p_extract_claims
from .run_benchmark_v2_parts import classify_claim as _p_classify_claim
from .run_benchmark_v2_parts import compute_claim_hallucination as _p_claim_hallucination
from .run_benchmark_v2_parts import compute_evidence_metrics as _p_evidence
from .run_benchmark_v2_parts import compute_abstention_metrics as _p_abstention
from .run_benchmark_v2_parts import compute_correction_metrics as _p_correction
from .run_benchmark_v2_parts import classify_attack_result as _p_classify_attack
from .run_benchmark_v2_parts import compute_security_metrics as _p_security
from .run_benchmark_v2_parts import evaluate_questions_v2 as _p_eval_questions
from .run_benchmark_v2_parts import evaluate_attacks_v2 as _p_eval_attacks
from .run_benchmark_v2_parts import compute_all_metrics_v2 as _p_all_metrics
from .run_benchmark_v2_parts import main as _p_main

_PART_MODULES = (
    _p_check_factual,
    _p_extract_claims,
    _p_classify_claim,
    _p_claim_hallucination,
    _p_evidence,
    _p_abstention,
    _p_correction,
    _p_classify_attack,
    _p_security,
    _p_eval_questions,
    _p_eval_attacks,
    _p_all_metrics,
    _p_main,
)

# Seed every part with the shared namespace that historically lived in this
# module. A second pass below adds sibling public functions after binding.
_shared = {
    name: value
    for name, value in globals().items()
    if name not in {"_shared", "_PART_MODULES"}
}
for _part in _PART_MODULES:
    _part.__dict__.update(_shared)

check_factual_correctness = _p_check_factual.check_factual_correctness
extract_claims_from_answer = _p_extract_claims.extract_claims_from_answer
classify_claim = _p_classify_claim.classify_claim
compute_claim_hallucination = _p_claim_hallucination.compute_claim_hallucination
compute_evidence_metrics = _p_evidence.compute_evidence_metrics
compute_abstention_metrics = _p_abstention.compute_abstention_metrics
compute_correction_metrics = _p_correction.compute_correction_metrics
classify_attack_result = _p_classify_attack.classify_attack_result
compute_security_metrics = _p_security.compute_security_metrics
evaluate_questions_v2 = _p_eval_questions.evaluate_questions_v2
evaluate_attacks_v2 = _p_eval_attacks.evaluate_attacks_v2
compute_all_metrics_v2 = _p_all_metrics.compute_all_metrics_v2
main = _p_main.main

_public_namespace = dict(globals())
for _part in _PART_MODULES:
    _part.__dict__.update(_public_namespace)

__all__ = [
    "normalize_string",
    "extract_number",
    "check_factual_correctness",
    "extract_claims_from_answer",
    "classify_claim",
    "compute_claim_hallucination",
    "compute_evidence_metrics",
    "compute_abstention_metrics",
    "compute_correction_metrics",
    "classify_attack_result",
    "compute_security_metrics",
    "evaluate_questions_v2",
    "evaluate_attacks_v2",
    "compute_all_metrics_v2",
    "main",
]

if __name__ == "__main__":
    main()
