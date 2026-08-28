Stop-Process -Name "python" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

Write-Host "1. Khởi động V3 Enterprise Kernel..."
$serverProcess = Start-Process -FilePath "python" -ArgumentList "-m scp 8002" -PassThru -WindowStyle Hidden

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
    Write-Host "LỖI: Máy chủ không thể khởi động. Kiểm tra server_log.txt"
    exit 1
}

Write-Host "2. Chạy bài thi GSM8K Top 1% (Gửi kèm JWT, chấm bằng LLM Judge)..."
$env:PYTHONIOENCODING="utf-8"
python c:\Users\check\Downloads\scp\benchmark\run_world_exam.py c:\Users\check\Downloads\scp\benchmark\gsm8k_sample_10.jsonl

Stop-Process -Id $serverProcess.Id -Force
Write-Host "Đã đóng máy chủ."
