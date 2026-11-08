from fetch_literature import query,ROOT
import urllib.parse,json,xml.etree.ElementTree as ET
if __name__=='__main__':
 rs=[]
 for n,t in enumerate(['"Stock Connect"','"nonoverlapping holidays"','"northbound" "liquidity"','"Stock Connect" "holiday"']):
  u='https://api.openalex.org/works?'+urllib.parse.urlencode({'search':t,'filter':'from_publication_date:2010-01-01,to_publication_date:2026-11-07','per-page':100,'sort':'publication_date:desc'})
  r=query(f'openalex_targeted_{n}',u);rs.append(r)
  if r['status']==200:
   for a in json.loads(open(r['path']).read()).get('results',[]):
    inv=a.get('abstract_inverted_index') or {};w={i:k for k,ii in inv.items() for i in ii};abstract=' '.join(w[i] for i in sorted(w))
    if any(x in (a['title']+' '+abstract).lower() for x in ['liquidity','efficiency','holiday','absence','market quality','price discovery','northbound']): print(json.dumps(dict(title=a['title'],date=a['publication_date'],doi=a['doi'],abstract=abstract,locations=a['locations']),ensure_ascii=False))
 p=ROOT/'meta/literature_receipts.json';p.write_text(json.dumps(json.loads(p.read_text())+rs,indent=2))
