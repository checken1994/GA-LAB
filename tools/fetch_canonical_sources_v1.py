import json,requests,datetime,concurrent.futures
from pathlib import Path
ROOT=Path(r'C:\Users\check\Downloads\scp');SRC=ROOT/'data'/'rag_normalized_source_candidates_v1_20260817.jsonl';OUT=ROOT/'data'/'rag_canonical_fetch_results_v1_20260817.jsonl'
rows=[json.loads(x) for x in SRC.read_text(encoding='utf-8').splitlines() if x.strip()]
def one(r):
 c=(r.get('candidate_sources') or [{}])[0];u=c.get('canonical_url_candidate','');res={'question_id':r.get('question_id'),'question':r.get('question'),'canonical_url':u,'fetch_status':'NO_URL','http_status':None,'final_url':'','content_type':'','title':'','text_preview':'','fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 if not u:return res
 try:
  h=requests.get(u,timeout=20,headers={'User-Agent':'SCP-Canonical-Fetch/1.0'},allow_redirects=True)
  res.update({'fetch_status':'FETCHED' if h.ok else 'HTTP_ERROR','http_status':h.status_code,'final_url':h.url,'content_type':h.headers.get('content-type','')})
  if h.ok and 'text' in h.headers.get('content-type',''):
   t=h.text[:500000];res['text_preview']=t[:2000]
   import re
   m=re.search(r'<title[^>]*>(.*?)</title>',t,re.I|re.S);res['title']=re.sub(r'\s+',' ',m.group(1)).strip()[:300] if m else ''
 except Exception as e:res.update({'fetch_status':'FETCH_ERROR','error':type(e).__name__+': '+str(e)[:200]})
 return res
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:out=list(ex.map(one,rows))
OUT.write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in out)+'\n',encoding='utf-8')
from collections import Counter
print(json.dumps({'rows':len(out),'status':dict(Counter(x['fetch_status'] for x in out)),'output':str(OUT)},ensure_ascii=False))
