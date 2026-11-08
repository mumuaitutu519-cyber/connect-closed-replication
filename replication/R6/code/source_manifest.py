from common import *
import hashlib,re

def main():
 urls={'tc.dat':'https://www.hko.gov.hk/dps/wxinfo/climat/warndb/tc.dat','rstorm.dat':'https://www.hko.gov.hk/dps/wxinfo/climat/warndb/rstorm.dat','2016_connect_weather_rules.pdf':'https://www.hkex.com.hk/-/media/HKEX-Market/Services/Rules-and-Forms-and-Fees/Rules/SEHK/Securities/Rule-Update_Rules-of-the-Exchange/105-16-SEHK-Shenzhen-HK-Stock-Connect_e_markup.pdf'}
 for r in json.loads((R/'meta/supplemental_source_receipts.json').read_text()):urls[r['name']]=r['url']
 for r in json.loads((R/'meta/hkex_fetch_receipts.json').read_text()):
  if r.get('url'):
   base=r['url'].split('/')[-1].split('?')[0];urls[base+'.html']=r['url'];urls[base+'.txt']=r['url']
 f=pd.read_csv(R/'meta/forecast_bulletins.csv')
 for u in f.url:urls['forecasts/'+u.rsplit('/',1)[-1]]=u
 urls['SFC_2025Q3_web_evidence.json']=next(r['url'] for r in json.loads((R/'meta/supplemental_source_receipts.json').read_text()) if r['name']=='2025Q3_SFC_operations.pdf')
 for p in (R/'sources/forecasts').glob('index_*.html'):
  d=p.stem.removeprefix('index_');u=f'https://www.info.gov.hk/gia/wr/{d[:6]}/{d[6:]}.htm';urls['forecasts/'+p.name]=u;urls[f'forecasts/{d[:6]}_{d[6:]}.htm']=u
 out=[]
 for p in sorted((R/'sources').rglob('*')):
  if not p.is_file():continue
  name=str(p.relative_to(R/'sources'));u=urls.get(name,'');role='cached_official_source' if u else 'ancillary_or_obsolete_cache_not_used_for_event_assignment'
  if re.fullmatch(r'\d{6}\d?news\.html',p.name) and not u:
   n=p.stem;u=f'https://www.hkex.com.hk/News/Market-Communications/20{n[:2]}/{n}?sc_lang=en';role='unused_candidate_error_or_nonweather_page'
  if p.name=='SFC_2025Q3_web_evidence.json':role='official_web_extraction_evidence_original_pdf_inaccessible'
  out.append(dict(file='sources/'+name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),url=u,role=role))
 (R/'meta/source_snapshots.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print('Official source snapshots indexed:',len(out))
if __name__=='__main__':main()
