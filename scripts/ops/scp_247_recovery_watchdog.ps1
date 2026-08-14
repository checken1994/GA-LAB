param(
    [switch]$Once
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$PrivateDir = Join-Path $Root '.private-secrets\release-audit\scp-247'
$KillSwitch = Join-Path $PrivateDir 'KILL'
$Ledger = Join-Path $PrivateDir 'supervisor-ledger.jsonl'
$SupervisorTask = 'SCP-247-Supervisor'
$WatchdogTask = 'SCP-247-Recovery-Watchdog'

New-Item -ItemType Directory -Force -Path $PrivateDir | Out-Null

function Write-AtomicJsonLine([hashtable]$Event) {
    $Event['timestamp'] = [DateTime]::UtcNow.ToString('o')
    $Event['watchdog_task'] = $WatchdogTask
    $line = ($Event | ConvertTo-Json -Compress -Depth 6)
    Add-Content -LiteralPath $Ledger -Value $line -Encoding UTF8
}

function Test-KillSwitch {
    return (Test-Path -LiteralPath $KillSwitch -PathType Leaf)
}

function Get-SupervisorState {
    try {
        return (Get-ScheduledTask -TaskName $SupervisorTask -ErrorAction Stop).State.ToString()
    } catch {
        return 'MISSING'
    }
}

function Invoke-Recovery {
    if (Test-KillSwitch) {
        Write-AtomicJsonLine @{ event = 'WATCHDOG_SUPPRESSED'; reason = 'kill_switch_present' }
        return 'SUPPRESSED_KILL'
    }
    $state = Get-SupervisorState
    if ($state -eq 'Running') {
        return 'HEALTHY_RUNNING'
    }
    if ($state -eq 'Disabled') {
        Write-AtomicJsonLine @{ event = 'WATCHDOG_BLOCKED'; reason = 'supervisor_task_disabled' }
        return 'BLOCKED_DISABLED'
    }
    try {
        Start-ScheduledTask -TaskName $SupervisorTask -ErrorAction Stop
        Write-AtomicJsonLine @{ event = 'WATCHDOG_RECOVERY_START'; reason = "supervisor_state=$state" }
        return 'RECOVERY_STARTED'
    } catch {
        Write-AtomicJsonLine @{ event = 'WATCHDOG_RECOVERY_FAIL'; reason = $_.Exception.Message.Substring(0, [Math]::Min(200, $_.Exception.Message.Length)) }
        return 'RECOVERY_FAILED'
    }
}

$result = Invoke-Recovery
if ($Once) {
    Write-Output "WATCHDOG_RESULT=$result"
    exit 0
}

# The scheduled task invokes this script once per minute. No resident loop is
# used, so a hung watchdog cannot accumulate duplicate processes.
Write-Output "WATCHDOG_RESULT=$result"
exit 0
