from common import *
import requests,urllib.parse,re,concurrent.futures as cf,time,html
OUT=R/'meta/literature_raw';OUT.mkdir(exist_ok=True)
TARGETS=[
 ('Bae Ozoguz Tan Wirjanto 2012 JFE','Bae Ozoguz Tan Wirjanto 2012 foreign investors stock price informativeness','Journal of Financial Economics',2012,['bae','ozoguz','tan','wirjanto']),
 ('Barclay Hendershott 2003 RFS','Barclay Hendershott 2003 price discovery trading after hours','The Review of Financial Studies',2003,['barclay','hendershott']),
 ('Chordia Roll Subrahmanyam 2008 JFE','Chordia Roll Subrahmanyam 2008 liquidity market efficiency','Journal of Financial Economics',2008,['chordia','roll','subrahmanyam']),
 ('Corwin Lipson 2000 JF','Corwin Lipson 2000 order flow around trading halts','The Journal of Finance',2000,['corwin','lipson']),
 ('Duffie 2010 JF','Duffie 2010 presidential address asset price dynamics slow moving capital','The Journal of Finance',2010,['duffie']),
 ('Hasbrouck 2003 JF','Hasbrouck 2003 intraday price formation US equity index markets','The Journal of Finance',2003,['hasbrouck']),
 ('Hou Moskowitz 2005 RFS','Hou Moskowitz 2005 market frictions price delay cross section expected returns','The Review of Financial Studies',2005,['hou','moskowitz']),
 ('Kacperczyk Sundaresan Wang 2021 RFS','Kacperczyk Sundaresan Wang 2021 foreign investors improve market efficiency','The Review of Financial Studies',2021,['kacperczyk','sundaresan','wang']),
 ('Lei Lu 2024 JAAF','Lei Lu 2024 foreign investors information Journal Accounting Auditing Finance','Journal of Accounting, Auditing & Finance',2024,['lei','lu']),
 ('Zhang 2025 JBF 107420','Zhang 2025 international information flow market quality 107420','Journal of Banking & Finance',2025,['zhang'])]
JOURNALS=[('International Business Review','0969-5931'),('Journal of International Business Studies','0047-2506'),('Journal of World Business','1090-9516'),('Journal of International Financial Markets, Institutions and Money','1042-4431'),('Journal of International Money and Finance','0261-5606')]
TERMS=['foreign investors','foreign institutional ownership','Stock Connect','capital market liberalization','liability of foreignness capital markets','information advantage foreign investors']
def get(job):
 name,url=job;p=OUT/(name+'.json');receipt=OUT/(name+'.receipt.json')
 if p.exists() and receipt.exists():
  cached=json.loads(receipt.read_text())
  if cached.get('url')==url:return cached
 rec=dict(name=name,url=url,retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 try:
  response=requests.get(url,timeout=40,headers={'User-Agent':'R4-connect-closed academic metadata verification/1.0','Accept':'application/json'});response.raise_for_status();p.write_bytes(response.content);rec.update(status=response.status_code,sha256=hashlib.sha256(response.content).hexdigest(),path=str(p))
 except Exception as e:rec.update(status='FAILED',error=str(e))
 js(receipt,rec);return rec
def year(a):
 for k in ['published-print','published','published-online','issued']:
  z=a.get(k,{}).get('date-parts',[])
  if z:return int(z[0][0])
 return None
def clean(x):return html.unescape(re.sub(r'\s+',' ',re.sub('<[^>]*>',' ',x or '')).strip())
def excerpt(x):
 # Bounded extract; metadata source response remains inspectable separately.
 return ' '.join(clean(x).split()[:25])[:300]
def metadata(a):
 return dict(title=clean('; '.join(a.get('title',[]))),authors='; '.join((' '.join([z.get('given',''),z.get('family','')])).strip() for z in a.get('author',[])),journal=clean('; '.join(a.get('container-title',[]))),year=year(a),online_year=(a.get('published-online',{}).get('date-parts') or [[None]])[0][0],print_year=(a.get('published-print',{}).get('date-parts') or [[None]])[0][0],volume=a.get('volume',''),issue=a.get('issue',''),pages=a.get('page',''),article_number=a.get('article-number',''),doi=a.get('DOI',''),url=a.get('URL',''),abstract_300=excerpt(a.get('abstract','')),abstract_extract_rule='first 25 words, at most 300 characters',abstract_status='AVAILABLE' if a.get('abstract') else 'MISSING_IN_CROSSREF')
def main():
 import subprocess
 subprocess.run([sys.executable,str(R/'code/literature_openalex_search.py')],check=True)
 jobs=[]
 for i,t in enumerate(TARGETS):jobs.append((f'verify_{i}', 'https://api.crossref.org/works?'+urllib.parse.urlencode({'query.bibliographic':t[1],'rows':8})))
 for i,(journal,issn) in enumerate(JOURNALS):
  for j,term in enumerate(TERMS):jobs.append((f'candidate_{i}_{j}','https://api.crossref.org/journals/'+issn+'/works?'+urllib.parse.urlencode({'query':term,'filter':'from-pub-date:2019-01-01,until-pub-date:2026-11-07','rows':30})))
 with cf.ThreadPoolExecutor(max_workers=4) as pool:receipts=list(pool.map(get,jobs))
 # Retry transient server/network failures once, without alternate identities.
 failed={r['name'] for r in receipts if r['status']!=200}
 if failed:
  with cf.ThreadPoolExecutor(max_workers=4) as pool:retry=list(pool.map(get,[j for j in jobs if j[0] in failed]))
  receiptmap={r['name']:r for r in receipts};receiptmap.update({r['name']:r for r in retry});receipts=list(receiptmap.values())
 save(receipts,'literature_api_receipts.csv');verified=[]
 for i,(given,query,journal,yr,authors) in enumerate(TARGETS):
  p=OUT/f'verify_{i}.json'
  if not p.exists():verified.append(dict(input_reference=given,status='API_UNAVAILABLE'));continue
  items=json.loads(p.read_text()).get('message',{}).get('items',[])
  def score(a):
   au=[z.get('family','').lower() for z in a.get('author',[])];ja=' '.join(a.get('container-title',[])).lower();return sum(any(n==x or n in x for x in au) for n in authors)*10+int(year(a)==yr)*4+int(journal.lower().replace('the ','') in ja.replace('the ',''))*5
  items.sort(key=score,reverse=True);a=items[0] if items else {};m=metadata(a);families=[z.get('family','').lower() for z in a.get('author',[])];m['input_reference']=given;m['crossref_query_url']=dict(jobs)[f'verify_{i}'];m['match_score']=score(a);dif=[]
  if families!=authors:dif.append('AUTHOR_ORDER_OR_COUNT: '+str(families)+' vs '+str(authors))
  if m['year']!=yr:dif.append('YEAR: '+str(m['year'])+' vs '+str(yr))
  if journal.lower().replace('the ','') not in m['journal'].lower().replace('the ',''):dif.append('JOURNAL: '+m['journal']+' vs '+journal)
  if i==9 and '107420' not in str(m.get('article_number'))+str(m.get('pages')):dif.append('ARTICLE_NUMBER differs from 107420')
  m['status']='VERIFIED_MATCH' if not dif else 'MISMATCH_OR_AMBIGUOUS';m['inconsistencies']='; '.join(dif);m['full_author_names_status']='INITIALS_ONLY_IN_CROSSREF' if any(len(re.sub('[^a-z]','',z.get('given','').lower()))<=2 for z in a.get('author',[])) else 'AS_REGISTERED_IN_CROSSREF';m['unprovided_fields']='Title, full given names, volume, issue, pages and DOI absent from input; recovered, not a comparison against manuscript bibliography';verified.append(m)
 for i,v in enumerate(verified):
  if not v.get('doi'):continue
  rec=get(('verify_oa_'+str(i),'https://api.openalex.org/works/https://doi.org/'+v['doi']))
  if rec['status']==200:
   a=json.loads(Path(rec['path']).read_text());v['author_names_openalex']='; '.join(x['author']['display_name'] for x in a.get('authorships',[]));v['author_name_note']='Crossref registered names retained; OpenAlex full display names supplied separately for initials expansion';v['openalex_id']=a.get('id');normal=lambda s:re.sub('[^a-z]','',s.lower());v['crossref_openalex_name_difference']=normal(v['authors'])!=normal(v['author_names_openalex']);v['name_difference_note']='Provider display names differ (initials, extra middle names, or given/family display order); do not silently replace Crossref author order' if v['crossref_openalex_name_difference'] else ''
 primary=pd.read_csv(R/'meta/author_name_primary_checks.csv') if (R/'meta/author_name_primary_checks.csv').exists() else pd.DataFrame()
 for v in verified:
  raw=v.get('authors','');v['authors_full_verified']=raw.title() if raw.isupper() else raw;v['full_given_names_source']='Crossref given/family author entries; registered middle initials preserved';v['title_crossref_raw']=v.get('title','')
  if len(primary):
   found=primary[primary.doi.str.lower().eq(str(v.get('doi','')).lower())]
   if len(found):
    row=found.iloc[0];v['authors_full_verified']=row.authors_primary;v['full_given_names_source']=row.source_url;v['primary_name_check']=row.check_result;v['primary_online_date']=row.get('online_date','')
    if pd.notna(row.get('title_primary')):
     v['title_primary_difference']=v['title_crossref_raw']!=row.title_primary;v['title']=row.title_primary
 pd.DataFrame(verified).to_csv(R/'refs_verified.csv',index=False)
 candidates=[]
 pattern=re.compile(r'foreign (?:institutional |portfolio )?investor|foreign institutional ownership|stock connect|capital.market liberaliz|international institutional investor',re.I)
 for i,(journal,issn) in enumerate(JOURNALS):
  by={}
  for j in range(len(TERMS)):
   p=OUT/f'candidate_{i}_{j}.json'
   if not p.exists():continue
   for a in json.loads(p.read_text()).get('message',{}).get('items',[]):
    m=metadata(a);text=m['title']+' '+clean(a.get('abstract',''));hits=pattern.findall(text)
    if not hits and re.search('liability of foreignness',text,re.I) and re.search('capital market|stock market|securit|portfolio|institutional invest|equity market',text,re.I):hits=['liability of foreignness in capital markets']
    if not hits or not (2019<=int(m.get('year') or 0)<=2026):continue
    # Keyword relevance is a retrieval criterion, never an inclusion recommendation.
    m.update(search_journal=journal,matched_keywords='; '.join(sorted(set(hits))),selection='direct title/abstract keyword match; newest first; max ten per journal');by[m['doi']]=m
  candidates+=sorted(by.values(),key=lambda x:(-int(x['year']),x['doi']))[:10]
 # Merge independent OpenAlex journal searches before applying the same journal cap.
 extra_path=R/'meta/openalex_search_candidates.csv'
 if extra_path.exists():
  extra=pd.read_csv(extra_path).replace({np.nan:''}).to_dict('records');pool={x['doi'].lower():x for x in candidates}
  for x in extra:
   key=x['doi'].lower()
   if key in pool:
    if not pool[key].get('abstract_300') and x.get('abstract_300'):pool[key]['abstract_300']=x['abstract_300'];pool[key]['abstract_status']='AVAILABLE_OPENALEX_SEARCH';pool[key]['openalex_id']=x.get('openalex_id','')
   else:pool[key]=x
  candidates=[]
  for journal,issn in JOURNALS:candidates+=sorted([x for x in pool.values() if x.get('search_journal')==journal],key=lambda x:(-int(x['year']),x['doi']))[:10]
 # Recover exact journal-year/volume/pages for candidates discovered only via OpenAlex.
 fresh=[(i,x) for i,x in enumerate(candidates) if str(x.get('metadata_source','')).startswith('OpenAlex')];lookup=[('cf_candidate_'+hashlib.sha256(x['doi'].encode()).hexdigest()[:16],'https://api.crossref.org/works/'+urllib.parse.quote(x['doi'],safe='/')) for i,x in fresh]
 with cf.ThreadPoolExecutor(max_workers=4) as executor:cf_receipts=list(executor.map(get,lookup))
 for (i,original),receipt in zip(fresh,cf_receipts):
  if receipt['status']!=200:continue
  response=json.loads(Path(receipt['path']).read_text());m=metadata(response.get('message',{}))
  if m['doi'].lower()!=original['doi'].lower():candidates[i]['metadata_check']='CROSSREF_DOI_MISMATCH';continue
  candidates[i]['openalex_publication_year']=original['year']
  for key in ['title','authors','journal','year','volume','issue','pages','article_number','url']:
   if m.get(key) not in [None,'']:candidates[i][key]=m[key]
  if not original.get('abstract_300') and m.get('abstract_300'):candidates[i]['abstract_300']=m['abstract_300'];candidates[i]['abstract_status']='AVAILABLE_CROSSREF'
  candidates[i]['metadata_source']='Crossref DOI metadata + OpenAlex independent search';candidates[i]['metadata_check']='DOI_CONFIRMED'
 save(cf_receipts,'literature_candidate_crossref_enrichment_receipts.csv');candidates=[x for x in candidates if 2019<=int(x['year'])<=2026]
 # OpenAlex DOI lookup provides missing abstracts, preserving missing status if unavailable.
 enrich=[('oa_'+str(i),'https://api.openalex.org/works/https://doi.org/'+x['doi']) for i,x in enumerate(candidates) if not x['abstract_300']]
 with cf.ThreadPoolExecutor(max_workers=4) as pool:oa=list(pool.map(get,enrich))
 for rec in oa:
  if rec['status']!=200:continue
  idx=int(rec['name'].split('_')[-1]);a=json.loads(Path(rec['path']).read_text());assert (a.get('doi') or '').lower().endswith(candidates[idx]['doi'].lower());inv=a.get('abstract_inverted_index') or {};words={n:w for w,ns in inv.items() for n in ns};abstract=' '.join(words[n] for n in sorted(words));candidates[idx]['abstract_300']=excerpt(abstract);candidates[idx]['abstract_status']='AVAILABLE_OPENALEX' if abstract else 'MISSING_CROSSREF_AND_OPENALEX';candidates[idx]['openalex_id']=a.get('id')
 pd.DataFrame(candidates).to_csv(R/'refs_candidates.csv',index=False);save(oa,'literature_openalex_receipts.csv');print('LITERATURE',len(verified),len(candidates),flush=True)
if __name__=='__main__':main()
