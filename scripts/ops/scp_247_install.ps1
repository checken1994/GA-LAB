[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$StartNow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$TaskName = 'SCP-247-Supervisor'
$Supervisor = Join-Path $Root 'scripts\ops\scp_247_supervisor.ps1'
$PrivateDir = Join-Path $Root '.private-secrets\release-audit\scp-247'
$LogDir = Join-Path $PrivateDir 'logs'
$Manifest = Join-Path $PrivateDir 'install-manifest.json'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if (-not (Test-Path $Supervisor)) { throw "Supervisor missing: $Supervisor" }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Supervisor`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'SCP fail-closed 24/7 supervisor; policy learning remains disabled'

$record = [ordered]@{
    timestamp = [DateTime]::UtcNow.ToString('o')
    task_name = $TaskName
    user = $env:USERNAME
    trigger = 'AtLogOn'
    supervisor = $Supervisor
    policy_learning = 'not_enabled_by_installer'
    production_env_modified = $false
    dry_run = [bool]$DryRun
}

if ($DryRun) {
    $record.mode = 'DRY_RUN'
} else {
    Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
    $record.mode = 'REGISTERED'
}
$record | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $Manifest
Write-Output ($record | ConvertTo-Json -Depth 5)

if ($StartNow -and -not $DryRun) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Output 'START_REQUESTED=True'
}
