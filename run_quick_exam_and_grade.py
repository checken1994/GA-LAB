import json
import requests
import os

URL = "http://127.0.0.1:8002/ask"
GOLD = r"c:\Users\check\Downloads\scp\benchmark\gold_anchor_5_QUICK.jsonl"
RUNTIME = r"c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\real_exam_5_runtime.jsonl"
SCORE = r"c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\ragas_5_score.json"

print(">> BẮT ĐẦU CHO AI LÀM BÀI (5 CÂU)...")
with open(GOLD, "r", encoding="utf-8") as fin, open(RUNTIME, "w", encoding="utf-8") as fout:
    for line in fin:
        if not line.strip(): continue
        q = json.loads(line)
        print(f"Đang hỏi: {q['question']}")
        
        try:
            resp = requests.post(URL, json={"question": q["question"], "source": "quick_exam"}, timeout=30)
            ai_ans = resp.json().get("final_answer", "")
            
            res_obj = {
                "question_id": q["question_id"],
                "question": q["question"],
                "gold_answer": q["gold_answer"],
                "gold_chunk_text": q["gold_chunk_text"],
                "ai_answer": ai_ans
            }
            fout.write(json.dumps(res_obj, ensure_ascii=False) + "\n")
            print(" -> OK")
        except Exception as e:
            print(f" -> LỖI: {e}")

print(">> ĐÃ LÀM XONG. CHUẨN BỊ GỌI RAGAS CHẤM ĐIỂM...")
