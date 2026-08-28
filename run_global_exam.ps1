$examLog = "c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\global_exam_progress.log"
Write-Output "BẮT ĐẦU KỲ THI FULL-SCALE (ZERO-SHOT) - 08/28/2026 14:58:50" | Out-File -FilePath $examLog -Encoding UTF8
cd c:\Users\check\Downloads\scp

# Ép hệ thống dùng UTF-8 chuẩn
$env:PYTHONIOENCODING="utf-8"

# Chạy Full dataset không giới hạn số lượng câu hỏi (--workers 8)
python benchmark\run_benchmark_v2_parallel.py 
    --url "http://127.0.0.1:8002" 
    --output "data\archives\benchmarks_202608\GLOBAL_EXAM_FINAL_RESULT.json" 
    --questions-output "data\archives\benchmarks_202608\GLOBAL_EXAM_QUESTIONS.jsonl" 
    --workers 8 2>&1 | Tee-Object -FilePath $examLog -Append
    
Write-Output "KỲ THI ĐÃ KẾT THÚC. KẾT QUẢ ĐƯỢC LƯU TẠI GLOBAL_EXAM_FINAL_RESULT.json" | Out-File -FilePath $examLog -Append -Encoding UTF8
