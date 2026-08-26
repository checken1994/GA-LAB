param(
  [string]$RepoA = '',
  [string]$RepoB = '',
  [string]$OutputDir = ''
)
$ErrorActionPreference = 'Stop'
$CanonicalRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($RepoB)) { $RepoB = $CanonicalRoot }
if ([string]::IsNullOrWhiteSpace($OutputDir)) { $OutputDir = Join-Path $CanonicalRoot 'reports/core_repo_matrix_latest' }
if ([string]::IsNullOrWhiteSpace($RepoA)) { throw 'RepoA is required. Pass -RepoA <path-to-read-only-source-repo>; retired workspace defaults were removed.' }
if ($RepoA -match '(?i)(scp-agent-structure-debt|scp-structure-debt-worktree)') { throw 'RepoA points to a retired workspace name; pass the intended read-only source checkout explicitly.' }
foreach ($repo in @($RepoA, $RepoB)) {
  if (-not (Test-Path -LiteralPath $repo -PathType Container)) { throw "Repository path does not exist: $repo" }
  if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) { throw "Repository is not a Git checkout: $repo" }
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
function Get-TreeMap([string]$Repo) {
  $map = @{}
  $lines = @( & git -C $Repo ls-files -s )
  if ($LASTEXITCODE -ne 0) { throw "git ls-files failed for $Repo" }
  foreach ($line in $lines) {
    if ($line -match '^\S+\s+([0-9a-f]+)\s+\d+\s+(.*)$') { $map[$Matches[2]] = $Matches[1] }
  }
  if ($map.Count -eq 0) { throw "empty tracked-file inventory for $Repo" }
  return $map
}
function Classify([string]$Path) {
  if ($Path -match '(?i)(task_kernel|ask_kernel_adapter|trace_ledger|verifier|recovery_manager|capability_guard)') { return 'kernel' }
  if ($Path -match '(?i)(api_server|api/|runtime/|dashboard/|llm_gateway|retriever|security/|autofix|scheduler|storage|requirements|pyproject|package\.json|package-lock)') { return 'stack' }
  return 'common-core'
}
$a = Get-TreeMap $RepoA
$b = Get-TreeMap $RepoB
$common = @($a.Keys | Where-Object { $b.ContainsKey($_) } | Sort-Object)
$onlyA = @($a.Keys | Where-Object { -not $b.ContainsKey($_) } | Sort-Object)
$onlyB = @($b.Keys | Where-Object { -not $a.ContainsKey($_) } | Sort-Object)
$rows = @(
  foreach ($path in $common) {
    $equal = ($a[$path] -eq $b[$path])
    $class = Classify $path
    [pscustomobject]@{ path=$path; classification=$class; scp_agent_blob=$a[$path]; ga_lab_blob=$b[$path]; blob_equal=$equal; decision=if($equal){'SHARED_IDENTICAL_KEEP_ONE'}elseif($class -eq 'kernel'){'SHARED_KERNEL_REVIEW_BEFORE_PORT'}elseif($class -eq 'stack'){'SHARED_STACK_MERGE_REVIEW'}else{'SHARED_DIFF_REVIEW'} }
  }
)
$summary = [pscustomobject]@{
  generated_at=(Get-Date).ToString('o'); repo_a=$RepoA; repo_a_head=(& git -C $RepoA rev-parse HEAD).Trim(); repo_b=$RepoB; repo_b_head=(& git -C $RepoB rev-parse HEAD).Trim(); repo_a_tracked=$a.Count; repo_b_tracked=$b.Count; common_paths=$common.Count; common_blob_identical=@($rows|Where-Object {$_.blob_equal}).Count; common_blob_different=@($rows|Where-Object {-not $_.blob_equal}).Count; only_scp_agent=$onlyA.Count; only_ga_lab=$onlyB.Count; shared_kernel_paths=@($rows|Where-Object {$_.classification -eq 'kernel'}).Count; shared_stack_paths=@($rows|Where-Object {$_.classification -eq 'stack'}).Count; kernel_only_scp_agent=@($onlyA|Where-Object {$_ -match '(?i)(task_kernel|ask_kernel_adapter|trace_ledger|verifier|recovery_manager|capability_guard)'}).Count; stack_only_ga_lab=@($onlyB|Where-Object {$_ -match '(?i)(api_server|api/|runtime/|dashboard/|llm_gateway|retriever|security/|autofix|scheduler|storage)'}).Count
}
$summary|ConvertTo-Json -Depth 6|Set-Content (Join-Path $OutputDir 'summary.json') -Encoding UTF8
$rows|ConvertTo-Json -Depth 6|Set-Content (Join-Path $OutputDir 'common_paths.json') -Encoding UTF8
[pscustomobject]@{path=$onlyA;repo='scp-agent';category='only-in-scp-agent'}|ConvertTo-Json -Depth 4|Set-Content (Join-Path $OutputDir 'only_scp_agent.json') -Encoding UTF8
[pscustomobject]@{path=$onlyB;repo='GA-LAB';category='only-in-ga-lab'}|ConvertTo-Json -Depth 4|Set-Content (Join-Path $OutputDir 'only_ga_lab.json') -Encoding UTF8
$md=@('# Core Repository Matrix — scp-agent vs GA-LAB','','> Generated: '+$summary.generated_at,'','| Metric | Value |','|---|---:|');foreach($p in @('repo_a_head','repo_b_head','repo_a_tracked','repo_b_tracked','common_paths','common_blob_identical','common_blob_different','only_scp_agent','only_ga_lab','shared_kernel_paths','shared_stack_paths','kernel_only_scp_agent','stack_only_ga_lab')){$md+=("| $p | $($summary.$p) |")};$md+=('','## Merge rule','','A shared path is not assumed to be the same implementation. Blob-identical paths are kept as one logical file; differing paths require review. Kernel-only files are not copied blindly into GA-LAB. GA-LAB stack files are treated as the integration surface.','','## Common paths requiring review','','| Path | Class | Blob equal | Decision |','|---|---|---:|---|');foreach($r in ($rows|Where-Object {-not $_.blob_equal}|Select-Object -First 220)){$md+=("| ``$($r.path)`` | $($r.classification) | $($r.blob_equal) | $($r.decision) |")};$md -join "`n"|Set-Content (Join-Path $OutputDir 'CORE_REPO_MATRIX.md') -Encoding UTF8
Write-Output ($summary|ConvertTo-Json -Compress)
