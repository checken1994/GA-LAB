param(
    [string]$Root = 'C:\Users\check\Downloads\scp'
)
$ErrorActionPreference = 'Stop'
$api = Join-Path $Root 'scp\api_server.py'
$helpers = Join-Path $Root 'scp\api_server_parts\helpers.py'

function Backup-Once([string]$path) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Copy-Item -LiteralPath $path -Destination ($path + '.bak-before-p1-ledger-v2-' + $stamp) -Force
}
function Find-Line([System.Collections.Generic.List[string]]$items, [string]$needle, [int]$start = 0) {
    for ($i=$start; $i -lt $items.Count; $i++) { if ($items[$i] -eq $needle) { return $i } }
    return -1
}
function Insert-Once([System.Collections.Generic.List[string]]$items, [int]$index, [string]$text, [string]$label) {
    if ($index -lt 0) { throw "$label insertion index missing" }
    [void]$items.Insert($index, $text)
}
if (-not (Test-Path $api) -or -not (Test-Path $helpers)) { throw 'P1 API targets missing' }

# Helpers: tolerate the first attempt having already written these fields.
$hLines = New-Object 'System.Collections.Generic.List[string]'
foreach ($line in (Get-Content -LiteralPath $helpers)) { [void]$hLines.Add([string]$line) }
if ((Find-Line $hLines '    run_id: str | None = None') -lt 0) {
    Backup-Once $helpers
    $sid = Find-Line $hLines '    session_id: str'
    Insert-Once $hLines ($sid + 1) '    # P1: Durable request-level identity and terminal status.' 'AskResponse identity'
    Insert-Once $hLines ($sid + 2) '    run_id: str | None = None' 'run_id'
    Insert-Once $hLines ($sid + 3) '    trace_id: str | None = None' 'trace_id'
    Insert-Once $hLines ($sid + 4) '    run_status: str | None = None' 'run_status'
    Insert-Once $hLines ($sid + 5) '    ledger_status: str | None = None' 'ledger_status'
    [IO.File]::WriteAllLines($helpers, $hLines, (New-Object Text.UTF8Encoding($false)))
}

# API route source: line-based edits avoid CRLF/UTF-8 comment mismatch.
$aLines = New-Object 'System.Collections.Generic.List[string]'
foreach ($line in (Get-Content -LiteralPath $api)) { [void]$aLines.Add([string]$line) }
Backup-Once $api

if ((Find-Line $aLines 'from scp.core.request_run_ledger import RequestRunLedger, stage_request, traced_request') -lt 0) {
    $getJudge = Find-Line $aLines '    get_judge,'
    if ($getJudge -lt 0) { throw 'get_judge import line missing' }
    $close = Find-Line $aLines ')' ($getJudge + 1)
    if ($close -lt 0) { throw 'helpers import close missing' }
    Insert-Once $aLines ($close + 1) 'from scp.core.request_run_ledger import RequestRunLedger, stage_request, traced_request' 'ledger import'
    Insert-Once $aLines ($close + 2) '' 'ledger import spacer'
    Insert-Once $aLines ($close + 3) '_REQUEST_RUN_LEDGER = RequestRunLedger()' 'ledger singleton'
    Insert-Once $aLines ($close + 4) '' 'ledger singleton spacer'
}
$askDecorator = Find-Line $aLines '@app.post("/ask", response_model=AskResponse)'
if ($askDecorator -lt 0) { throw 'ask decorator missing' }
if ((Find-Line $aLines '@traced_request(_REQUEST_RUN_LEDGER)' $askDecorator) -lt 0) {
    Insert-Once $aLines ($askDecorator + 1) '@traced_request(_REQUEST_RUN_LEDGER)' 'ask decorator'
}
$askStart = Find-Line $aLines 'async def ask(req: AskRequest, request: Request):'
if ($askStart -lt 0) { throw 'ask function missing' }
$judgeLine = Find-Line $aLines '    judge = get_judge()' $askStart
if ($judgeLine -lt 0) { throw 'ask judge line missing' }
if ((Find-Line $aLines '    stage_request(request, "judge_ready")' $judgeLine) -lt 0) {
    Insert-Once $aLines ($judgeLine + 1) '    stage_request(request, "judge_ready")' 'judge stage'
}
$verifierIf = Find-Line $aLines '    if hasattr(judge, "judge_with_react_fallback"):' $askStart
if ($verifierIf -lt 0) { throw 'verifier if missing' }
if ((Find-Line $aLines '    stage_request(request, "verifier_started")' $verifierIf) -lt 0) {
    Insert-Once $aLines $verifierIf '    stage_request(request, "verifier_started")' 'verifier start'
    $verifierIf += 1
}
$verifierClose = -1
for ($i=$verifierIf + 1; $i -lt $aLines.Count; $i++) {
    if ($aLines[$i] -eq '        )' -and $i + 1 -lt $aLines.Count -and $aLines[$i+1] -eq '    else:') { $verifierClose = $i; break }
}
if ($verifierClose -lt 0) { throw 'verifier close missing' }
if ((Find-Line $aLines '    stage_request(request, "verifier_completed", verdict=v.verdict, governance_decision=v.evidence.get("governance_decision", ""))' $verifierClose) -lt 0) {
    Insert-Once $aLines ($verifierClose + 1) '    stage_request(request, "verifier_completed", verdict=v.verdict, governance_decision=v.evidence.get("governance_decision", ""))' 'verifier complete'
}
$boundaryIf = -1
for ($i=$askStart; $i -lt $aLines.Count; $i++) {
    if ($aLines[$i] -eq '    if _web_fallback_used:') { $boundaryIf = $i; break }
}
if ($boundaryIf -lt 0) { throw 'response boundary missing' }
if ((Find-Line $aLines '    stage_request(request, "response_boundary", verdict=v.verdict, governance_decision=_gov_decision)' $boundaryIf) -lt 0) {
    Insert-Once $aLines $boundaryIf '    stage_request(request, "response_boundary", verdict=v.verdict, governance_decision=_gov_decision)' 'response boundary'
}
[IO.File]::WriteAllLines($api, $aLines, (New-Object Text.UTF8Encoding($false)))
Write-Output 'PATCHED=True'
Write-Output ('API_SHA256=' + (Get-FileHash $api -Algorithm SHA256).Hash)
Write-Output ('HELPERS_SHA256=' + (Get-FileHash $helpers -Algorithm SHA256).Hash)
