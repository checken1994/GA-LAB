[CmdletBinding()]
param(
    [ValidateSet('Auto', 'WindowsSandbox', 'HyperV')]
    [string]$Mode = 'Auto',
    [string]$RepoPath = '',
    [string]$OutputRoot = 'D:\UserData\scp-benchmark',
    [string]$HyperVBaseVhdxPath = '',
    [switch]$Start
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Chạy PowerShell bằng Run as administrator để tạo sandbox/VM.'
    }
}

function Resolve-Repo {
    param([string]$Requested)
    if ($Requested) {
        return (Resolve-Path -LiteralPath $Requested).Path
    }
    return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Get-Mode {
    param([string]$Requested)
    if ($Requested -ne 'Auto') { return $Requested }
    $sandbox = Get-Command WindowsSandbox.exe -ErrorAction SilentlyContinue
    if ($sandbox) { return 'WindowsSandbox' }
    $hyperv = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -ErrorAction SilentlyContinue
    if ($hyperv -and $hyperv.State -eq 'Enabled') { return 'HyperV' }
    throw 'Không thấy Windows Sandbox hoặc Hyper-V đã bật. Hãy bật một trong hai trước; script không tự reboot máy.'
}

function Copy-SanitizedRepo {
    param(
        [string]$Source,
        [string]$Destination
    )
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $excluded = @(
        '.git', '.private-secrets', 'data', 'node_modules', 'venv', '.next',
        'desktop\\runtime', 'desktop\\.private-release-current',
        'desktop\\.private-release', 'Downloads', 'dist', 'build'
    )
    $xd = @()
    foreach ($name in $excluded) { $xd += (Join-Path $Source $name) }
    & robocopy $Source $Destination /E /R:0 /W:0 /XJ /NFL /NDL /NJH /NJS /XD $xd | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Sao chép workspace thất bại, robocopy exit=$LASTEXITCODE"
    }

    $forbidden = Get-ChildItem -LiteralPath $Destination -Recurse -Force -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^(\.env|.*\.(pem|key|pfx|p12|kdbx|sqlite|db|jsonl))$' -or
            $_.Name -match '(secret|token|password|credential|cookie)' -or
            $_.FullName -match '\\(data|\.private-secrets|node_modules|venv|\.git)\\'
        }
    if ($forbidden) {
        $names = ($forbidden | Select-Object -First 20 -ExpandProperty FullName) -join "`n"
        throw "Workspace benchmark chứa file có thể là secret hoặc runtime data; dừng, không tự xóa:`n$names"
    }
}

function Write-Bootstrap {
    param(
        [string]$InputFolder,
        [string]$OutputFolder
    )
    $bootstrap = @'
$ErrorActionPreference = 'Stop'
$root = 'C:\SCPBenchmark'
$input = Join-Path $root 'input'
$workspace = Join-Path $root 'workspace'
$out = Join-Path $root 'out'
New-Item -ItemType Directory -Force -Path $workspace, $out | Out-Null

# Copy to a writable guest-only workspace. The host input mapping remains read-only.
robocopy $input $workspace /E /R:0 /W:0 /XJ /NFL /NDL /NJH /NJS /XD '.git' 'node_modules' 'venv' '.next' 'data' | Out-Null
if ($LASTEXITCODE -gt 7) { throw "Workspace copy failed: $LASTEXITCODE" }

# Safe benchmark boundary. No provider key, production env, or host token is allowed.
$env:SCP_BENCHMARK_MODE = '1'
$env:SCP_DEV_MODE = '0'
$env:SCP_SKIP_STARTUP_GATE = '0'
$env:SCP_AUTO_APPROVE_TIER3 = '0'
$env:SCP_TIER3_ALLOW_RELAXATION = '0'
$env:SCP_TIER3_ALLOW_BAREEXCEPTPASS = '0'
$env:SCP_EVOLUTION_AUTO = '0'
$env:SCP_WHY_LLM_ENABLED = '0'
$env:SCP_ENABLE_CLOSED_LOOP = '0'
$env:SCP_AUTOFIX_DETERMINISTIC_ONLY = '1'
$env:SCP_AUTH_TOKEN_SECRET = ''
$env:SCP_AUTH_PASSWORD = ''
$env:OPENROUTER_API_KEY = ''
$env:OPENAI_API_KEY = ''

$manifest = [ordered]@{
    run_id = [guid]::NewGuid().ToString('N')
    started_utc = [DateTime]::UtcNow.ToString('o')
    network = 'disabled-by-wsb'
    host_input_read_only = $true
    host_secrets_mapped = $false
    clipboard = 'disabled'
    audio = 'disabled'
    video = 'disabled'
    dangerous_flags = 'forced_off'
    workspace = $workspace
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $out 'sandbox-manifest.json')

# This command only runs deterministic, offline checks. Add a separate, reviewed
# benchmark command after the test set is frozen; never paste secrets here.
$compile = Join-Path $out 'compile.log'
& py -3 -m compileall -q (Join-Path $workspace 'scp') *> $compile
$manifest.compile_exit = $LASTEXITCODE
$manifest.finished_utc = [DateTime]::UtcNow.ToString('o')
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $out 'sandbox-manifest.json')
'@
    Set-Content -LiteralPath (Join-Path $InputFolder 'sandbox_bootstrap.ps1') -Value $bootstrap -Encoding UTF8
}

function New-WindowsSandboxProfile {
    param(
        [string]$InputFolder,
        [string]$OutputFolder,
        [string]$ProfilePath
    )
    $xml = @"
<Configuration>
  <VGpu>Disable</VGpu>
  <Networking>Disable</Networking>
  <AudioInput>Disable</AudioInput>
  <VideoInput>Disable</VideoInput>
  <ProtectedClient>Enable</ProtectedClient>
  <PrinterRedirection>Disable</PrinterRedirection>
  <ClipboardRedirection>Disable</ClipboardRedirection>
  <MemoryInMB>8192</MemoryInMB>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$InputFolder</HostFolder>
      <SandboxFolder>C:\SCPBenchmark\input</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$OutputFolder</HostFolder>
      <SandboxFolder>C:\SCPBenchmark\out</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\SCPBenchmark\input\sandbox_bootstrap.ps1</Command>
  </LogonCommand>
</Configuration>
"@
    Set-Content -LiteralPath $ProfilePath -Value $xml -Encoding UTF8
}

function New-HyperVProfile {
    param(
        [string]$VmRoot,
        [string]$BaseVhdx,
        [string]$VmName
    )
    if (-not $BaseVhdx) {
        throw 'HyperV mode cần -HyperVBaseVhdxPath trỏ tới một VHDX sạch đã được kiểm tra. Script không tải ISO hay mở mạng.'
    }
    if (-not (Test-Path -LiteralPath $BaseVhdx -PathType Leaf)) {
        throw "Không tìm thấy base VHDX: $BaseVhdx"
    }
    $switch = Get-VMSwitch -Name 'SCP-Benchmark-Private' -ErrorAction SilentlyContinue
    if (-not $switch) {
        New-VMSwitch -Name 'SCP-Benchmark-Private' -SwitchType Private | Out-Null
    }
    $vm = Get-VM -Name $VmName -ErrorAction SilentlyContinue
    if (-not $vm) {
        New-Item -ItemType Directory -Force -Path $VmRoot | Out-Null
        $diff = Join-Path $VmRoot ($VmName + '.avhdx')
        New-VHD -Path $diff -ParentPath $BaseVhdx -Differencing | Out-Null
        New-VM -Name $VmName -Generation 2 -MemoryStartupBytes 8GB -VHDPath $diff -SwitchName 'SCP-Benchmark-Private' | Out-Null
        Set-VMProcessor -VMName $VmName -Count 4
        Set-VM -Name $VmName -AutomaticStopAction TurnOff -CheckpointType Standard
        Set-VMFirmware -VMName $VmName -EnableSecureBoot On
    }
    $vm | Select-Object Name,State,Generation,Path | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $VmRoot 'hyperv-manifest.json')
}

Assert-Administrator
$repo = Resolve-Repo $RepoPath
$selected = Get-Mode $Mode
$run = 'scp-benchmark-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$runRoot = Join-Path $OutputRoot $run
$input = Join-Path $runRoot 'input'
$out = Join-Path $runRoot 'out'
New-Item -ItemType Directory -Force -Path $runRoot, $out | Out-Null
Copy-SanitizedRepo -Source $repo -Destination $input
Write-Bootstrap -InputFolder $input -OutputFolder $out

$manifest = [ordered]@{
    run_id = $run
    mode = $selected
    source_repo = $repo
    run_root = $runRoot
    network = 'disabled'
    input_read_only = $true
    host_secrets_mapped = $false
    created_utc = [DateTime]::UtcNow.ToString('o')
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $runRoot 'host-manifest.json')

if ($selected -eq 'WindowsSandbox') {
    $profile = Join-Path $runRoot ($run + '.wsb')
    New-WindowsSandboxProfile -InputFolder $input -OutputFolder $out -ProfilePath $profile
    Write-Output "PROFILE=$profile"
    if ($Start) {
        Start-Process -FilePath 'WindowsSandbox.exe' -ArgumentList "`"$profile`""
        Write-Output 'STARTED=WindowsSandbox'
    }
}
else {
    New-HyperVProfile -VmRoot $runRoot -BaseVhdx $HyperVBaseVhdxPath -VmName ($run + '-vm')
    Write-Output "HYPERV_ROOT=$runRoot"
    Write-Output 'STARTED=NO (install/provision the clean guest before booting the benchmark)'
    if ($Start) {
        Start-VM -Name ($run + '-vm') | Out-Null
        Write-Output 'HYPERV_STARTED=YES'
    }
}

Write-Output "MODE=$selected"
Write-Output "RUN_ROOT=$runRoot"
Write-Output 'NETWORK=DISABLED'
Write-Output 'SECRETS_MAPPED=NO'
Write-Output 'CLIPBOARD=AUDIO=VIDEO=DISABLED'
