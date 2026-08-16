[CmdletBinding()]
param(
    [ValidateSet('Status', 'Disable', 'Enable', 'SetInterval', 'Restore')]
    [string]$Action = 'Status',
    [ValidateRange(1, 1440)]
    [int]$IntervalMinutes = 5,
    [string]$BackupXmlPath = '',
    [switch]$StartAfterEnable
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$TaskName = 'SCP-247-Recovery-Watchdog'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$AuditRoot = Join-Path $RepoRoot 'scp-audit'

function Get-Watchdog {
    return Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
}

function Get-IntervalText {
    param($Task)
    $trigger = @($Task.Triggers) | Select-Object -First 1
    if ($null -eq $trigger) { return '' }
    return [string]$trigger.Repetition.Interval
}

function Write-Status {
    $task = Get-Watchdog
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    $action = @($task.Actions) | Select-Object -First 1
    [pscustomobject]@{
        Task = $TaskName
        State = [string]$task.State
        Hidden = [bool]$task.Settings.Hidden
        MultipleInstances = [string]$task.Settings.MultipleInstances
        ExecutionTimeLimit = [string]$task.Settings.ExecutionTimeLimit
        Interval = Get-IntervalText $task
        LastRun = [string]$info.LastRunTime
        NextRun = [string]$info.NextRunTime
        LastResult = $info.LastTaskResult
        Execute = [string]$action.Execute
        Arguments = [string]$action.Arguments
    } | ConvertTo-Json -Depth 6
}

function Backup-Task {
    New-Item -ItemType Directory -Force -Path $AuditRoot | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $dir = Join-Path $AuditRoot ('watchdog-control-' + $stamp)
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $xmlPath = Join-Path $dir ($TaskName + '.xml')
    $jsonPath = Join-Path $dir 'status-before.json'
    Export-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Set-Content -LiteralPath $xmlPath -Encoding UTF8
    (Write-Status | Out-String) | Set-Content -LiteralPath $jsonPath -Encoding UTF8
    Write-Output ('BACKUP_DIR=' + $dir)
    Write-Output ('BACKUP_XML=' + $xmlPath)
    return $xmlPath
}

function Restore-Task {
    param([string]$Path)
    if (-not $Path) { throw '-BackupXmlPath là bắt buộc khi Action=Restore.' }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Không tìm thấy XML backup: $Path" }
    $xml = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop
    if ($xml -notmatch '<Task') { throw 'Backup XML không giống Scheduled Task XML; dừng.' }
    Register-ScheduledTask -TaskName $TaskName -Xml $xml -Force -ErrorAction Stop | Out-Null
    Write-Output 'RESTORE=PASS'
    Write-Status
}

switch ($Action) {
    'Status' {
        Write-Status
        break
    }
    'Disable' {
        $null = Backup-Task
        $task = Get-Watchdog
        if ($task.State -eq 'Running') {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        }
        Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
        Write-Output 'DISABLE=PASS'
        Write-Status
        break
    }
    'Enable' {
        $null = Backup-Task
        Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
        if ($StartAfterEnable) {
            Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        }
        Write-Output 'ENABLE=PASS'
        Write-Status
        break
    }
    'SetInterval' {
        $xmlPath = Backup-Task
        $xml = Get-Content -LiteralPath $xmlPath -Raw -ErrorAction Stop
        $pattern = '<Interval>PT[0-9]+M</Interval>'
        if ($xml -notmatch $pattern) { throw 'Không tìm thấy interval PTnM trong task XML; không sửa mù.' }
        $newInterval = 'PT' + $IntervalMinutes + 'M'
        $updated = [regex]::Replace($xml, $pattern, '<Interval>' + $newInterval + '</Interval>', 1)
        if ($updated -eq $xml) { throw 'Interval mới không tạo ra thay đổi; dừng.' }
        Register-ScheduledTask -TaskName $TaskName -Xml $updated -Force -ErrorAction Stop | Out-Null
        Write-Output ('SET_INTERVAL=PASS VALUE=' + $newInterval)
        Write-Status
        break
    }
    'Restore' {
        Restore-Task -Path $BackupXmlPath
        break
    }
}
