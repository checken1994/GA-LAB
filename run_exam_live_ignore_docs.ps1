Write-Host "1. Bật máy chủ SCP (TaskKernel)..."
$serverProcess = Start-Process -FilePath "python" -ArgumentList "-m scp 8002" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 5

Write-Host "3. Máy chủ đã khởi động! Tiến hành chạy bài thi NHÃN VÀNG (BẰNG CHỨNG THÉP)..."
$env:PYTHONIOENCODING="utf-8"
python c:\Users\check\Downloads\scp\benchmark\run_world_exam.py c:\Users\check\Downloads\scp\benchmark\human_verified_gold.jsonl

Stop-Process -Id $serverProcess.Id -Force
Write-Host "Đã hoàn thành."
