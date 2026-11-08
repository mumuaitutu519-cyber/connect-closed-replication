#!/usr/bin/env python3
"""Fetch specified official records and save receipts; do not bypass blocked sources."""
from pathlib import Path
import urllib.request,urllib.parse,json,datetime,hashlib,concurrent.futures,re,html
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'meta/official_raw'
DEST.mkdir(parents=True,exist_ok=True)
def fetch(job):
 name,url=job; at=datetime.datetime.now(datetime.timezone.utc).isoformat();p=DEST/name
 if p.exists():return dict(name=name,url=url,status='CACHED',path=str(p))
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'266-connect-closed-research/1.0'})
  with urllib.request.urlopen(req,timeout=50) as f:body=f.read(20*1024*1024);status=f.status;headers=dict(f.headers)
  p.write_bytes(body)
  return dict(name=name,url=url,status=status,retrieved_utc=at,path=str(p),bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),headers=headers)
 except Exception as e:return dict(name=name,url=url,status='FAILED',retrieved_utc=at,error=str(e),no_bypass=True)
def main():
 jobs=[('calendar_index.html','https://www.hkex.com.hk/mutual-market/stock-connect/reference-materials/trading-hour%2C-trading-and-settlement-calendar?sc_lang=en'),('calendar_enhancement_20230224.html','https://www.hkex.com.hk/News/News-Release/2023/2302243news?sc_lang=en'),('sfc_20220812.html','https://apps.sfc.hk/edistributionWeb/api/news/list-content?lang=EN&refNo=22PR61')]
 base='https://www.hkex.com.hk/-/media/HKEX-Market/Mutual-Market/Stock-Connect/Reference-Materials/Trading-Hour%2C-Trading-and-Settlement-Calendar/'
 jobs += [(f'calendar_historical_{y}.pdf',base+f'{y}-%28Eng%29.pdf?la=en') for y in [2017,2018,2019,2020,2023]]
 jobs += [(f'calendar_trading_{y}.csv',base+f'{y}-Calendar_csv_e.csv') for y in [2023,2024]]
 jobs += [('calendar_trading_2023.pdf',base+'2023-Calendar_pdf_e.pdf')]
 with concurrent.futures.ProcessPoolExecutor(max_workers=4) as p: rs=list(p.map(fetch,jobs))
 path=ROOT/'meta/official_receipts.json';old=json.loads(path.read_text()) if path.exists() else [];path.write_text(json.dumps(old+rs,ensure_ascii=False,indent=2))
 for r in rs:print(json.dumps(r,ensure_ascii=False))
 if (DEST/'calendar_index.html').exists():
  s=(DEST/'calendar_index.html').read_text(errors='replace')
  links=[html.unescape(x) for x in re.findall(r'href=["\x27]([^"\x27]+)',s) if any(str(y) in x for y in range(2017,2027)) and any(ext in x.lower() for ext in ['pdf','csv','xls'])]
  links=sorted(set(urllib.parse.urljoin('https://www.hkex.com.hk',x) for x in links))
  jobs=[(f'calendar_{i}_'+urllib.parse.unquote(urllib.parse.urlparse(u).path).split('/')[-1].replace(' ','_'),u) for i,u in enumerate(links)]
  with concurrent.futures.ProcessPoolExecutor(max_workers=4) as p: rs=list(p.map(fetch,jobs))
  old=json.loads(path.read_text());path.write_text(json.dumps(old+rs,ensure_ascii=False,indent=2))
  for r in rs: print(json.dumps(r,ensure_ascii=False))
if __name__=='__main__':main()
