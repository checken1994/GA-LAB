[CmdletBinding()]
param(
    [ValidateSet('status','stop','kill','clear-kill')]
    [string]$Action = 'status'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$TaskName = 'SCP-247-Supervisor'
$PrivateDir = Join-Path $Root '.private-secrets\release-audit\scp-247'
$KillSwitch = Join-Path $PrivateDir 'KILL'
$Ledger = Join-Path $PrivateDir 'supervisor-ledger.jsonl'

New-Item -ItemType Directory -Force -Path $PrivateDir | Out-Null

switch ($Action) {
    'status' {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
        [ordered]@{
            task_exists = [bool]$task
            task_state = if ($task) { [string]$task.State } else { 'MISSING' }
            last_run = if ($info) { $info.LastRunTime.ToUniversalTime().ToString('o') } else { $null }
            next_run = if ($info) { $info.NextRunTime.ToUniversalTime().ToString('o') } else { $null }
            kill_switch = Test-Path $KillSwitch
            ledger_exists = Test-Path $Ledger
            root = $Root
        } | ConvertTo-Json -Depth 4
    }
    'stop' {
        New-Item -ItemType File -Force -Path $KillSwitch | Out-Null
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Write-Output 'KILL_SWITCH_CREATED=True'
        Write-Output 'TASK_STOP_REQUESTED=True'
    }
    'kill' {
        New-Item -ItemType File -Force -Path $KillSwitch | Out-Null
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like 'SCP-*' } | Stop-Process -Force -ErrorAction SilentlyContinue
        Write-Output 'KILL_SWITCH_CREATED=True'
        Write-Output 'TASK_STOP_REQUESTED=True'
        Write-Output 'WINDOW_PROCESSES_STOP_REQUESTED=True'
    }
    'clear-kill' {
        if (Test-Path $KillSwitch) { Remove-Item -Force $KillSwitch }
        Write-Output 'KILL_SWITCH_CLEARED=True'
    }
}
