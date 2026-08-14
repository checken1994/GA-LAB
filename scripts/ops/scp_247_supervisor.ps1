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
$SafeChildEnvFile = Join-Path $PrivateDir 'child-safe.env'
$MutexName = 'Global\SCP_247_Supervisor'
$TaskName = 'SCP-247-Supervisor'

# Windows Job Object is the containment boundary. If Task Scheduler, pwsh,
# or this supervisor is terminated externally, closing the process handle
# kills every child service and prevents orphan runtime writers.
Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

public static class ScpJobObjectNative
{
    private const uint JobObjectExtendedLimitInformation = 9;
    private const uint JobObjectLimitKillOnJobClose = 0x2000;

    [StructLayout(LayoutKind.Sequential)]
    private struct BasicLimitInformation
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct IoCounters
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ExtendedLimitInformation
    {
        public BasicLimitInformation BasicLimitInformation;
        public IoCounters IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateJobObject(IntPtr attributes, string name);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetInformationJobObject(IntPtr job, uint infoClass, ref ExtendedLimitInformation info, uint length);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr handle);

    public static IntPtr CreateKillOnCloseJob()
    {
        IntPtr job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero) throw new InvalidOperationException("CreateJobObject failed: " + Marshal.GetLastWin32Error());
        var info = new ExtendedLimitInformation();
        info.BasicLimitInformation.LimitFlags = JobObjectLimitKillOnJobClose;
        if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation, ref info, (uint)Marshal.SizeOf(typeof(ExtendedLimitInformation))))
        {
            int error = Marshal.GetLastWin32Error();
            CloseHandle(job);
            throw new InvalidOperationException("SetInformationJobObject failed: " + error);
        }
        return job;
    }

    public static void Assign(IntPtr job, int processId)
    {
        using (var process = Process.GetProcessById(processId))
        {
            if (!AssignProcessToJobObject(job, process.Handle))
                throw new InvalidOperationException("AssignProcessToJobObject failed: " + Marshal.GetLastWin32Error());
        }
    }

    public static void Close(IntPtr job)
    {
        if (job != IntPtr.Zero) CloseHandle(job);
    }
}
'@

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
# Explicit child env boundary: only safe OFF flags. Auth values are injected
# directly into the child process environment and never written here.
$safeEnvText = @(
    'SCP_DEV_MODE=0',
    'SCP_SKIP_STARTUP_GATE=0',
    'SCP_AUTO_APPROVE_TIER3=0',
    'SCP_TIER3_ALLOW_RELAXATION=0',
    'SCP_TIER3_ALLOW_BAREEXCEPTPASS=0',
    'SCP_ENABLE_CLOSED_LOOP=0'
) -join [Environment]::NewLine
$safeEnvTmp = "$SafeChildEnvFile.tmp"
[IO.File]::WriteAllText($safeEnvTmp, $safeEnvText + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $safeEnvTmp -Destination $SafeChildEnvFile -Force

$mutex = [Threading.Mutex]::new($false, $MutexName)
    $ownsMutex = $false
$jobHandle = [IntPtr]::Zero
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
        $oldScpEnvFile = $env:SCP_ENV_FILE
        $oldAuthToken = $env:SCP_AUTH_TOKEN_SECRET
        $oldAuthPassword = $env:SCP_AUTH_PASSWORD
        $oldAuthTokenFile = $env:SCP_AUTH_TOKEN_SECRET_FILE
        $oldAuthPasswordFile = $env:SCP_AUTH_PASSWORD_FILE
        $oldDangerous = @{}
        foreach ($flag in @('SCP_DEV_MODE','SCP_SKIP_STARTUP_GATE','SCP_AUTO_APPROVE_TIER3','SCP_TIER3_ALLOW_RELAXATION','SCP_TIER3_ALLOW_BAREEXCEPTPASS')) {
            $oldDangerous[$flag] = [Environment]::GetEnvironmentVariable($flag, 'Process')
        }
        $env:SCP_ENABLE_CLOSED_LOOP = '0'
        try {
            if ($Service.Name -in @('loop-scheduler','scp-python')) {
                $env:LOOP_LOG_PATH = Join-Path $Root 'data\\loop_runs.jsonl'
                $env:SCP_BASE_URL = 'http://127.0.0.1:8000'
                $env:LLM_BRIDGE_URL = 'http://127.0.0.1:11434'
                # Bun/Python child processes must not receive the entire
                # production env file: it may contain unrelated/dangerous flags.
                # Read only auth values into the child environment, never print
                # or write them, and force all mutation/learning flags OFF.
                foreach ($flag in @('SCP_DEV_MODE','SCP_SKIP_STARTUP_GATE','SCP_AUTO_APPROVE_TIER3','SCP_TIER3_ALLOW_RELAXATION','SCP_TIER3_ALLOW_BAREEXCEPTPASS','SCP_ENABLE_CLOSED_LOOP')) {
                    Set-Item -Path "Env:$flag" -Value '0'
                }
                $explicitEnvFile = Join-Path (Split-Path $Root -Parent) '.env'
                if (-not (Test-Path -LiteralPath $explicitEnvFile -PathType Leaf)) {
                    Write-Ledger -Event 'START_REJECTED' -Service $Service.Name -Reason 'explicit_auth_env_file_missing'
                    return $null
                }
                $authToken = ''
                $authPassword = ''
                foreach ($line in Get-Content -LiteralPath $explicitEnvFile -Encoding UTF8) {
                    $trimmed = ([string]$line).Trim()
                    if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) { continue }
                    $pair = $trimmed.Split('=', 2)
                    $key = $pair[0].Trim()
                    $value = $pair[1].Trim().Trim('"').Trim("'")
                    if ($key -eq 'SCP_AUTH_TOKEN_SECRET') { $authToken = $value }
                    if ($key -eq 'SCP_AUTH_PASSWORD') { $authPassword = $value }
                }
                if (-not $authToken -and -not $authPassword) {
                    Write-Ledger -Event 'START_REJECTED' -Service $Service.Name -Reason 'auth_value_missing_in_explicit_env_file'
                    return $null
                }
                if ($authToken) { $env:SCP_AUTH_TOKEN_SECRET = $authToken } else { Remove-Item Env:SCP_AUTH_TOKEN_SECRET -ErrorAction SilentlyContinue }
                if ($authPassword) { $env:SCP_AUTH_PASSWORD = $authPassword } else { Remove-Item Env:SCP_AUTH_PASSWORD -ErrorAction SilentlyContinue }
                Remove-Item Env:SCP_AUTH_TOKEN_SECRET_FILE -ErrorAction SilentlyContinue
                Remove-Item Env:SCP_AUTH_PASSWORD_FILE -ErrorAction SilentlyContinue
                $env:SCP_ENV_FILE = $SafeChildEnvFile
            }
            if ($DryRun) {
                Write-Ledger -Event 'DRYRUN_START' -Service $Service.Name -Reason 'start_would_be_requested'
                return [pscustomobject]@{ Id = 0; Name = $Service.Name; StartedAt = [DateTime]::UtcNow }
            }
            $process = Start-Process -FilePath $Service.File -ArgumentList $Service.Args -WorkingDirectory $Service.Dir -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
            try {
                Add-ScpProcessToJob -ChildProcessId $process.Id
            } catch {
                & taskkill.exe /PID $process.Id /T /F *> $null
                throw
            }
            Write-Ledger -Event 'START' -Service $Service.Name -Reason 'supervisor_start' -Extra @{ child_pid = $process.Id; port = $Service.Port; contained_by_job = (-not $DryRun) }
            return [pscustomobject]@{ Id = $process.Id; Name = $Service.Name; StartedAt = [DateTime]::UtcNow }
        } finally {
            $env:LOOP_LOG_PATH = $oldLoopLog
            $env:SCP_BASE_URL = $oldScpBaseUrl
            $env:LLM_BRIDGE_URL = $oldLlmBridgeUrl
            $env:SCP_ENABLE_CLOSED_LOOP = $oldClosedLoop
            if ($null -eq $oldScpEnvFile) { Remove-Item Env:SCP_ENV_FILE -ErrorAction SilentlyContinue } else { $env:SCP_ENV_FILE = $oldScpEnvFile }
            if ($null -eq $oldAuthToken) { Remove-Item Env:SCP_AUTH_TOKEN_SECRET -ErrorAction SilentlyContinue } else { $env:SCP_AUTH_TOKEN_SECRET = $oldAuthToken }
            if ($null -eq $oldAuthPassword) { Remove-Item Env:SCP_AUTH_PASSWORD -ErrorAction SilentlyContinue } else { $env:SCP_AUTH_PASSWORD = $oldAuthPassword }
            if ($null -eq $oldAuthTokenFile) { Remove-Item Env:SCP_AUTH_TOKEN_SECRET_FILE -ErrorAction SilentlyContinue } else { $env:SCP_AUTH_TOKEN_SECRET_FILE = $oldAuthTokenFile }
            if ($null -eq $oldAuthPasswordFile) { Remove-Item Env:SCP_AUTH_PASSWORD_FILE -ErrorAction SilentlyContinue } else { $env:SCP_AUTH_PASSWORD_FILE = $oldAuthPasswordFile }
            foreach ($flag in $oldDangerous.Keys) {
                if ($null -eq $oldDangerous[$flag]) { Remove-Item "Env:$flag" -ErrorAction SilentlyContinue } else { Set-Item "Env:$flag" $oldDangerous[$flag] }
            }
        }
    }

    function Add-ScpProcessToJob {
        param([int]$ChildProcessId)
        if ($DryRun) { return }
        if ($jobHandle -eq [IntPtr]::Zero) { throw 'Job Object is not initialized' }
        [ScpJobObjectNative]::Assign($jobHandle, $ChildProcessId)
    }

    function Stop-ScpService {
        param([object]$Runtime, [string]$Reason)
        if ($null -eq $Runtime -or $Runtime.Id -le 0 -or $DryRun) { return }
        & taskkill.exe /PID $Runtime.Id /T /F *> $null
        Write-Ledger -Event 'STOP' -Service $Runtime.Name -Reason $Reason -Extra @{ child_pid = $Runtime.Id }
    }

    Assert-Guardrails
    if (-not $DryRun) {
        $jobHandle = [ScpJobObjectNative]::CreateKillOnCloseJob()
        Write-Ledger -Event 'JOB_OBJECT_CREATED' -Reason 'kill_on_job_close_child_containment'
    }
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
    if ($jobHandle -ne [IntPtr]::Zero) {
        [ScpJobObjectNative]::Close($jobHandle)
        $jobHandle = [IntPtr]::Zero
    }
    if ($ownsMutex) { $mutex.ReleaseMutex() | Out-Null }
    $mutex.Dispose()
}
