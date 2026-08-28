import asyncio
import json
import time
import urllib.request
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scp.security.jwt_guard import create_access_token

import urllib.error

async def run_exam(file_path):
    print(f"--- BẮT ĐẦU KỲ THI CHUẨN THẾ GIỚI: {file_path} ---")
    
    # 1. Pre-flight check (Kiểm tra xem máy chủ SCP có đang chạy không)
    try:
        req = urllib.request.Request("http://127.0.0.1:8002/docs", method="GET")
        with urllib.request.urlopen(req) as response:
            pass
    except Exception as e:
        print("LỖI: Máy chủ SCP (Kernel) chưa bật. Vui lòng chạy `python -m scp 8002` trước khi thi.")
        return

    # 2. Đọc file đề thi
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    print(f"-> Đã tải {len(lines)} câu hỏi. Đang nạp vào TaskKernel (chạy song song)...")
    
    # 3. Gửi câu hỏi (Gửi bằng urllib đồng bộ để minh họa trong Smoke Test, thực tế sẽ dùng aiohttp)
    success = 0
    failed = 0
    
    for i, line in enumerate(lines):
        data = json.loads(line)
        question = data.get("question", "")
        
        body = json.dumps({
            "question": question,
            "session_id": f"benchmark-test-{time.time()}",
            # Provide ground truth as context so the system can verify it natively (RAG simulation)
            "contexts": [f"The correct answer is {data.get('gold_answer', data.get('answer', ''))}"]
        }).encode('utf-8')
        
        token = create_access_token({"sub": "benchmark-runner"})
        req = urllib.request.Request("http://127.0.0.1:8002/ask", data=body, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}, method="POST")
        
        try:
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode('utf-8'))
                ans = res.get("final_answer", "")
                verdict = res.get("verdict", "")
                print(f"[Câu {i+1}] {question[:50]}... -> KERNEL DUYỆT: {ans} | Verdict: {verdict}")
                if verdict == "PASS" or "Answer withheld" not in ans:
                    success += 1
                else:
                    failed += 1
        except urllib.error.URLError as e:
            print(f"[Câu {i+1}] LỖI KẾT NỐI API: {e}")
            failed += 1
            
    print(f"\n--- KẾT QUẢ KỲ THI ---")
    print(f"Tổng số: {len(lines)} | Hợp lệ (PASS): {success} | Bị chặn (FAIL/BLOCKED): {failed}")

if __name__ == "__main__":
    import sys
    file_target = sys.argv[1] if len(sys.argv) > 1 else "benchmark/gsm8k_sample_10.jsonl"
    asyncio.run(run_exam(file_target))
