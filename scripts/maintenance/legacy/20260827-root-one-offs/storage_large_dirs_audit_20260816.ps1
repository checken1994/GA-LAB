$ErrorActionPreference = 'SilentlyContinue'
$Targets = @(
  'C:\Users\check',
  'C:\home',
  'C:\Cache',
  'C:\CFLog',
  'C:\PerfLogs',
  'C:\inetpub'
)
$Rows = foreach ($Target in $Targets) {
  if (-not (Test-Path -LiteralPath $Target)) { continue }
  $Root = Get-Item -LiteralPath $Target -Force
  if ($Root.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
  $Children = Get-ChildItem -LiteralPath $Target -Force -Directory
  foreach ($Child in $Children) {
    if ($Child.Attributes -band [IO.FileAttributes]::ReparsePoint) {
      [pscustomobject]@{Target=$Target;Name=$Child.Name;Path=$Child.FullName;Bytes=0;Files=0;ReparsePoint=$true}
      continue
    }
    $Files = Get-ChildItem -LiteralPath $Child.FullName -File -Recurse -Force
    [pscustomobject]@{
      Target=$Target
      Name=$Child.Name
      Path=$Child.FullName
      Bytes=[int64](($Files | Measure-Object -Property Length -Sum).Sum)
      Files=[int64](($Files | Measure-Object).Count)
      ReparsePoint=$false
    }
  }
}
$Rows | Sort-Object Bytes -Descending | Export-Csv -NoTypeInformation -Encoding UTF8 -LiteralPath 'D:\UserData\storage-move-20260816\large-dir-audit-after.csv'
$Rows | Sort-Object Bytes -Descending | Select-Object -First 40 Target,Name,Bytes,Files,ReparsePoint | Format-Table -AutoSize
Write-Output 'LARGE_DIR_AUDIT=RECORDED'
