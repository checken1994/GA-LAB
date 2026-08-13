from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
for item in data.get("question_results", []):
    trace = item.get("slm_trace") or []
    trace_summary = []
    for record in trace:
        if isinstance(record, dict):
            trace_summary.append(
                {
                    "provider": record.get("provider"),
                    "answer": record.get("answer"),
                    "source": record.get("source"),
                    "evidence": record.get("evidence"),
                }
            )
    fields = {
        "id": item.get("id"),
        "category": item.get("category"),
        "expected": item.get("expected_answer"),
        "ai_answer": item.get("ai_answer"),
        "final_answer": item.get("final_answer"),
        "verdict": item.get("verdict"),
        "factual_match": item.get("factual_match"),
        "evidence_recall": item.get("evidence_recall"),
        "error": item.get("error"),
        "trace": trace_summary,
    }
    print(json.dumps(fields, ensure_ascii=True, separators=(",", ":")))
