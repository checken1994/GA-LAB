import json
import time
import requests
import os

URL = "http://127.0.0.1:8002/ask"
GOLD_DATASET = r"c:\Users\check\Downloads\scp\benchmark\gold_anchor_1000_VERIFIED.jsonl"
OUTPUT_FILE = r"c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\real_exam_1000_runtime.jsonl"
FINAL_SCORE = r"c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\ragas_1000_score.json"

log_file = r"c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\exam_1000_progress.log"
def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

log("BẮT ĐẦU CHẠY THI 1000 CÂU RAG (KẾT NỐI API SCP LOCAL)...")

results = []
count = 0
with open(GOLD_DATASET, "r", encoding="utf-8") as f, open(OUTPUT_FILE, "w", encoding="utf-8") as out:
    for line in f:
        if not line.strip(): continue
        q = json.loads(line)
        question = q["question"]
        qid = q["question_id"]
        
        count += 1
        if count % 10 == 0: log(f"Đang thi tới câu {count}/1000...")
        
        try:
            resp = requests.post(URL, json={"question": question, "source": "real_exam_1000"}, timeout=60)
            data = resp.json()
            ai_answer = data.get("final_answer", "")
            
            res_obj = {
                "question_id": qid,
                "question": question,
                "gold_answer": q["gold_answer"],
                "gold_chunk_text": q["gold_chunk_text"],
                "ai_answer": ai_answer
            }
            out.write(json.dumps(res_obj, ensure_ascii=False) + "\n")
            out.flush()
        except Exception as e:
            log(f"Lỗi timeout ở câu {qid}, hệ thống bỏ qua.")

log("ĐÃ HOÀN THÀNH 1000 CÂU! GỌI RAGAS CHẤM ĐIỂM BẰNG OPENROUTER...")
os.system(f'python benchmark\\run_ragas_v2.py --runtime "{OUTPUT_FILE}" --gold "{GOLD_DATASET}" --output "{FINAL_SCORE}" >> "{log_file}" 2>&1')
log("TOÀN BỘ TIẾN TRÌNH THI VÀ CHẤM ĐIỂM ĐÃ KẾT THÚC.")
