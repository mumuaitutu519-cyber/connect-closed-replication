#!/usr/bin/env python3
"""Bounded preregistered literature discovery. Store original API responses, no bypass."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[k]='1'
from pathlib import Path
import json, urllib.request, urllib.parse, datetime, hashlib, concurrent.futures, re
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'meta/literature_raw'
OUT.mkdir(parents=True, exist_ok=True)
def query(name,url):
    at=datetime.datetime.now(datetime.timezone.utc).isoformat()
    req=urllib.request.Request(url,headers={'User-Agent':'266-connect-closed-research/1.0 (academic metadata retrieval)','Accept':'application/json, application/atom+xml, text/html'})
    path=OUT/(name+'.txt')
    try:
        with urllib.request.urlopen(req,timeout=50) as response:
            body=response.read(16*1024*1024)
            status=response.status
        path.write_bytes(body)
        return dict(name=name,url=url,retrieved_utc=at,status=status,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),path=str(path))
    except Exception as exc:
        return dict(name=name,url=url,retrieved_utc=at,status='FAILED',error=str(exc),policy='No access-control bypass or repeated alternate identities')
def main():
    queries=[]
    terms=['Stock Connect holiday','northbound trading closure liquidity','foreign investors absence China market quality','Stock Connect liquidity price efficiency']
    for n,t in enumerate(terms):
        queries.append((f'crossref_{n}','https://api.crossref.org/works?'+urllib.parse.urlencode({'query':t,'filter':'from-pub-date:2010-01-01,until-pub-date:2026-11-07','rows':50,'select':'DOI,title,author,published,abstract,URL,type'})))
        queries.append((f'openalex_{n}','https://api.openalex.org/works?'+urllib.parse.urlencode({'search':t,'filter':'from_publication_date:2010-01-01,to_publication_date:2026-11-07','per-page':50,'sort':'publication_date:desc'})))
    queries += [('arxiv','https://export.arxiv.org/api/query?'+urllib.parse.urlencode({'search_query':'all:"Stock Connect" OR (all:northbound AND all:stock) OR (all:"foreign investors" AND all:holiday)','start':0,'max_results':50,'sortBy':'submittedDate','sortOrder':'descending'})),('ssrn','https://papers.ssrn.com/sol3/results.cfm?'+urllib.parse.urlencode({'txtKey_Words':'Stock Connect holiday northbound'}))]
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        receipts=list(pool.map(query,*zip(*queries)))
    (ROOT/'meta/literature_receipts.json').write_text(json.dumps(receipts,indent=2,ensure_ascii=False))
    records=[]
    for r in receipts:
        if r['status']!=200:continue
        if r['name'].startswith('crossref'):
            d=json.loads(Path(r['path']).read_text())
            for a in d['message']['items']:
                records.append(dict(source=r['name'],title='; '.join(a.get('title',[])),doi=a.get('DOI'),date=a.get('published',{}).get('date-parts'),abstract=re.sub('<[^>]+>',' ',a.get('abstract','')),url=a.get('URL')))
        elif r['name'].startswith('openalex'):
            d=json.loads(Path(r['path']).read_text())
            for a in d.get('results',[]):
                inv=a.get('abstract_inverted_index') or {}; words={n:w for w,ns in inv.items() for n in ns}
                abstract=' '.join(words[n] for n in sorted(words))
                records.append(dict(source=r['name'],title=a.get('title'),doi=a.get('doi'),date=a.get('publication_date'),abstract=abstract,url=a.get('id'),locations=a.get('locations')))
    (ROOT/'meta/literature_candidates.json').write_text(json.dumps(records,indent=2,ensure_ascii=False))
    print(json.dumps(receipts,ensure_ascii=False,indent=2))
    seen=set()
    for r in records:
        title=r['title'] or ''
        if title.lower() in seen: continue
        seen.add(title.lower())
        full=(title+' '+r['abstract']).lower()
        if any(w in full for w in ['holiday','absence','nonoverlap','non-overlap','closure','suspend','suspension','day off']):
            print(json.dumps({k:v for k,v in r.items() if k!='locations'},ensure_ascii=False))
if __name__=='__main__': main()
