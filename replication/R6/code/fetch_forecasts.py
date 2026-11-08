from common import *
import requests,re
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
D=['20170822','20170823','20190730','20190731','20200818','20201012','20201013','20210627','20210628','20220824','20221101','20221102','20230714','20230716','20230831','20230907','20231006','20231008','20240905']
OUT=R/'sources/forecasts';OUT.mkdir(exist_ok=True)
def get(u):
 n=u.rsplit('/',1)[-1];n=(u.rsplit('/',2)[-2]+'_'+n) if n[:1].isdigit() else n;p=OUT/n
 try:
  if not p.exists():p.write_bytes(requests.get(u,timeout=25).content)
  s=BeautifulSoup(p.read_bytes(),'html.parser');return u,s
 except Exception:return u,None
urls=[]
for d in D:
 u=f'https://www.info.gov.hk/gia/wr/{d[:6]}/{d[6:]}.htm';_,s=get(u)
 if s is None:continue
 (OUT/f'index_{d}.html').write_text(str(s))
 for a in s.find_all('a'):
  h=a.get('href','');txt=a.get_text(' ',strip=True)
  if h.startswith('/gia/wr/') and ('TROPICAL CYCLONE' in txt or 'LOCAL WEATHER FORECAST' in txt or 'RAINSTORM WARNING' in txt):urls.append('https://www.info.gov.hk'+h)
rs=[]
for u,s in ThreadPoolExecutor(4).map(get,sorted(set(urls))):
 if s is None:continue
 text=s.get_text(' ',strip=True);ts=re.search(r'DISPATCHED BY HONG KONG OBSERVATORY AT (\d{2}:\d{2}) HKT ON (\d{2}\.\d{2}\.\d{4})',text)
 if not ts:continue
 date=pd.to_datetime(ts[2],format='%d.%m.%Y')+pd.Timedelta(hours=int(ts[1][:2]),minutes=int(ts[1][3:]));mentions8=bool(re.search(r'(NO\.?\s*8|NUMBER\s*8)',text,re.I));preview=''
 if mentions8:
  z=re.split(r'(?<=[.!])\s+',text);preview=' | '.join(t for t in z if re.search(r'NO\.?\s*8|NUMBER\s*8',t,re.I))
 rs.append(dict(timestamp=date,url=u,mentions8=mentions8,excerpt=preview,text=text))
pd.DataFrame(rs).to_csv(R/'meta/forecast_bulletins.csv',index=False)
for x in rs:
 if x['mentions8']:print(x['timestamp'],x['url'],x['excerpt'][:700],flush=True)
