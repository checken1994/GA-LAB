import json

in_file = r"c:\Users\check\Downloads\scp\benchmark\gold_anchor_1000_VERIFIED.jsonl"
out_gold = r"c:\Users\check\Downloads\scp\benchmark\gold_anchor_5_QUICK.jsonl"

print("Đang trích xuất 5 câu hỏi...")
count = 0
with open(in_file, "r", encoding="utf-8") as fin, open(out_gold, "w", encoding="utf-8") as fout:
    for line in fin:
        if not line.strip(): continue
        data = json.loads(line)
        # Đóng con dấu cuối cùng mà RAGAS đòi hỏi
        data["eligible_for_ragas"] = True
        fout.write(json.dumps(data, ensure_ascii=False) + "\n")
        count += 1
        if count >= 5: break
print("Đã tạo bộ đề 5 câu thành công.")
