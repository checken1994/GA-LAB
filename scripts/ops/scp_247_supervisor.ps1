[CmdletBinding()]
param(
    [switch]$Once,
    [switch]$DryRun,
    [int]$IntervalSeconds = 15,
    [int]$MaxRestartsPerWindow = 5,
    [int]$RestartWindowSeconds = 900
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$PrivateDir = Join-Path $Root '.private-secrets\release-audit\scp-247'
$LogDir = Join-Path $PrivateDir 'logs'
$LedgerPath = Join-Path $PrivateDir 'supervisor-ledger.jsonl'
$StatePath = Join-Path $PrivateDir 'supervisor-state.json'
$KillSwitchPath = Join-Path $PrivateDir 'KILL'
$MutexName = 'Global\SCP_247_Supervisor'
$TaskName = 'SCP-247-Supervisor'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$mutex = [Threading.Mutex]::new($false, $MutexName)
$ownsMutex = $false
try {
    $ownsMutex = $mutex.WaitOne(0)
    if (-not $ownsMutex) {
        exit 17
    }

    function Write-Ledger {
        param(
            [string]$Event,
            [string]$Service = '',
            [string]$Reason = '',
            [hashtable]$Extra = @{}
        )
        $record = [ordered]@{
            ts = [DateTime]::UtcNow.ToString('o')
            event = $Event
            service = $Service
            reason = $Reason
            task = $TaskName
            pid = $PID
        }
        foreach ($key in $Extra.Keys) {
            $record[$key] = $Extra[$key]
        }
        ($record | ConvertTo-Json -Compress -Depth 5) + "`n" | Add-Content -Encoding UTF8 -Path $LedgerPath
    }

    function Get-EnvFlag {
        param([string]$Name)
        $envFile = Join-Path $Root '.env'
        $value = $null
        if (Test-Path $envFile) {
            $line = Get-Content $envFile -Encoding UTF8 | Where-Object { $_ -match "^$([regex]::Escape($Name))\s*=" } | Select-Object -Last 1
            if ($line) {
                $value = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
            }
        }
        if ($null -eq $value -and $null -ne [Environment]::GetEnvironmentVariable($Name)) {
            $value = [Environment]::GetEnvironmentVariable($Name)
        }
        if ($null -eq $value -or $value -eq '') { return 'MISSING' }
        if ($value -match '^(1|true|on|yes|active)$') { return 'ON' }
        if ($value -match '^(0|false|off|no|inactive)$') { return 'OFF' }
        return 'INVALID'
    }

    function Assert-Guardrails {
        $dangerous = @(
            'SCP_DEV_MODE',
            'SCP_SKIP_STARTUP_GATE',
            'SCP_AUTO_APPROVE_TIER3',
            'SCP_TIER3_ALLOW_RELAXATION',
            'SCP_TIER3_ALLOW_BAREEXCEPTPASS'
        )
        $bad = @()
        foreach ($name in $dangerous) {
            $state = Get-EnvFlag $name
            if ($state -eq 'ON' -or $state -eq 'INVALID') { $bad += $name }
            Write-Ledger -Event 'GUARDRAIL' -Reason "$name=$state"
        }
        $closedLoop = Get-EnvFlag 'SCP_ENABLE_CLOSED_LOOP'
        Write-Ledger -Event 'GUARDRAIL' -Reason "SCP_ENABLE_CLOSED_LOOP=$closedLoop"
        if ($closedLoop -eq 'ON') { $bad += 'SCP_ENABLE_CLOSED_LOOP' }
        if ($bad.Count -gt 0) {
            Write-Ledger -Event 'BLOCKED' -Reason 'dangerous_or_closed_loop_flag_active' -Extra @{ flags = ($bad -join ',') }
            throw 'SCP 24/7 blocked by guardrail flags'
        }
    }

    function Resolve-Executable {
        param([string]$Name)
        $command = Get-Command $Name -ErrorAction SilentlyContinue
        if (-not $command) { throw "Executable not found: $Name" }
        return $command.Source
    }

    $bun = Resolve-Executable 'bun'
    $python = Join-Path $Root 'scp\venv\Scripts\python.exe'
    if (-not (Test-Path $python)) { throw "Python venv missing: $python" }

    $services = @(
        [ordered]@{ Name = 'llm-bridge'; File = $bun; Args = @('run', 'dev'); Dir = (Join-Path $Root 'mini-services\llm-bridge'); Port = 11434; Url = 'http://127.0.0.1:11434/api/tags' },
        [ordered]@{ Name = 'loop-scheduler'; File = $bun; Args = @('run', 'dev'); Dir = (Join-Path $Root 'mini-services\loop-scheduler'); Port = 3030; Url = 'http://127.0.0.1:3030/' },
        [ordered]@{ Name = 'scp-python'; File = $python; Args = @('-m', 'scp', '8000'); Dir = $Root; Port = 8000; Url = 'http://127.0.0.1:8000/health' },
        [ordered]@{ Name = 'dashboard'; File = $bun; Args = @('run', 'dev'); Dir = (Join-Path $Root 'dashboard'); Port = 3000; Url = 'http://127.0.0.1:3000/' }
    )

    function Test-PortInUse {
        param([int]$Port)
        return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    }

    function Test-HttpHealthy {
        param([string]$Url)
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4 -SkipHttpErrorCheck
            return ($response.StatusCode -lt 500)
        } catch {
            return $false
        }
    }

    function Start-ScpService {
        param([object]$Service)
        if (Test-PortInUse $Service.Port) {
            Write-Ledger -Event 'PORT_OCCUPIED' -Service $Service.Name -Reason 'listener_exists_before_supervisor_start'
            return $null
        }
        if (-not (Test-Path $Service.Dir)) {
            Write-Ledger -Event 'START_REJECTED' -Service $Service.Name -Reason 'working_directory_missing'
            return $null
        }
        $stdout = Join-Path $LogDir "$($Service.Name).out.log"
        $stderr = Join-Path $LogDir "$($Service.Name).err.log"
        $oldLoopLog = $env:LOOP_LOG_PATH
        $oldScpBaseUrl = $env:SCP_BASE_URL
        $oldLlmBridgeUrl = $env:LLM_BRIDGE_URL
        $oldClosedLoop = $env:SCP_ENABLE_CLOSED_LOOP
        $env:SCP_ENABLE_CLOSED_LOOP = '0'
        if ($Service.Name -eq 'loop-scheduler') {
            $env:LOOP_LOG_PATH = Join-Path $Root 'data\\loop_runs.jsonl'
            $env:SCP_BASE_URL = 'http://127.0.0.1:8000'
            $env:LLM_BRIDGE_URL = 'http://127.0.0.1:11434'
        }
        try {
            if ($DryRun) {
                Write-Ledger -Event 'DRYRUN_START' -Service $Service.Name -Reason 'start_would_be_requested'
                return [pscustomobject]@{ Id = 0; Name = $Service.Name; StartedAt = [DateTime]::UtcNow }
            }
            $process = Start-Process -FilePath $Service.File -ArgumentList $Service.Args -WorkingDirectory $Service.Dir -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
            Write-Ledger -Event 'START' -Service $Service.Name -Reason 'supervisor_start' -Extra @{ child_pid = $process.Id; port = $Service.Port }
            return [pscustomobject]@{ Id = $process.Id; Name = $Service.Name; StartedAt = [DateTime]::UtcNow }
        } finally {
            $env:LOOP_LOG_PATH = $oldLoopLog
            $env:SCP_BASE_URL = $oldScpBaseUrl
            $env:LLM_BRIDGE_URL = $oldLlmBridgeUrl
            $env:SCP_ENABLE_CLOSED_LOOP = $oldClosedLoop
        }
    }

    function Stop-ScpService {
        param([object]$Runtime, [string]$Reason)
        if ($null -eq $Runtime -or $Runtime.Id -le 0 -or $DryRun) { return }
        & taskkill.exe /PID $Runtime.Id /T /F *> $null
        Write-Ledger -Event 'STOP' -Service $Runtime.Name -Reason $Reason -Extra @{ child_pid = $Runtime.Id }
    }

    Assert-Guardrails
    if (Test-Path $KillSwitchPath) {
        Write-Ledger -Event 'KILL_SWITCH_PRESENT' -Reason 'startup_abort'
        exit 20
    }

    $restartHistory = @{}
    $runtime = @{}
    foreach ($service in $services) {
        $runtime[$service.Name] = Start-ScpService $service
        $restartHistory[$service.Name] = @()
    }

    Write-Ledger -Event 'SUPERVISOR_STARTED' -Reason $(if ($DryRun) { 'dry_run' } else { 'canary_or_service_mode' }) -Extra @{ interval_seconds = $IntervalSeconds; root = $Root }

    do {
        Start-Sleep -Seconds $IntervalSeconds
        if (Test-Path $KillSwitchPath) {
            Write-Ledger -Event 'KILL_SWITCH' -Reason 'operator_file_present'
            foreach ($service in $services) { Stop-ScpService $runtime[$service.Name] 'kill_switch' }
            break
        }
        foreach ($service in $services) {
            $entry = $runtime[$service.Name]
            $processAlive = $false
            if ($null -ne $entry -and $entry.Id -gt 0) {
                $processAlive = [bool](Get-Process -Id $entry.Id -ErrorAction SilentlyContinue)
            } elseif ($DryRun) {
                $processAlive = $true
            }
            $healthy = $processAlive -and (Test-HttpHealthy $service.Url)
            if ($healthy) {
                Write-Ledger -Event 'HEALTHY' -Service $service.Name -Reason 'process_and_http_ok'
                continue
            }
            $now = [DateTime]::UtcNow
            $restartHistory[$service.Name] = @($restartHistory[$service.Name] | Where-Object { ($now - $_).TotalSeconds -lt $RestartWindowSeconds })
            if ($restartHistory[$service.Name].Count -ge $MaxRestartsPerWindow) {
                Write-Ledger -Event 'CIRCUIT_OPEN' -Service $service.Name -Reason 'restart_budget_exhausted' -Extra @{ restart_count = $restartHistory[$service.Name].Count }
                continue
            }
            Stop-ScpService $entry 'health_failure'
            $restartHistory[$service.Name] += $now
            $runtime[$service.Name] = Start-ScpService $service
            Write-Ledger -Event 'RESTART' -Service $service.Name -Reason 'health_failure' -Extra @{ restart_count = $restartHistory[$service.Name].Count }
        }
    } while (-not $Once)

    foreach ($service in $services) { Stop-ScpService $runtime[$service.Name] 'supervisor_exit' }
    Write-Ledger -Event 'SUPERVISOR_STOPPED' -Reason $(if (Test-Path $KillSwitchPath) { 'kill_switch' } else { 'once_or_exit' })
} catch {
    Write-Ledger -Event 'SUPERVISOR_ERROR' -Reason $_.Exception.GetType().Name
    exit 1
} finally {
    if ($ownsMutex) { $mutex.ReleaseMutex() | Out-Null }
    $mutex.Dispose()
}
