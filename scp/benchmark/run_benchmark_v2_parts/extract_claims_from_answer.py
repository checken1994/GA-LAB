# Auto-extracted from run_benchmark_v2.py
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

def extract_claims_from_answer(answer: str, question: str='') -> list[dict]:
    """Extract factual claims from answer.

    Uses SCP's ClaimExtractor if available, else simple heuristic.
    """
    try:
        sys.path.insert(0, str(BENCHMARK_DIR.parent))
        from scp.knowledge.claim_extractor import ClaimExtractor
        extractor = ClaimExtractor()
        claims = extractor.extract(answer, question)
        return [{'claim_id': c.claim_id, 'claim_type': c.claim_type, 'text': c.text, 'entity': c.entity, 'value': c.value, 'unit': c.unit, 'relation': c.relation, 'target': c.target} for c in claims]
    except Exception:
        sentences = re.split('[.!?]+', answer)
        return [{'claim_id': f'claim_{i}', 'claim_type': 'sentence', 'text': s.strip()} for i, s in enumerate(sentences) if s.strip() and len(s.strip()) > 10]
