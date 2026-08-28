Stop-Process -Name "python" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

Write-Host "1. Bật máy chủ SCP (TaskKernel)..."
$serverProcess = Start-Process -FilePath "python" -ArgumentList "-m scp 8002" -PassThru -WindowStyle Hidden

Write-Host "2. Đợi máy chủ khởi động (Pre-flight check)..."
$retries = 0
$serverReady = $false
while ($retries -lt 30) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8002/docs" -Method Head -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $serverReady = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
        $retries++
    }
}

if (-not $serverReady) {
    Write-Host "LỖI: Máy chủ không thể khởi động."
    Get-Content server_log7.txt -Tail 20
    exit 1
}

Write-Host "3. Máy chủ đã SẴN SÀNG! Đang chạy 4 câu Nhãn Vàng..."
$env:PYTHONIOENCODING="utf-8"
python c:\Users\check\Downloads\scp\benchmark\run_world_exam.py c:\Users\check\Downloads\scp\benchmark\human_verified_gold.jsonl

Write-Host "`n4. Đang chạy 10 câu GSM8K Top 1%..."
python c:\Users\check\Downloads\scp\benchmark\run_world_exam.py c:\Users\check\Downloads\scp\benchmark\gsm8k_sample_10.jsonl

Stop-Process -Id $serverProcess.Id -Force
Write-Host "Đã đóng máy chủ."
