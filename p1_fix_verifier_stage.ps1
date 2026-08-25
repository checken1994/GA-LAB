param([string]$Root = 'C:\Users\check\Downloads\scp')
$ErrorActionPreference = 'Stop'
$p = Join-Path $Root 'scp\api_server.py'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Copy-Item $p ($p + '.bak-before-p1-verifier-stage-fix-' + $stamp) -Force
$lines = New-Object 'System.Collections.Generic.List[string]'
foreach ($line in (Get-Content -LiteralPath $p)) { [void]$lines.Add([string]$line) }
$stage = '    stage_request(request, "verifier_completed", verdict=v.verdict, governance_decision=v.evidence.get("governance_decision", ""))'
$stageIndex = -1
for ($i=0; $i -lt $lines.Count; $i++) { if ($lines[$i] -eq $stage) { $stageIndex=$i; break } }
if ($stageIndex -lt 0) { throw 'verifier_completed line missing' }
$lines.RemoveAt($stageIndex)
$elseIndex = -1
for ($i=$stageIndex; $i -lt $lines.Count; $i++) { if ($lines[$i] -eq '    else:') { $elseIndex=$i; break } }
if ($elseIndex -lt 0) { throw 'else line missing' }
$closeIndex = -1
for ($i=$elseIndex+1; $i -lt $lines.Count; $i++) { if ($lines[$i] -eq '        )' -and $i+1 -lt $lines.Count -and $lines[$i+1].Trim() -eq '') { $closeIndex=$i; break } }
if ($closeIndex -lt 0) { throw 'else branch close missing' }
[void]$lines.Insert($closeIndex+1, $stage)
[IO.File]::WriteAllLines($p, $lines, (New-Object Text.UTF8Encoding($false)))
Write-Output 'VERIFIER_STAGE_MOVED=True'
Write-Output ('API_SHA256=' + (Get-FileHash $p -Algorithm SHA256).Hash)
