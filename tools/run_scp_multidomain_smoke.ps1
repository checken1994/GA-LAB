$ErrorActionPreference='Continue'
$cases=@(
 @{id='MATH-1';domain='math';question='What is 2 + 2? Answer briefly and show the arithmetic.'},
 @{id='HISTORY-1';domain='history';question='Who was the first president of the United States? Answer with a source if available.'},
 @{id='BIOLOGY-1';domain='biology';question='What is the main function of red blood cells? Answer briefly and cite evidence if available.'},
 @{id='LAW-1';domain='legal';question='What is a contract in general legal terms? Give a concise definition and say when evidence is missing.'},
 @{id='FINANCE-1';domain='finance';question='What is compound interest? Give the formula conceptually and do not invent current rates.'},
 @{id='TECH-1';domain='tech';question='What is a URL canonical link? Explain briefly and distinguish it from a search redirect.'},
 @{id='LANG-1';domain='language';question='What is the difference between a noun and a verb in English grammar?'},
 @{id='GENERAL-1';domain='general';question='Explain why a verified source URL is needed for a factual RAG answer.'}
)
$out=@();foreach($c in $cases){$body=@{question=$c.question;domain=$c.domain;return_evidence=$true;include_sources=$true}|ConvertTo-Json;try{$r=Invoke-RestMethod -Uri 'http://127.0.0.1:8000/ask' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 120;$out+=([ordered]@{id=$c.id;domain=$c.domain;question=$c.question;verdict=$r.verdict;run_status=$r.run_status;governance_decision=$r.governance_decision;confidence=$r.confidence;answer=$r.final_answer;trace_id=$r.trace_id;run_id=$r.run_id;elapsed_ms=$r.elapsed_ms;slm_trace=$r.slm_trace})}catch{$out+=([ordered]@{id=$c.id;domain=$c.domain;question=$c.question;verdict='REQUEST_ERROR';error=$_.Exception.Message})}}
$out|ConvertTo-Json -Depth 12|Set-Content 'C:\Users\check\Downloads\scp\reports\SCP_MULTIDOMAIN_SMOKE_BRIDGE_2026-08-17.json' -Encoding UTF8;$out|Select-Object id,domain,verdict,run_status,confidence,elapsed_ms|Format-Table -AutoSize
