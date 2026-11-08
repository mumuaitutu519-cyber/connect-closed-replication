import requests,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
urls={'tc.dat':'https://www.hko.gov.hk/dps/wxinfo/climat/warndb/tc.dat','rain_form.html':'https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml','rstorm.dat':'https://www.hko.gov.hk/dps/wxinfo/climat/warndb/rstorm.dat'}
def f(j):
 n,u=j;p=Path('sources',n)
 if not p.exists():
  r=requests.get(u,timeout=40);r.raise_for_status();p.write_bytes(r.content)
 return dict(name=n,url=u,status='CACHED_OR_FETCHED',bytes=p.stat().st_size)
print(list(ThreadPoolExecutor(4).map(f,urls.items())))
