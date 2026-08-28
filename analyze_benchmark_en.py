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
            c["Blocked_by_Governance"] += 1
        elif "kh" in ans and ("ng c" in ans or "ngo" in ans): # rough match for "không có đủ dữ liệu"
            c["Fail_Closed_No_Data"] += 1
        elif ans.strip() == "":
            c["Empty_Response"] += 1
        else:
            c["Answered"] += 1

print(f"Total: {total}")
for k, v in c.items():
    print(f" - {k}: {v} ({v/total*100:.1f}%)")
