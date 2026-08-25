$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
$ProdEnvFile = Join-Path $Root ".env"
$EnvFile = Join-Path $Root ".env.test"
if (Test-Path -LiteralPath $ProdEnvFile) {
foreach ($line in Get-Content -LiteralPath $ProdEnvFile) {
$trim = $line.Trim()
if ($trim -and -not $trim.StartsWith("#") -and $trim.Contains("=")) {
$name = $trim.Split("=",2)[0].Trim()
if ($name) { [Environment]::SetEnvironmentVariable($name,"","Process") }
} } }
if (-not (Test-Path -LiteralPath $EnvFile)) { throw ".env.test not found" }
[Environment]::SetEnvironmentVariable("SCP_ENV_FILE", $EnvFile, "Process")
foreach ($line in Get-Content -LiteralPath $EnvFile) {
$trim = $line.Trim()
if ($trim -and -not $trim.StartsWith("#") -and $trim.Contains("=")) {
$parts = $trim.Split("=",2)
[Environment]::SetEnvironmentVariable($parts[0].Trim(),$parts[1].Trim(),"Process")
} }
$safe=@{ SCP_HOST="127.0.0.1"; SCP_PORT="8001"; SCP_SKIP_STARTUP_GATE="0"; SCP_DEV_MODE="0"; SCP_AUTO_APPROVE_TIER3="0"; SCP_EVOLUTION_AUTO="0"; SCP_ENABLE_CLOSED_LOOP="0"; SCP_TIER3_ALLOW_RELAXATION="0"; SCP_TIER3_ALLOW_BAREEXCEPTPASS="0"; SCP_DATA_DIR="data-test"; OPENROUTER_API_KEY=""; OPENROUTER_API_KEY_2=""; OPENROUTER_API_KEY_3=""; OLLAMA_ENABLED="false" }
foreach ($k in $safe.Keys) { [Environment]::SetEnvironmentVariable($k,$safe[$k],"Process") }
Write-Output "SCP isolated test launcher"
Write-Output "Host=$env:SCP_HOST Port=$env:SCP_PORT DataDir=$env:SCP_DATA_DIR"
Write-Output "StartupGate=$env:SCP_SKIP_STARTUP_GATE DevMode=$env:SCP_DEV_MODE AutoApprove=$env:SCP_AUTO_APPROVE_TIER3 ClosedLoop=$env:SCP_ENABLE_CLOSED_LOOP"
Write-Output "ProviderKeysPresent=$(-not [string]::IsNullOrWhiteSpace($env:OPENROUTER_API_KEY))"
& (Join-Path $Root "scp\venv\Scripts\python.exe") -m scp $env:SCP_PORT


