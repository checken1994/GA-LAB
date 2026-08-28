import json
import time
import requests
import os

URL = "http://127.0.0.1:8002/ask"
GOLD_DATASET = r"c:\Users\check\Downloads\scp\benchmark\gold_anchor_1000_VERIFIED.jsonl"
OUTPUT_FILE = r"c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\real_exam_1000_runtime.jsonl"
log_file = r"c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\exam_1000_progress.log"

def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

log("BẮT ĐẦU CHẠY LẠI THI 1000 CÂU RAG (ĐÃ FIX LỖI KEYERROR)...")

count = 0
with open(GOLD_DATASET, "r", encoding="utf-8") as f, open(OUTPUT_FILE, "w", encoding="utf-8") as out:
    for line in f:
        if not line.strip(): continue
        q = json.loads(line)
        question = q.get("question", "")
        qid = q.get("question_id", "UNKNOWN")
        
        count += 1
        if count % 10 == 0: log(f"Đang thi tới câu {count}/1000...")
        
        try:
            resp = requests.post(URL, json={"question": question, "source": "real_exam_1000"}, timeout=60)
            ai_answer = resp.json().get("final_answer", "")
            
            res_obj = {
                "question_id": qid,
                "question": question,
                "gold_answer": q.get("gold_answer", ""),
                # FIX LỖI Ở ĐÂY: Dùng .get() để tránh sập nếu không có nhãn này
                "gold_chunk_text": q.get("gold_chunk_text", q.get("evidence", "")),
                "ai_answer": ai_answer
            }
            out.write(json.dumps(res_obj, ensure_ascii=False) + "\n")
            out.flush()
        except Exception as e:
            log(f"Lỗi timeout/server ở câu {qid}")

log("ĐÃ HOÀN THÀNH 1000 CÂU!")
