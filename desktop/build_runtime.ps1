[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDir,
    [string]$OutputDir = (Join-Path $PSScriptRoot 'runtime')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$required = @(
    'scp-backend.exe',
    'scp-llm-bridge.exe',
    'scp-loop-scheduler.exe',
    'scp-autofix-worker.exe'
)

$source = (Resolve-Path $SourceDir).Path
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

foreach ($name in $required) {
    $candidate = Join-Path $source $name
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Required runtime artifact missing: $candidate"
    }
    Copy-Item -LiteralPath $candidate -Destination (Join-Path $OutputDir $name) -Force
}

# Never copy live runtime data, production .env files, source Python, or node_modules.
Get-ChildItem -LiteralPath $OutputDir -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @('data', '.env', 'node_modules') -or $_.Extension -eq '.py' } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$artifacts = foreach ($name in $required) {
    $path = Join-Path $OutputDir $name
    $item = Get-Item -LiteralPath $path
    $hash = Get-FileHash -LiteralPath $path -Algorithm SHA256
    [ordered]@{
        name = $name
        size_bytes = $item.Length
        sha256 = $hash.Hash
        built_at_utc = [DateTime]::UtcNow.ToString('o')
    }
}

$manifest = [ordered]@{
    schema = 'scp.desktop.runtime-build.v1'
    platform = 'windows-x64'
    source_dir = $source
    output_dir = (Resolve-Path $OutputDir).Path
    artifacts = @($artifacts)
    production_env_copied = $false
    live_data_copied = $false
    source_python_copied = $false
}
$manifestPath = Join-Path $OutputDir 'runtime-build-manifest.json'
$tmp = "$manifestPath.tmp"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $tmp -Encoding UTF8
Move-Item -LiteralPath $tmp -Destination $manifestPath -Force
Write-Output ($manifest | ConvertTo-Json -Depth 8)
