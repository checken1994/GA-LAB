Write-Host "--- SCP PRE-PUSH GATE ---"

Write-Host "1. Checking Imports vs Requirements..."
python scripts/check_imports_vs_requirements.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Import check failed."
    exit 1
}

Write-Host "2. Starting Server..."
$proc = Start-Process -FilePath "python" -ArgumentList "-m scp 8002" -PassThru -WindowStyle Hidden
Write-Host "Waiting for server to boot..."
Start-Sleep -Seconds 5

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8002/health" -Method GET
    Write-Host "Health: $($health.status)"
    
    $admin_key = $env:SCP_ADMIN_KEY
    if (-not $admin_key) { 
        Write-Host "[FAIL] SCP_ADMIN_KEY environment variable not set."
        Stop-Process -Id $proc.Id -Force
        exit 1 
    }
    
    $token_body = @{ "admin_key" = $admin_key } | ConvertTo-Json
    $token_res = Invoke-RestMethod -Uri "http://127.0.0.1:8002/auth/token" -Method POST -Body $token_body -ContentType "application/json"
    $token = $token_res.access_token
    Write-Host "Auth: Token Acquired"

    $random_id = [guid]::NewGuid().ToString()
    $ask_body = @{
        "question" = "Is the sky blue?"
        "ai_answer" = "The sky is blue."
        "contexts" = @("The sky is blue.")
        "session_id" = "test_gate_$random_id"
    } | ConvertTo-Json

    $ask_res = Invoke-RestMethod -Uri "http://127.0.0.1:8002/ask" -Method POST -Body $ask_body -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $token" }
    
    $ans = $ask_res.final_answer
    Write-Host "Answer: $ans"
    
    if ($ans -match "Answer withheld") {
        Write-Host "[FAIL] The server withheld the answer despite having evidence. The logic is broken."
        Stop-Process -Id $proc.Id -Force
        exit 1
    }

    Write-Host "[PASS] Pre-push gate cleared."
    Stop-Process -Id $proc.Id -Force
    exit 0
} catch {
    Write-Host "[FAIL] Gate failed with error: $_"
    Stop-Process -Id $proc.Id -Force
    exit 1
}
