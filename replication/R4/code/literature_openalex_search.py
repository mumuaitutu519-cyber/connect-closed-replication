"""Independent, bounded OpenAlex search in the five preregistered journals."""
from common import *
from literature import get,JOURNALS,TERMS,clean,excerpt
import concurrent.futures as cf,urllib.parse,re
def main():
 jobs=[('oa_journal_'+str(i),'https://api.openalex.org/sources/issn:'+issn) for i,(journal,issn) in enumerate(JOURNALS)]
 with cf.ThreadPoolExecutor(max_workers=4) as pool:source_receipts=list(pool.map(get,jobs))
 queries=[]
 for rec in source_receipts:
  if rec['status']!=200:continue
  i=int(rec['name'].split('_')[-1]);a=json.loads(Path(rec['path']).read_text());sid=a.get('id','').split('/')[-1]
  if not sid.startswith('S'):continue
  for j,term in enumerate(TERMS):queries.append((f'oa_search_{i}_{j}','https://api.openalex.org/works?'+urllib.parse.urlencode({'search':term,'filter':f'from_publication_date:2019-01-01,to_publication_date:2026-11-07,primary_location.source.id:{sid}','per-page':50,'sort':'publication_date:desc'})))
 with cf.ThreadPoolExecutor(max_workers=4) as pool:receipts=list(pool.map(get,queries))
 pattern=re.compile(r'foreign (?:institutional |portfolio )?investor|foreign institutional ownership|stock connect|capital.market liberaliz|international institutional investor',re.I);rows={}
 for rec in receipts:
  if rec['status']!=200:continue
  i=int(rec['name'].split('_')[2]);journal=JOURNALS[i][0]
  for a in json.loads(Path(rec['path']).read_text()).get('results',[]):
   doi=(a.get('doi') or '').removeprefix('https://doi.org/').lower()
   if not doi or a.get('type') not in ['article','review']:continue
   inv=a.get('abstract_inverted_index') or {};words={n:w for w,ns in inv.items() for n in ns};abstract=' '.join(words[n] for n in sorted(words));title=clean(a.get('title'));text=title+' '+abstract;hits=pattern.findall(text)
   if not hits and re.search('liability of foreignness',text,re.I) and re.search('capital market|stock market|securit|portfolio|institutional invest|equity market',text,re.I):hits=['liability of foreignness in capital markets']
   yr=int(a.get('publication_year') or 0)
   if not hits or not 2019<=yr<=2026:continue
   bib=a.get('biblio') or {};first=bib.get('first_page') or '';last=bib.get('last_page') or '';pages=first+'-'+last if first and last and first!=last else first
   rows[doi]=dict(title=title,authors='; '.join(z['author']['display_name'] for z in a.get('authorships',[])),journal=journal,year=yr,volume=bib.get('volume',''),issue=bib.get('issue',''),pages=pages,article_number='',doi=doi,url='https://doi.org/'+doi,abstract_300=excerpt(abstract),abstract_extract_rule='first 25 words, at most 300 characters',abstract_status='AVAILABLE_OPENALEX_SEARCH' if abstract else 'MISSING_OPENALEX_SEARCH',search_journal=journal,matched_keywords='; '.join(sorted(set(hits))),selection='direct title/abstract keyword match; newest first; max ten per journal',openalex_id=a.get('id'),metadata_source='OpenAlex journal-filtered independent search')
 columns=['title','authors','journal','year','volume','issue','pages','article_number','doi','url','abstract_300','abstract_extract_rule','abstract_status','search_journal','matched_keywords','selection','openalex_id','metadata_source'];pd.DataFrame(list(rows.values()),columns=columns).to_csv(R/'meta/openalex_search_candidates.csv',index=False);save(source_receipts+receipts,'literature_openalex_search_receipts.csv');print('OPENALEX INDEPENDENT MATCHES',len(rows),flush=True)
if __name__=='__main__':main()
