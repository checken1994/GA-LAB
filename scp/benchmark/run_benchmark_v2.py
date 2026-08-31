from .run_benchmark_v2_parts.check_factual_correctness import check_factual_correctness
from .run_benchmark_v2_parts.extract_claims_from_answer import extract_claims_from_answer
from .run_benchmark_v2_parts.classify_claim import classify_claim
from .run_benchmark_v2_parts.compute_claim_hallucination import compute_claim_hallucination
from .run_benchmark_v2_parts.compute_evidence_metrics import compute_evidence_metrics
from .run_benchmark_v2_parts.compute_abstention_metrics import compute_abstention_metrics
from .run_benchmark_v2_parts.compute_correction_metrics import compute_correction_metrics
from .run_benchmark_v2_parts.classify_attack_result import classify_attack_result
from .run_benchmark_v2_parts.compute_security_metrics import compute_security_metrics
from .run_benchmark_v2_parts.evaluate_questions_v2 import evaluate_questions_v2
from .run_benchmark_v2_parts.evaluate_attacks_v2 import evaluate_attacks_v2
from .run_benchmark_v2_parts.compute_all_metrics_v2 import compute_all_metrics_v2
from .run_benchmark_v2_parts.main import main

"""SCP Benchmark v2 — Proper anti-hallucination evaluator.

Fixes all methodology issues identified in v1:
  A. Factual correctness: normalized + structured match (no substring)
  B. Claim-level hallucination: SUPPORTED/CONTRADICTED/UNSUPPORTED (not Claim= Evidence)
  C. Evidence grounding: entailment check (not keyword overlap)
  D. Evidence Recall: retrieved / gold_evidence (not coverage)
  E. Abstention: gold answerable=True/False (not circular confidence)
  F. Self-correction: inject corrupted_answer (not empty ai_answer)
  G. Security: BLOCKED/BYPASSED/ERROR/TIMEOUT (not HTTP error = blocked)

Usage:
    python run_benchmark_v2.py --url http://127.0.0.1:8000 --token XXX --output results_v2/scp_results.json
    python run_benchmark_v2.py --full --output results_v2/scp_results.json
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
import statistics
from pathlib import Path
from typing import Any
import requests
try:
    from scp.benchmark.question_generator import generate_random_questions, save_questions_to_jsonl
except ImportError:
    from question_generator import generate_random_questions, save_questions_to_jsonl
BENCHMARK_DIR = Path(__file__).parent
DEFAULT_URL = os.environ.get('SCP_BASE_URL', 'http://127.0.0.1:8000')
DEFAULT_TOKEN = os.environ.get('SCP_AUTH_TOKEN_SECRET', os.environ.get('SCP_AUTH_PASSWORD', ''))
QUESTION_CATEGORIES_V2 = {'math': 'questions_v2/math_sample.jsonl', 'geography': 'questions_v2/geography_sample.jsonl', 'ambiguous': 'questions_v2/ambiguous_sample.jsonl'}
ATTACK_CATEGORIES_V2 = {'dan': 'attacks_v2/dan_sample.jsonl'}

def normalize_string(s: str) -> str:
    """Normalize string for comparison: lowercase, strip articles, remove punctuation."""
    s = s.lower().strip()
    s = re.sub('\\b(the|a|an|le|la|les|un|une|của|là|có)\\b', ' ', s)
    s = re.sub('[^\\w\\s]', ' ', s)
    s = re.sub('\\s+', ' ', s).strip()
    return s

def extract_number(s: str) -> float | None:
    """Extract first numeric value from string. Returns None if no number found."""
    m = re.search('-?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?', s.replace(',', ''))
    if m:
        try:
            return float(m.group())
        except ValueError:
            return None
    return None
if __name__ == '__main__':
    main()
