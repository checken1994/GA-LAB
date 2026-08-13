$ErrorActionPreference = 'Stop'
$path = 'C:\Users\check\Downloads\scp\scp\api_server.py'
$text = Get-Content $path -Raw -Encoding UTF8
$marker = '# SCP Hands v3.2 — action fabric'
if ($text.Contains($marker)) {
    Write-Output 'routerAlreadyRegistered=True'
    exit 0
}
$block = @'

# SCP Hands v3.2 — action fabric
try:
    from scp.api.routes.hands_routes import router as hands_router
    app.include_router(hands_router)
    _HANDS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"[SCP Hands v3.2] Hands router unavailable: {e}")
    _HANDS_AVAILABLE = False
'@
$text = $text.TrimEnd() + $block + "`r`n"
[System.IO.File]::WriteAllText($path, $text, [System.Text.UTF8Encoding]::new($false))
Write-Output 'routerRegistered=True'
