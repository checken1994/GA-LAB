$ErrorActionPreference = 'Stop'
try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/api/scp/health' -Method Get -TimeoutSec 10
    $o = $r.Content | ConvertFrom-Json
    Write-Output ('http=' + [int]$r.StatusCode)
    Write-Output ('overall=' + [bool]$o.overall)
    Write-Output ('scp=' + [string]$o.scp)
    foreach($name in @('fastapi','loopScheduler','llmBridge')){
        $v=$o.$name
        if($null -eq $v){Write-Output ($name + '=missing');continue}
        $status='missing'; $ok='missing'
        if($v.PSObject.Properties.Name -contains 'status'){$status=[string]$v.status}
        if($v.PSObject.Properties.Name -contains 'ok'){$ok=[bool]$v.ok}
        $errorClass='none'
        if($v.PSObject.Properties.Name -contains 'error' -and $null -ne $v.error){
            $errorClass='other'
            $errText=[string]$v.error
            if($errText -match '(?i)fetch failed|econnrefused|enotfound|eai_again|timeout|connect'){ $errorClass='network_or_timeout' }
        }
        Write-Output ($name + ';ok=' + $ok + ';status=' + $status + ';error_class=' + $errorClass)
    }
} catch {
    $code='ERROR'
    $o=$null
    try {
        if($null -ne $_.Exception.Response){
            $code=[int]$_.Exception.Response.StatusCode
            $stream=$_.Exception.Response.GetResponseStream()
            $reader=[IO.StreamReader]::new($stream)
            $body=$reader.ReadToEnd()
            $reader.Dispose(); $stream.Dispose()
            try{$o=$body | ConvertFrom-Json}catch{$o=$null}
        }
    } catch {}
    Write-Output ('http=' + $code)
    if($null -eq $o){Write-Output 'body_parse=FAIL'; exit 0}
    Write-Output ('body_parse=PASS')
    Write-Output ('overall=' + [bool]$o.overall)
    Write-Output ('scp=' + [string]$o.scp)
    foreach($name in @('fastapi','loopScheduler','llmBridge')){
        $v=$o.$name
        if($null -eq $v){Write-Output ($name + '=missing');continue}
        $status='missing'; $ok='missing'
        if($v.PSObject.Properties.Name -contains 'status'){$status=[string]$v.status}
        if($v.PSObject.Properties.Name -contains 'ok'){$ok=[bool]$v.ok}
        $errorClass='none'
        if($v.PSObject.Properties.Name -contains 'error' -and $null -ne $v.error){
            $errorClass='other'
            $errText=[string]$v.error
            if($errText -match '(?i)fetch failed|econnrefused|enotfound|eai_again|timeout|connect'){ $errorClass='network_or_timeout' }
        }
        Write-Output ($name + ';ok=' + $ok + ';status=' + $status + ';error_class=' + $errorClass)
    }
}
