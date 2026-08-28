import json
import requests
import os
import subprocess

# 1. Ép AI làm bài thi 5 câu (Nếu chưa làm)
URL = "http://127.0.0.1:8002/ask"
GOLD = r"c:\Users\check\Downloads\scp\benchmark\gold_anchor_5_QUICK.jsonl"
RUNTIME = r"c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\real_exam_5_runtime.jsonl"
SCORE = r"c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\ragas_5_score.json"

print(">> KIỂM TRA BÀI LÀM CỦA AI...")
with open(GOLD, "r", encoding="utf-8") as fin, open(RUNTIME, "w", encoding="utf-8") as fout:
    for line in fin:
        if not line.strip(): continue
        q = json.loads(line)
        try:
            resp = requests.post(URL, json={"question": q["question"], "source": "quick_exam"}, timeout=30)
            ai_ans = resp.json().get("final_answer", "")
            if ai_ans:
                print(f"Câu hỏi: {q['question'][:30]}... -> OK (Có đáp án)")
            res_obj = {
                "question_id": q["question_id"],
                "question": q["question"],
                "gold_answer": q["gold_answer"],
                "gold_chunk_text": q["gold_chunk_text"],
                "ai_answer": ai_ans
            }
            fout.write(json.dumps(res_obj, ensure_ascii=False) + "\n")
        except:
            print(f"Câu hỏi: {q['question'][:30]}... -> LỖI Timeout")

print("\n>> GỌI RAGAS CHẤM ĐIỂM (ÉP NHẬN DIỆN KEY)...")
# Lấy Key từ dòng cuối cùng của file .env
env_lines = open(r"c:\Users\check\Downloads\scp\.env", "r").readlines()
openrouter_key = ""
for line in env_lines:
    if line.startswith("OPENAI_API_KEY="):
        openrouter_key = line.split("=")[1].strip()

# Khởi tạo môi trường ảo với chỉ ĐÚNG 2 biến để tránh nhiễu
env_vars = os.environ.copy()
env_vars["OPENAI_API_KEY"] = openrouter_key
env_vars["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
env_vars["PYTHONIOENCODING"] = "utf-8"

# Gọi module chấm điểm
result = subprocess.run(["python", r"benchmark\run_ragas_v2.py", "--runtime", RUNTIME, "--gold", GOLD, "--output", SCORE], env=env_vars, capture_output=True, text=True, cwd=r"c:\Users\check\Downloads\scp")

print(result.stdout)
if result.stderr:
    print(f"BÁO LỖI: {result.stderr}")
