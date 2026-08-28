import json
import time
import requests

URL = "http://127.0.0.1:8002/ask"
GOLD_DATASET = "benchmark/gold_anchor_50_v1.jsonl"
OUTPUT_FILE = "data/archives/benchmarks_202608/real_exam_runtime.jsonl"

print("BẮT ĐẦU KỲ THI THỰC TẾ (REAL RAG BENCHMARK)...")

results = []
with open(GOLD_DATASET, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip(): continue
        q = json.loads(line)
        question = q["question"]
        qid = q["question_id"]
        
        print(f"Đang thi câu {qid}...")
        try:
            resp = requests.post(URL, json={"question": question, "source": "real_exam"}, timeout=45)
            data = resp.json()
            ai_answer = data.get("final_answer", "")
            
            # Lưu lại định dạng theo chuẩn của RAGAS v2 script
            res_obj = {
                "question_id": qid,
                "question": question,
                "gold_answer": q["gold_answer"],
                "gold_chunk_text": q["gold_chunk_text"],
                "ai_answer": ai_answer
            }
            results.append(res_obj)
        except Exception as e:
            print(f"Lỗi ở câu {qid}: {e}")
            
with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
    for r in results:
        out.write(json.dumps(r, ensure_ascii=False) + "\n")
        
print("Đã hoàn thành thi! Đang chuyển cho công cụ RAGAS chấm điểm...")
