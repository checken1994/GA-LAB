import json
import requests
import os
import subprocess

URL = "http://127.0.0.1:8002/ask"
GOLD = r"c:\Users\check\Downloads\scp\benchmark\gold_anchor_5_QUICK.jsonl"
RUNTIME = r"c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\real_exam_1_runtime.jsonl"
SCORE = r"c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\ragas_1_score.json"

print(">> [1/2] LẤY 1 CÂU HỎI & CHỜ AI TRẢ LỜI (Đợi tối đa 120 giây)...")
with open(GOLD, "r", encoding="utf-8") as fin:
    first_q = json.loads(fin.readline())

with open(RUNTIME, "w", encoding="utf-8") as fout:
    try:
        resp = requests.post(URL, json={"question": first_q["question"], "source": "quick_exam"}, timeout=120)
        ai_ans = resp.json().get("final_answer", "")
        print(f"Đã có đáp án: {ai_ans[:50]}...")
        res_obj = {
            "question_id": first_q["question_id"],
            "question": first_q["question"],
            "gold_answer": first_q["gold_answer"],
            "gold_chunk_text": first_q["gold_chunk_text"],
            "ai_answer": ai_ans
        }
        fout.write(json.dumps(res_obj, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"LỖI: Máy chủ AI quá tải không thể trả lời. ({e})")

print("\n>> [2/2] GỌI RAGAS CHẤM ĐIỂM (Fix lỗi Encoding UTF-8)...")
try:
    # Fix lỗi UnicodeDecodeError bằng cách thêm encoding="utf-8"
    env_lines = open(r"c:\Users\check\Downloads\scp\.env", "r", encoding="utf-8").readlines()
    openrouter_key = ""
    for line in env_lines:
        if line.startswith("OPENAI_API_KEY="):
            openrouter_key = line.split("=")[1].strip()

    env_vars = os.environ.copy()
    env_vars["OPENAI_API_KEY"] = openrouter_key
    env_vars["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
    env_vars["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(["python", r"benchmark\run_ragas_v2.py", "--runtime", RUNTIME, "--gold", GOLD, "--output", SCORE], env=env_vars, capture_output=True, text=True, cwd=r"c:\Users\check\Downloads\scp")
    print(result.stdout)
except Exception as e:
    print("Lỗi chấm điểm:", e)
