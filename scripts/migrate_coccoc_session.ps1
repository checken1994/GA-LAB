$ErrorActionPreference = 'Stop'

$sourceData = 'C:\Users\check\AppData\Local\CocCoc\Browser\User Data'
$sourceProfile = Join-Path $sourceData 'Default'
$targetData = 'C:\Users\check\AppData\Local\SCP\CocCocDevToolsProfile'
$targetProfile = Join-Path $targetData 'Default'

if (-not (Test-Path $sourceProfile)) {
    throw "Khong tim thay profile Cốc Cốc nguon: $sourceProfile"
}

Write-Output 'Dang dong cac tien trinh Cốc Cốc...'
$processes = @(Get-CimInstance Win32_Process | Where-Object {
    ([string]$_.ExecutablePath -like '*\CocCoc\*') -or
    ([string]$_.CommandLine -like '*\CocCoc\*')
})
foreach ($proc in $processes) {
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

New-Item -ItemType Directory -Force -Path $targetProfile | Out-Null

function Copy-SessionItem([string]$relativePath) {
    $source = Join-Path $sourceData $relativePath
    $target = Join-Path $targetData $relativePath
    if (-not (Test-Path $source)) {
        Write-Output ("SKIP|" + $relativePath)
        return
    }
    $targetParent = Split-Path -Parent $target
    New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
    $item = Get-Item $source
    if ($item.PSIsContainer) {
        Copy-Item -Path $source -Destination $target -Recurse -Force
        $bytes = (Get-ChildItem $source -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    } else {
        Copy-Item -Path $source -Destination $target -Force
        $bytes = $item.Length
    }
    Write-Output ("COPIED|" + $relativePath + "|bytes=" + $bytes)
}

# Local State contains the Windows-user-bound encryption key metadata.
# The following browser storage files hold session state; their contents are not read.
$items = @(
    'Local State',
    'Default\Cookies',
    'Default\Network\Cookies',
    'Default\Local Storage',
    'Default\Session Storage',
    'Default\IndexedDB',
    'Default\Preferences'
)
foreach ($item in $items) {
    Copy-SessionItem $item
}

Write-Output ("DONE|target=" + $targetData)
