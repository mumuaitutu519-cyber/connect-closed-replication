from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests,re,json
from bs4 import BeautifulSoup
D=['20170524','20170612','20170613','20170823','20180917','20190731','20190801','20200819','20201013','20210628','20211008','20211013','20220825','20221102','20221103','20230717','20230901','20230908','20231009','20240906','20241114']
jobs=[(d,s) for d in D for s in ['','2','3']]
def f(j):
 d,s=j;n=d[2:]+s+'news';u=f'https://www.hkex.com.hk/News/Market-Communications/{d[:4]}/{n}?sc_lang=en';p=Path('sources')/f'{n}.html'
 try:
  if not p.exists():p.write_bytes(requests.get(u,timeout=30).content)
  t=BeautifulSoup(p.read_bytes(),'html.parser');h=t.find('h1');h=h.get_text(' ',strip=True) if h else ''
  if not h or 'Page Not Found' in t.get_text():return None
  # Actual article is a dedicated content panel; retain entire official HTML, extract beginning at h1.
  text=t.get_text(' ',strip=True);start=text.rfind(h);text=text[start:];text=text[:text.find('Last updated')] if 'Last updated' in text else text
  valid=any(k in h.lower() for k in ['typhoon','rainstorm','severe weather'])
  if valid:Path('sources',f'{n}.txt').write_text(text)
  return dict(date=d,url=u,headline=h,valid_weather=valid,text=text[:6000] if valid else '')
 except Exception as e:return dict(date=d,url=u,error=str(e))
r=[x for x in ThreadPoolExecutor(4).map(f,jobs) if x];Path('meta/hkex_fetch_receipts.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
for x in r:
 if x.get('valid_weather'):print(x['date'],x['url'],x['text'][:3500],flush=True)
