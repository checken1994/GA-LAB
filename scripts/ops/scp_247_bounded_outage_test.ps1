[CmdletBinding()]
param(
    [int]$Cycles = 1,
    [int]$ObservationSeconds = 45
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$AuditDir = Join-Path $Root '.private-secrets\release-audit\scp-247\experiments'
$Ledger = Join-Path $Root '.private-secrets\release-audit\scp-247\supervisor-ledger.jsonl'
New-Item -ItemType Directory -Force -Path $AuditDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$eventsBefore = (Get-Content -LiteralPath $Ledger -ErrorAction SilentlyContinue).Count
$record = [ordered]@{
    experiment = 'bounded-llm-bridge-outage'
    started_utc = [DateTime]::UtcNow.ToString('o')
    cycles = $Cycles
    observation_seconds = $ObservationSeconds
    kill_switch_before = Test-Path (Join-Path $Root '.private-secrets\release-audit\scp-247\KILL')
    env_touched = $false
    policy_touched = $false
    events_before = $eventsBefore
    cycles_result = @()
}
if ($record.kill_switch_before) { throw 'Refusing test: kill switch already present' }
for ($cycle = 1; $cycle -le $Cycles; $cycle++) {
    $listener = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $listener) { throw "Refusing test: LLM Bridge port 11434 is not listening before cycle $cycle" }
    $targetPid = [int]$listener.OwningProcess
    $killed_at = [DateTime]::UtcNow
    & taskkill.exe /PID $targetPid /T /F *> $null
    $recovered = $false
    $recovery_seconds = $null
    for ($i = 1; $i -le $ObservationSeconds; $i++) {
        Start-Sleep -Seconds 1
        $portUp = [bool](Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)
        $httpOk = $false
        if ($portUp) {
            try {
                $response = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -UseBasicParsing -TimeoutSec 2 -SkipHttpErrorCheck
                $httpOk = ([int]$response.StatusCode -lt 500)
            } catch { $httpOk = $false }
        }
        if ($portUp -and $httpOk) { $recovered = $true; $recovery_seconds = $i; break }
    }
    $record.cycles_result += [ordered]@{cycle=$cycle; killed_pid=$targetPid; killed_utc=$killed_at.ToString('o'); recovered=$recovered; recovery_seconds=$recovery_seconds}
    if (-not $recovered) { break }
}
$record.finished_utc = [DateTime]::UtcNow.ToString('o')
$record.kill_switch_after = Test-Path (Join-Path $Root '.private-secrets\release-audit\scp-247\KILL')
$record.port_11434_after = [bool](Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)
try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -UseBasicParsing -TimeoutSec 5 -SkipHttpErrorCheck; $record.http_11434_after = [int]$response.StatusCode } catch { $record.http_11434_after = 'FAIL' }
$out = Join-Path $AuditDir "outage-$stamp.json"
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Encoding UTF8
Write-Output "EVIDENCE=$out"
$record | ConvertTo-Json -Depth 8
if (@($record.cycles_result | Where-Object { -not $_.recovered }).Count -gt 0) { exit 2 }
if (-not $record.port_11434_after -or $record.http_11434_after -ge 500) { exit 3 }
exit 0
