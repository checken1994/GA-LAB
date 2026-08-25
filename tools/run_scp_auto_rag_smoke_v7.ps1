$cases=@(
 @{id='HISTORY';domain='history';question='Who was the first president of the United States?'},
 @{id='LAW';domain='legal';question='What is a contract in general legal terms?'},
 @{id='TECH';domain='tech';question='What is a canonical URL signal?'},
 @{id='UNKNOWN';domain='science';question='What is the main function of red blood cells?'}
);$out=@();foreach($c in $cases){$body=@{question=$c.question;domain=$c.domain;rag_enabled=$true;return_evidence=$true;include_sources=$true}|ConvertTo-Json;$r=Invoke-RestMethod -Uri 'http://127.0.0.1:8001/ask' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 120;$out+=([ordered]@{id=$c.id;domain=$c.domain;question=$c.question;verdict=$r.verdict;run_status=$r.run_status;confidence=$r.confidence;governance=$r.governance_decision;answer=$r.final_answer;trace_id=$r.trace_id;evidence=$r.v100_claims})};$out|ConvertTo-Json -Depth 12|Set-Content 'C:\Users\check\Downloads\scp\reports\SCP_AUTO_RAG_SMOKE_V7_2026-08-17.json' -Encoding UTF8;foreach($r in $out){Write-Output "$($r.id)|$($r.verdict)|$($r.run_status)|$($r.confidence)|$($r.answer.Substring(0,[Math]::Min(140,$r.answer.Length)))"}
