[CmdletBinding()]
param(
    [int]$Cycles = 1,
    [int]$ObservationSeconds = 45,
    [string]$PythonPath = '',
    [string]$SnapshotScript = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($Cycles -lt 1 -or $Cycles -gt 6) { throw 'Cycles must be between 1 and 6' }
if ($ObservationSeconds -lt 10 -or $ObservationSeconds -gt 300) { throw 'ObservationSeconds must be between 10 and 300' }

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$AuditDir = Join-Path $Root '.private-secrets\release-audit\scp-247\experiments'
$Ledger = Join-Path $Root '.private-secrets\release-audit\scp-247\supervisor-ledger.jsonl'
$KillSwitch = Join-Path $Root '.private-secrets\release-audit\scp-247\KILL'
if ([string]::IsNullOrWhiteSpace($PythonPath)) { $PythonPath = Join-Path $Root 'scp\venv\Scripts\python.exe' }
if ([string]::IsNullOrWhiteSpace($SnapshotScript)) { $SnapshotScript = Join-Path $PSScriptRoot 'scp_db_consistent_snapshot.py' }
New-Item -ItemType Directory -Force -Path $AuditDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$out = Join-Path $AuditDir "outage-$stamp.json"

function Atomic-WriteJson([string]$Path, [object]$Value) {
    $tmp = "$Path.tmp"
    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $tmp -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}

function Task-Running {
    $task = Get-ScheduledTask -TaskName 'SCP-247-Supervisor' -ErrorAction Stop
    return ([string]$task.State -eq 'Running')
}

function Port-Listening([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Http-Ok([string]$Url) {
    try {
        # Keep this compatible with both Windows PowerShell 5.1 and pwsh 7.
        $reply = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
        return ([int]$reply.StatusCode -lt 500)
    } catch { return $false }
}

function Assert-Preflight {
    if (Test-Path -LiteralPath $KillSwitch) { throw 'Refusing test: kill switch already present' }
    if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python runtime missing: $PythonPath" }
    if (-not (Test-Path -LiteralPath $SnapshotScript)) { throw "Snapshot utility missing: $SnapshotScript" }
    if (-not (Task-Running)) { throw 'Refusing test: SCP-247-Supervisor is not Running; possible orphan-child state' }
    foreach ($port in 3000,3030,8000,11434) {
        if (-not (Port-Listening $port)) { throw "Refusing test: required port $port is not listening" }
    }
    if (-not (Http-Ok 'http://127.0.0.1:11434/api/tags')) { throw 'Refusing test: LLM Bridge health failed before test' }
}

$record = [ordered]@{
    schema = 'scp.bounded-outage.v2'
    experiment = 'bounded-llm-bridge-outage'
    status = 'STARTING'
    started_utc = [DateTime]::UtcNow.ToString('o')
    cycles_requested = $Cycles
    observation_seconds = $ObservationSeconds
    env_touched = $false
    policy_touched = $false
    kill_switch_before = Test-Path -LiteralPath $KillSwitch
    snapshot_manifest = $null
    cycles_result = @()
    errors = @()
}

$exitCode = 0
try {
    Assert-Preflight
    $record.preflight = 'PASS'

    $snapshotOutput = & $PythonPath $SnapshotScript --root $Root --label "pre-$stamp" 2>&1
    $snapshotExit = $LASTEXITCODE
    if ($snapshotExit -ne 0) { throw "Pre-test SQLite snapshot failed with exit ${snapshotExit}: $($snapshotOutput -join ' ')" }
    $snapshotJson = ($snapshotOutput -join "`n") | ConvertFrom-Json
    if ($snapshotJson.status -ne 'COMPLETE') { throw "Pre-test snapshot status was $($snapshotJson.status)" }
    $record.snapshot_manifest = [string]$snapshotJson.manifest

    for ($cycle = 1; $cycle -le $Cycles; $cycle++) {
        if (-not (Task-Running)) { throw "Supervisor stopped before cycle $cycle" }
        $listener = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $listener) { throw "LLM Bridge port 11434 is not listening before cycle $cycle" }
        $targetPid = [int]$listener.OwningProcess
        $killedAt = [DateTime]::UtcNow
        & taskkill.exe /PID $targetPid /T /F 2>$null | Out-Null
        $killExit = $LASTEXITCODE
        if ($killExit -ne 0) { throw "taskkill failed for target PID $targetPid with exit $killExit" }

        $recovered = $false
        $recoverySeconds = $null
        for ($second = 1; $second -le $ObservationSeconds; $second++) {
            Start-Sleep -Seconds 1
            $portUp = Port-Listening 11434
            $httpOk = $portUp -and (Http-Ok 'http://127.0.0.1:11434/api/tags')
            if ($portUp -and $httpOk) { $recovered = $true; $recoverySeconds = $second; break }
        }
        $record.cycles_result += [ordered]@{
            cycle = $cycle
            killed_process_id = $targetPid
            killed_utc = $killedAt.ToString('o')
            recovered = $recovered
            recovery_seconds = $recoverySeconds
            supervisor_running_after_cycle = (Task-Running)
        }
        if (-not $recovered) { throw "LLM Bridge did not recover within $ObservationSeconds seconds at cycle $cycle" }
        if (-not (Task-Running)) { throw "Supervisor stopped after cycle $cycle; refusing further fault injection" }
    }

    $record.status = 'PASS'
} catch {
    $record.status = 'FAIL_CLOSED'
    $record.errors += [ordered]@{ type = $_.Exception.GetType().Name; message = $_.Exception.Message }
    $exitCode = 2
} finally {
    $record.finished_utc = [DateTime]::UtcNow.ToString('o')
    $record.kill_switch_after = Test-Path -LiteralPath $KillSwitch
    $record.task_state_after = [string](Get-ScheduledTask -TaskName 'SCP-247-Supervisor' -ErrorAction SilentlyContinue).State
    $record.ports_after = [ordered]@{}
    foreach ($port in 3000,3030,8000,11434) { $record.ports_after["$port"] = Port-Listening $port }
    $record.http_11434_after = if (Http-Ok 'http://127.0.0.1:11434/api/tags') { 200 } else { 'FAIL' }
    Atomic-WriteJson $out $record
}

Write-Output "EVIDENCE=$out"
$record | ConvertTo-Json -Depth 12
exit $exitCode
