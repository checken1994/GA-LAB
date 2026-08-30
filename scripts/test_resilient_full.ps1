$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$body = @{
    question = 'SCP_FULL_FALLBACK_TEST: reply with one short sentence'
    providers = @('local_llm', 'chatgpt', 'claude', 'gemini')
    approved = $true
    useBrowser = $true
    allowLocal = $true
} | ConvertTo-Json -Depth 4

try {
    $result = Invoke-RestMethod 'http://127.0.0.1:8000/v3/ai/ask-resilient' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 180
    Write-Output ('resilientSuccess=' + $result.success)
    Write-Output ('successfulAI=' + (($result.successfulAIProviders) -join ','))
    Write-Output ('webSuccess=' + $result.webSearch.success)
    Write-Output ('webResultCount=' + @($result.webSearch.results).Count)
    foreach ($item in @($result.aiResults)) {
        $provider = $item.provider
        $providerResult = $item.result
        $answer = if ($providerResult.answer) { [string]$providerResult.answer } elseif ($providerResult.text) { [string]$providerResult.text } else { '' }
        if ($answer.Length -gt 500) { $answer = $answer.Substring(0, 500) }
        Write-Output ('provider=' + $provider + '|success=' + $providerResult.success + '|method=' + $providerResult.method + '|error=' + $providerResult.error + '|answer=' + $answer.Replace("`r", ' ').Replace("`n", ' '))
    }
} catch {
    Write-Output ('resilientError=' + $_.Exception.Message)
    exit 3
}
