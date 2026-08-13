from __future__ import annotations

import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
data = json.loads(p.read_text(encoding="utf-8"))
items = data.get("question_results", [])
for item in items:
    trace = item.get("slm_trace") or []
    evidence = sum(1 for record in trace if isinstance(record, dict) and record.get("evidence"))
    print(
        "|".join(
            [
                str(item.get("category")),
                str(item.get("id")),
                f"expected={bool(item.get('expected_answer'))}",
                f"ai={bool(item.get('ai_answer'))}:{len(item.get('ai_answer') or '')}",
                f"final={bool(item.get('final_answer'))}:{len(item.get('final_answer') or '')}",
                f"trace={len(trace)}",
                f"traceEvidence={evidence}",
                f"verdict={item.get('verdict')}",
                f"error={bool(item.get('error'))}",
            ]
        )
    )
metrics = data.get("metrics", {})
print(
    "METRICS|"
    + "|".join(
        [
            f"accuracy={metrics.get('A_factual_accuracy', {}).get('value')}",
            f"evidence={metrics.get('D_evidence_recall', {}).get('value')}",
            f"hallucination={metrics.get('B_claim_hallucination', {}).get('hallucination_rate')}",
        ]
    )
)
