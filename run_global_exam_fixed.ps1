$examLog = "c:\Users\check\Downloads\scp\data\archives\benchmarks_202608\global_exam_progress.log"
Write-Output "BẮT ĐẦU KỲ THI FULL-SCALE (ZERO-SHOT) - $(Get-Date)" | Out-File -FilePath $examLog -Encoding UTF8
cd c:\Users\check\Downloads\scp

$env:PYTHONIOENCODING="utf-8"

Write-Output "Đang chạy Python benchmark..." | Out-File -FilePath $examLog -Append -Encoding UTF8
# Viết trên 1 dòng duy nhất để tránh lỗi Syntax PowerShell
python benchmark\run_benchmark_v2_parallel.py --url "http://127.0.0.1:8002" --output "data\archives\benchmarks_202608\GLOBAL_EXAM_FINAL_RESULT.json" --questions-output "data\archives\benchmarks_202608\GLOBAL_EXAM_QUESTIONS.jsonl" --workers 8 2>&1 | Tee-Object -FilePath $examLog -Append

Write-Output "KỲ THI ĐÃ KẾT THÚC. KẾT QUẢ ĐƯỢC LƯU TẠI GLOBAL_EXAM_FINAL_RESULT.json" | Out-File -FilePath $examLog -Append -Encoding UTF8
