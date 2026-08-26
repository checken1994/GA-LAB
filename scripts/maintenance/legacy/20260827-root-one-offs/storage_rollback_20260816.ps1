$ErrorActionPreference = 'Stop'
$C = 'C:\Users\check\Downloads\scp'
$D = 'D:\UserData\storage-move-20260816\scp\repo'
$Relatives = @(
  'dashboard\node_modules',
  'dashboard\.next',
  'desktop\node_modules',
  'scp\venv',
  '..\..\Documents',
  '..\..\data',
  '..\..\Videos',
  '..\..\Music',
  '..\..\AppData\Local\npm-cache',
  '..\..\AppData\Local\pip',
  '..\..\AppData\Local\SCP',
  '..\..\AppData\Roaming\npm',
  '..\..\.bun',
  '..\..\AppData\Local\uv',
  '..\..\AppData\Local\ms-playwright',
  '..\..\AppData\Local\CrashDumps',
  '..\..\AppData\Local\electron-builder',
  '..\..\AppData\Local\CEF',
  '..\..\AppData\Local\D3DSCache'
)
foreach ($Relative in $Relatives) {
  $Link = Join-Path $C $Relative
  $Source = Join-Path $D $Relative
  if (-not (Test-Path -LiteralPath $Source)) {
    throw "Rollback source missing on D: $Source"
  }
  if (Test-Path -LiteralPath $Link) {
    $Item = Get-Item -LiteralPath $Link -Force
    if ($Item.LinkType) {
      Remove-Item -LiteralPath $Link -Force
    } else {
      throw "Expected junction but found regular path: $Link"
    }
  }
  New-Item -ItemType Directory -Force -Path $Link | Out-Null
  Copy-Item -LiteralPath (Join-Path $Source '*') -Destination $Link -Recurse -Force
}
Write-Output 'STORAGE_ROLLBACK=RESTORED_C_PATHS_FROM_D'
