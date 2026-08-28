import asyncio
import json
import time
import urllib.request
import sys
import os
import subprocess
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scp.security.jwt_guard import create_access_token

import urllib.error

async def run_exam(file_path):
    print(f"--- STARTING EXAM: {file_path} ---")
    
    # 1. Pre-flight check
    try:
        req = urllib.request.Request("http://127.0.0.1:8002/health", method="GET")
        with urllib.request.urlopen(req) as response:
            pass
    except Exception as e:
        print("LỖI: Máy chủ SCP (Kernel) chưa bật. Vui lòng chạy `python -m scp 8002` trước khi thi.")
        return

    # 2. Đọc file đề thi
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    print(f"-> Đã tải {len(lines)} câu hỏi. Đang gọi API server...")
    
    raw_results_file = "raw_results.jsonl"
    
    # 3. Gửi câu hỏi và lưu raw response
    with open(raw_results_file, "w", encoding="utf-8") as out_f:
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            question = data.get("question", "")
            
            body = json.dumps({
                "question": question,
                "session_id": f"benchmark-test-{time.time()}",
                "contexts": [],
                "source": "scp_batch_benchmark_v1"
            }).encode('utf-8')
            
            token = create_access_token({"sub": "benchmark-runner"})
            req = urllib.request.Request("http://127.0.0.1:8002/ask", data=body, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}, method="POST")
            
            api_response = {}
            try:
                with urllib.request.urlopen(req) as response:
                    api_response = json.loads(response.read().decode('utf-8'))
                    print(f"[Câu {i+1}] {question[:50]}... -> XONG")
            except Exception as e:
                print(f"[Câu {i+1}] LỖI KẾT NỐI API: {e}")
                api_response = {"error": str(e)}
                
            # Lưu raw kết quả để grader chấm điểm độc lập
            out_data = {
                "question": question,
                "gold_answer": data.get("gold_answer") or data.get("answer"),
                "api_response": api_response
            }
            out_f.write(json.dumps(out_data, ensure_ascii=False) + "\n")
            
    print(f"\n--- ĐÃ LƯU KẾT QUẢ THÔ VÀO {raw_results_file} ---")
    print("-> Gọi Grader độc lập (DNA #5, DNA #14) để chấm điểm...")
    
    dataset_type = "truthfulqa" if "truthfulqa" in str(file_path).lower() else "gsm8k"
    
    grader_path = os.path.join(os.path.dirname(__file__), "grader.py")
    subprocess.run([sys.executable, grader_path, raw_results_file, "--dataset", dataset_type])

if __name__ == "__main__":
    file_target = sys.argv[1] if len(sys.argv) > 1 else "benchmark/gsm8k_sample_10.jsonl"
    asyncio.run(run_exam(file_target))
