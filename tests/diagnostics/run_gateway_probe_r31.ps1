#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\check\Downloads\scp'
$names = @(
  'codex_sandbox_offline_block_outbound',
  'codex_sandbox_offline_block_loopback_tcp',
  'codex_sandbox_offline_block_loopback_udp'
)
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outPath = "data\gateway-probe-r31-$stamp.json"
$manifest = "data\firewall-r31-gateway-probe-after-$stamp.json"
$prior = [ordered]@{}
foreach ($name in $names) {
  $rule = Get-NetFirewallRule -DisplayName $name -ErrorAction Stop
  $prior[$name] = [string]$rule.Enabled
}
try {
  Disable-NetFirewallRule -DisplayName $names -ErrorAction Stop
  $env:SCP_LLM_PROVIDER_MODE = 'ollama_only'
  $env:OLLAMA_MODEL_AUTOFIX = 'llama3.2:latest'
  $env:OLLAMA_MODEL_WHY = 'llama3.2:latest'
  $env:OLLAMA_MODEL_LEARNING = 'llama3.2:latest'
  $env:OLLAMA_MODEL_JUDGE = 'llama3.2:latest'
  $env:PYTHONUTF8 = '1'
  $env:PYTHONIOENCODING = 'utf-8'
  $result = & 'scp\venv\Scripts\python.exe' 'probe_gateway_r31.py' 2>&1
  $result | Set-Content -LiteralPath $outPath -Encoding UTF8
  Write-Output "PROBE_OUTPUT=$outPath"
  Write-Output ($result | Select-Object -Last 1)
} finally {
  foreach ($name in $names) {
    Set-NetFirewallRule -DisplayName $name -Enabled $prior[$name] -ErrorAction Stop
  }
  $rules = [ordered]@{}
  foreach ($name in $names) {
    $rules[$name] = [string](Get-NetFirewallRule -DisplayName $name).Enabled
  }
  [ordered]@{
    restored_utc = (Get-Date).ToUniversalTime().ToString('o')
    rules = $rules
    restored_to = $prior
  } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifest -Encoding UTF8
  Write-Output "RESTORE_MANIFEST=$manifest"
}
