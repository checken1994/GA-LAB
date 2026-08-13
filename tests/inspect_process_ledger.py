from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

LEDGER = Path(r"C:\Users\check\Downloads\scp\data\hands\processes.jsonl")
records = []
invalid = []
if LEDGER.exists():
    for number, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            invalid.append((number, str(exc)))

print(f"exists={LEDGER.exists()}")
print(f"validLines={len(records)}")
print(f"invalidLines={len(invalid)}")
counts = Counter(record.get("event", "") for record in records)
for event in sorted(counts):
    print(f"count:{event}={counts[event]}")
for record in records[-12:]:
    print("record=" + "|".join(str(record.get(key, "")) for key in ("event", "pid", "commandId", "owned", "stopped", "returnCode", "error")))
