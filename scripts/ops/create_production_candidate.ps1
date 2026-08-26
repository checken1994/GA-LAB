$ErrorActionPreference='Stop'
$Root=(Get-Location).Path
$Private=Join-Path $Root '.private-secrets'
New-Item -ItemType Directory -Force $Private | Out-Null
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$candidate=Join-Path $Root '.env.production.candidate'
if(Test-Path $candidate){Copy-Item $candidate (Join-Path $Private ("env-production-candidate-before-"+$stamp+".bak")) -Force}
function New-SecretFile($name){
  $p=Join-Path $Private $name
  if(-not (Test-Path $p)){
    $bytes=New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    [IO.File]::WriteAllText($p,[Convert]::ToBase64String($bytes),[Text.UTF8Encoding]::new($false))
  }
  icacls $p /inheritance:r /grant:r "$env:USERNAME:(R)" | Out-Null
  return $p
}
$auth=New-SecretFile 'scp-auth-password'
$token=New-SecretFile 'scp-auth-token'
$scheduler=New-SecretFile 'scp-scheduler-admin-token'
@"
# SCP production candidate — NOT active until explicitly promoted.
# Generated: $stamp
SCP_PRODUCTION_MODE=1
SCP_DEV_MODE=0
SCP_SKIP_STARTUP_GATE=0
SCP_AUTO_APPROVE_TIER3=0
SCP_EVOLUTION_AUTO=0
SCP_ENABLE_CLOSED_LOOP=0
SCP_TIER3_ALLOW_RELAXATION=0
SCP_TIER3_ALLOW_BAREEXCEPTPASS=0
SCP_EGRESS_MODE=deny
SCP_HOST=127.0.0.1
SCP_PORT=8002
LOOP_SCHEDULER_HOST=127.0.0.1
LOOP_SCHEDULER_PORT=3030
SCP_AUTH_PASSWORD_FILE=.private-secrets\scp-auth-password
SCP_AUTH_TOKEN_SECRET_FILE=.private-secrets\scp-auth-token
SCP_SCHEDULER_ADMIN_TOKEN_FILE=.private-secrets\scp-scheduler-admin-token
# Keep provider credentials outside this candidate and inject them only at runtime.
# OPENROUTER_API_KEY must be provided through an approved secret-injection path.
"@ | Set-Content -Path $candidate -Encoding utf8
Write-Output ('CANDIDATE='+$candidate)
Write-Output ('SECRET_FILES_CREATED=3')
Write-Output ('ENV_PRODUCTION_UNCHANGED='+(-not (Test-Path (Join-Path $Private ('env-production-before-'+$stamp+'.bak')))))
