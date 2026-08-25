param(
    [string]$Root = 'C:\Users\check\Downloads\scp'
)
$ErrorActionPreference = 'Stop'
$nl = "`n"
$api = Join-Path $Root 'scp\api_server.py'
$helpers = Join-Path $Root 'scp\api_server_parts\helpers.py'
foreach ($path in @($api, $helpers)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "missing target: $path" }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Copy-Item -LiteralPath $path -Destination ($path + '.bak-before-p1-ledger-' + $stamp) -Force
}

function Replace-Once([string]$text, [string]$old, [string]$new, [string]$label) {
    $count = ([regex]::Matches($text, [regex]::Escape($old))).Count
    if ($count -ne 1) { throw "$label expected 1 match, got $count" }
    return $text.Replace($old, $new)
}

$h = [IO.File]::ReadAllText($helpers)
$oldH = '    session_id: str' + $nl + '    # V105: Full pipeline trace'
$newH = '    session_id: str' + $nl + '    # P1: Durable request-level identity and terminal status.' + $nl + '    run_id: str | None = None' + $nl + '    trace_id: str | None = None' + $nl + '    run_status: str | None = None' + $nl + '    ledger_status: str | None = None' + $nl + '    # V105: Full pipeline trace'
$h = Replace-Once $h $oldH $newH 'AskResponse fields'
[IO.File]::WriteAllText($helpers, $h, (New-Object Text.UTF8Encoding($false)))

$a = [IO.File]::ReadAllText($api)
$oldImport = '    get_judge,' + $nl + ')' + $nl + $nl + 'logging.basicConfig'
$newImport = '    get_judge,' + $nl + ')' + $nl + 'from scp.core.request_run_ledger import RequestRunLedger, stage_request, traced_request' + $nl + $nl + '_REQUEST_RUN_LEDGER = RequestRunLedger()' + $nl + $nl + 'logging.basicConfig'
$a = Replace-Once $a $oldImport $newImport 'ledger import'
$oldDecorator = '@app.post("/ask", response_model=AskResponse)' + $nl + 'async def ask(req: AskRequest, request: Request):'
$newDecorator = '@app.post("/ask", response_model=AskResponse)' + $nl + '@traced_request(_REQUEST_RUN_LEDGER)' + $nl + 'async def ask(req: AskRequest, request: Request):'
$a = Replace-Once $a $oldDecorator $newDecorator 'ask decorator'
$oldJudge = '    judge = get_judge()' + $nl + '    v98_context = _extract_v98_context(request)'
$newJudge = '    judge = get_judge()' + $nl + '    stage_request(request, "judge_ready")' + $nl + '    v98_context = _extract_v98_context(request)'
$a = Replace-Once $a $oldJudge $newJudge 'judge stage'
$oldStart = '    # [OPT-8/9] Use async judge with ReActAgent fallback.' + $nl + '    # Was: asyncio.to_thread(judge.judge, ...) — blocked event loop thread.'
$newStart = '    # [OPT-8/9] Use async judge with ReActAgent fallback.' + $nl + '    stage_request(request, "verifier_started")' + $nl + '    # Was: asyncio.to_thread(judge.judge, ...) — blocked event loop thread.'
$a = Replace-Once $a $oldStart $newStart 'verifier start stage'
$oldDone = '            v98_context=v98_context,' + $nl + '        )' + $nl + '    else:'
$newDone = '            v98_context=v98_context,' + $nl + '        )' + $nl + '    stage_request(request, "verifier_completed", verdict=v.verdict, governance_decision=v.evidence.get("governance_decision", ""))' + $nl + '    else:'
$a = Replace-Once $a $oldDone $newDone 'verifier completion stage'
$oldBoundary = '    if _web_fallback_used:' + $nl + '        _api_slm_trace.append({'
$newBoundary = '    stage_request(request, "response_boundary", verdict=v.verdict, governance_decision=_gov_decision)' + $nl + '    if _web_fallback_used:' + $nl + '        _api_slm_trace.append({'
$a = Replace-Once $a $oldBoundary $newBoundary 'response stage'
[IO.File]::WriteAllText($api, $a, (New-Object Text.UTF8Encoding($false)))
Write-Output 'PATCHED=True'
Write-Output ('API_SHA256=' + (Get-FileHash $api -Algorithm SHA256).Hash)
Write-Output ('HELPERS_SHA256=' + (Get-FileHash $helpers -Algorithm SHA256).Hash)
