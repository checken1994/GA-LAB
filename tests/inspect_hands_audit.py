from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

AUDIT = Path(str(Path(__file__).resolve().parent / "data" / "hands" / "audit.jsonl"))

valid = []
invalid = []
if AUDIT.exists():
    for number, line in enumerate(AUDIT.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            valid.append(json.loads(line))
        except json.JSONDecodeError as exc:
            invalid.append((number, str(exc), line[:160]))

print(f"exists={AUDIT.exists()}")
print(f"validLines={len(valid)}")
print(f"invalidLines={len(invalid)}")
counts = Counter(item.get("event", "") for item in valid)
for event in sorted(counts):
    print(f"count:{event}={counts[event]}")
for item in valid[-14:]:
    print("record=" + "|".join(str(item.get(key, "")) for key in ("iso", "event", "action", "success", "checkpointId", "target")))
for number, error, prefix in invalid[-5:]:
    print("invalid=" + json.dumps({"line": number, "error": error, "prefix": prefix}, ensure_ascii=True, separators=(",", ":")))
