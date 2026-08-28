import json
from collections import Counter

file_path = r"c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\real_exam_1000_runtime.jsonl"
c = Counter()
total = 0

with open(file_path, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip(): continue
        total += 1
        data = json.loads(line)
        ans = data.get("ai_answer", "")
        
        if "Governance KILL" in ans:
            c["blocked_by_governance"] += 1
        elif "Tôi không có đủ dữ liệu" in ans or "ngoài phạm vi kiến thức" in ans:
            c["fail_closed_insufficient_data"] += 1
        elif ans.strip() == "":
            c["empty_response"] += 1
        else:
            c["answered"] += 1

print(f"Tổng số câu: {total}")
for k, v in c.items():
    print(f" - {k}: {v} ({v/total*100:.1f}%)")
